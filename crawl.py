#!/usr/bin/env python3
"""네이버 플레이스 방문자 리뷰 수집기 v0.2 (연구용)

사용 예 (맥에서는 python 대신 .venv/bin/python)
  python crawl.py run --input 팀시트.xlsx --sheet 팀원A          시트의 업체 수집 (링크가 없으면 업체명으로 찾음)
  python crawl.py run --place "링크1" --place "링크2"           시트 없이 링크로 바로 수집
  python crawl.py probe --place "공유 링크"                     업체 1곳의 실제 데이터 구조 확인
  python crawl.py export                                        누적 CSV 전체를 엑셀로

엔진: 기본은 http(브라우저 없이 페이지 HTML의 데이터를 읽음, 업체당 최신 리뷰 10개).
      --engine browser는 브라우저로 열고 '더보기'까지 시도한다.
"""

import argparse
import contextlib
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from naver_reviews import __version__, extract, ids, places, store, web
from naver_reviews.browser import DEFAULT_CATEGORIES, DEFAULT_URL_TEMPLATE

KST = timezone(timedelta(hours=9), "KST")


def now_kst():
    return datetime.now(KST)


def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _scrubbed_capture(capture, place_name=""):
    return {
        "place_name": place_name,
        "place_id": capture["place_id"],
        "category": capture["category"],
        "requested": capture["url"],
        "final": capture["final_url"],
        "http_status": capture["http_status"],
        "error": capture["error"],
        "more_clicks": capture["more_clicks"],
        "graphql_operations": capture.get("graphql_ops", []),
        "apollo_state": extract.scrub(capture["apollo_state"]),
        "graphql": extract.scrub(capture["graphql"]),
    }


def _pause(args):
    time.sleep(random.uniform(args.delay_min, args.delay_max))


def _one_line(text):
    return " ".join(str(text or "").split())


def _make_follow(context, primary=None):
    """단축 링크(naver.me)의 최종 주소를 찾는 함수를 만든다. 파이썬으로 먼저 해 보고, 안 되면 브라우저로 연다."""
    from naver_reviews import browser

    primary = primary or ids.follow_redirects

    def follow(url, timeout):
        try:
            final = primary(url, timeout)
            if ids.extract_place_id(final):
                return final
        except Exception:
            pass
        return browser.final_url(context, url, timeout_ms=int(timeout * 1000))

    return follow


def _fetch(context, place_id, category, args):
    if args.engine == "browser":
        from naver_reviews import browser

        return browser.fetch_place(context, place_id, category=category, url_template=args.url_template,
                                   max_more=args.max_more, wait_ms=args.wait_ms)
    return web.fetch_place_http(place_id, category=category, url_template=args.url_template)


def _collect(context, place_id, args, today):
    """카테고리 후보 주소를 차례로 열어 리뷰가 나오면 멈춘다."""
    capture, reviews = None, []
    for n, category in enumerate(args.categories):
        if n > 0:
            _pause(args)
        capture = _fetch(context, place_id, category, args)
        reviews = extract.extract_all(capture["apollo_state"], capture["graphql"], today=today, salt=args.salt)
        if reviews:
            break
    return capture, reviews


@contextlib.contextmanager
def _maybe_browser(args):
    if args.engine == "browser":
        from naver_reviews import browser

        with browser.open_browser(headed=args.headed) as context:
            yield context
    else:
        yield None


def _targets(args):
    """(업체 목록, 읽은 시트 이름). --place가 있으면 그 링크들을, 아니면 --input 파일을 읽는다."""
    if args.place:
        return [{"name": ids.name_from_share_text(t), "link": t.strip(), "region": ""} for t in args.place], None
    return places.read_places_with_sheet(args.input, args.sheet)


def _resolve(pl, follow, args):
    """(플레이스 ID, 찾은 방법, 실패 상태). 링크가 있으면 링크로, 없으면 업체명 검색(정확히 같은 이름만)."""
    if pl["link"]:
        pid = ids.resolve_place_id(pl["link"], follow=follow)
        return (pid, "link", "") if pid else (None, "link", "unresolved_link")
    if args.no_search or not pl["name"]:
        return None, "", "no_link"
    try:
        candidates = web.search_places(pl["name"], coords=places.region_coords(pl.get("region"), web.DEFAULT_COORDS),
                                       search_url=args.search_url)
    except Exception as e:
        return None, "name", f"search_error: {type(e).__name__}"
    picked = web.pick_candidate(pl["name"], candidates)
    return (picked["id"], "name", "") if picked else (None, "name", "name_not_found")


def cmd_run(args):
    try:
        rows, sheet_used = _targets(args)
    except FileNotFoundError:
        print(f"입력 파일을 찾지 못했습니다: {args.input}")
        return 2
    except Exception as e:
        print(f"입력을 읽지 못했습니다: {e}")
        return 2
    if sheet_used:
        print(f"읽은 시트: {sheet_used} (업체 {len(rows)}곳)")
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out)
    start = now_kst()
    today = start.date()
    stamp = start.strftime("%Y%m%d_%H%M")

    logs, collected = [], []
    fetched_any = False
    with _maybe_browser(args) as context:
        follow = _make_follow(context) if context is not None else ids.follow_redirects
        for pl in rows:
            ts = now_kst().strftime("%Y-%m-%d %H:%M:%S")
            log = {c: "" for c in store.LOG_COLUMNS}
            log.update(collected_at=ts, place_name=pl["name"], link=_one_line(pl["link"]), reviews_found=0,
                       more_clicks=0)
            if not pl["link"] and (args.no_search or not pl["name"]):
                log["status"] = "no_link"
                logs.append(log)
                continue
            if fetched_any:
                _pause(args)
            fetched_any = True  # 검색이나 페이지 요청을 했으니 다음 업체 전에는 쉰다
            place_id, match, problem = _resolve(pl, follow, args)
            log["match"] = match
            if not place_id:
                log["status"] = problem
                logs.append(log)
                if problem != "no_link":
                    print(f"[{problem}] {pl['name'] or _one_line(pl['link'])[:40]}")
                continue
            name = pl["name"] or f"플레이스 {place_id}"
            capture, reviews = _collect(context, place_id, args, today)
            info = extract.place_info(capture["apollo_state"])
            for r in reviews:
                r.update(collected_at=ts, place_name=name, place_id=place_id)
            collected.extend(reviews)
            if not args.no_raw:
                _save_json(out / "raw" / today.isoformat() / f"{place_id}.json", _scrubbed_capture(capture, name))
            status = "ok" if reviews else ("error" if capture["error"] else "no_reviews")
            log.update(place_name=name, place_id=place_id, status=status, category=capture["category"],
                       http_status=capture["http_status"], reviews_found=len(reviews),
                       more_clicks=capture["more_clicks"], final_url=capture["final_url"], error=capture["error"],
                       **info)
            logs.append(log)
            print(f"[{status}] {name}: 리뷰 {len(reviews)}건 | 전체 {info['review_total']} | 쿠폰 {info['coupon_count']}")

    new_rows = store.append_new_reviews(out / "reviews.csv", collected)
    store.append_rows(out / "run_log.csv", logs, store.LOG_COLUMNS)
    xlsx = store.export_xlsx(collected, out / f"reviews_{stamp}.xlsx", places=logs)
    counts = Counter(l["status"] for l in logs)
    print("\n완료: 업체 {}곳 | 리뷰 {}건 (새로 저장 {}건)".format(len(rows), len(collected), len(new_rows)))
    print("상태별: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"이번 실행 엑셀: {xlsx} ('리뷰'·'업체' 시트)")
    if counts.get("no_link"):
        print(f"링크도 업체명도 쓸 수 없는 업체 {counts['no_link']}곳은 건너뛰었습니다.")
    if counts.get("name_not_found"):
        print("업체명이 네이버와 정확히 같지 않은 곳은 건너뛰었습니다. 시트에 '플레이스 링크'를 넣으면 해결됩니다.")
    if counts.get("no_reviews") or counts.get("error"):
        print("리뷰를 못 찾은 업체가 있으면 probe로 구조를 확인하세요 (README '문제 해결').")
    return 0


def _typename_counts(state, top=15):
    if not isinstance(state, dict):
        return []
    c = Counter(v.get("__typename") for v in state.values() if isinstance(v, dict) and v.get("__typename"))
    return c.most_common(top)


def _review_like_typenames(state, top=10):
    return [(t, n) for t, n in _typename_counts(state, top=None) if "review" in str(t).lower()][:top]


def _shape(value, state, depth):
    """값은 빼고 구조(키 이름과 자료형)만 보여 준다. 닉네임 같은 값은 드러나지 않는다."""
    value = extract.deref(value, state)
    if isinstance(value, dict):
        if depth <= 0:
            return "{…}"
        return {k: _shape(v, state, depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return "[]"
        return [_shape(value[0], state, depth - 1), f"{len(value)}개"]
    return type(value).__name__


def _probe_lines(cap, reviews):
    state = cap["apollo_state"]
    info = extract.place_info(state)
    lines = [
        f"[{cap['category']}] {cap['url']}",
        f"  HTTP {cap['http_status']} | 최종 주소: {cap['final_url'] or '-'} | 오류: {cap['error'] or '-'}",
        "  Apollo 상태: {} | GraphQL 응답 {}개 | 더보기 {}회".format(
            f"있음({len(state)}개 항목)" if isinstance(state, dict) else "없음",
            len(cap["graphql"]), cap["more_clicks"]),
        f"  업체: {info['place_title'] or '-'} | {info['place_category'] or '-'} | {info['road_address'] or '-'}",
        f"  방문자 리뷰 수(전체): {info['review_total']} | 쿠폰 수: {info['coupon_count']}",
        f"  GraphQL 작업 이름: {', '.join(cap.get('graphql_ops') or []) or '-'}",
        f"  자주 나온 객체 종류: {_typename_counts(state)}",
        f"  'Review'가 들어간 객체 종류: {_review_like_typenames(state) or '-'}",
        f"  찾은 리뷰: {len(reviews)}건",
    ]
    first = extract.first_review(state, cap["graphql"])
    if first is not None:
        matched = {field: next((k for k in cands if k in first), None)
                   for field, cands in extract.FIELD_CANDIDATES.items()}
        lines.append("  첫 리뷰 객체의 키: " + ", ".join(sorted(first.keys())))
        lines.append(f"  필드 대응(코드 이름 → 실제 키): {matched}")
        lines.append("  첫 리뷰 구조(값 없이): " + json.dumps(_shape(first, state, 3), ensure_ascii=False))
    if reviews:
        r = reviews[0]
        summary = {k: r[k] for k in ("created", "visited", "rating", "photo_count", "origin", "visit_count",
                                     "keywords", "reviewer_review_count", "reviewer_photo_count", "event_mention")}
        lines.append(f"  첫 리뷰 요약: {summary}")
        lines.append(f"  본문 앞부분: {_one_line(r['body'])[:60]}")
    else:
        hints = extract.body_like_typenames(state, cap["graphql"])
        lines.append(f"  본문 필드가 있는 객체 종류(진단용): {hints or '-'}")
    return lines


def cmd_probe(args):
    out = Path(args.out) / "probe"
    today = now_kst().date()

    with _maybe_browser(args) as context:
        follow = _make_follow(context) if context is not None else ids.follow_redirects
        place_id = ids.resolve_place_id(args.place, follow=follow)
        if not place_id:
            print("링크에서 플레이스 ID를 찾지 못했습니다. 공유 링크나 플레이스 주소를 그대로 넣어 주세요.")
            return 2
        name = ids.name_from_share_text(args.place) or f"플레이스 {place_id}"
        for n, category in enumerate(args.categories):
            if n > 0:
                _pause(args)
            cap = _fetch(context, place_id, category, args)
            reviews = extract.extract_all(cap["apollo_state"], cap["graphql"], today=today, salt=args.salt)
            base = out / f"probe_{place_id}_{category}"
            json_path = Path(f"{base}.json")
            summary_path = Path(f"{base}_summary.txt")
            _save_json(json_path, _scrubbed_capture(cap, name))
            saved = [json_path, summary_path]
            if reviews:
                ts = now_kst().strftime("%Y-%m-%d %H:%M:%S")
                for r in reviews:
                    r.update(collected_at=ts, place_name=name, place_id=place_id)
                saved.append(store.export_xlsx(reviews, Path(f"{base}_reviews.xlsx")))
            lines = _probe_lines(cap, reviews)
            lines.append("  저장(개인정보 제거): " + ", ".join(str(p) for p in saved))
            summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("\n" + "\n".join(lines))
            if reviews and not args.all_categories:
                break
    return 0


def cmd_export(args):
    out = Path(args.out)
    rows = store.read_rows(out / "reviews.csv")
    path = store.export_xlsx(rows, out / f"reviews_all_{now_kst():%Y%m%d_%H%M}.xlsx")
    print(f"리뷰 {len(rows)}건 → {path}")
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", default="data", help="결과 폴더 (기본: data)")
    common.add_argument("--engine", choices=("http", "browser"), default="http",
                        help="http: 브라우저 없이 최신 리뷰 10개(기본) / browser: 브라우저로 열고 더보기까지 시도")
    common.add_argument("--headed", action="store_true", help="(browser 엔진) 브라우저 창을 띄워서 실행")
    common.add_argument("--max-more", type=int, default=2, help="(browser 엔진) 업체마다 '더보기'를 누르는 최대 횟수")
    common.add_argument("--delay-min", type=float, default=4.0, help="업체 사이 최소 대기 초 (기본 4)")
    common.add_argument("--delay-max", type=float, default=8.0, help="업체 사이 최대 대기 초 (기본 8)")
    common.add_argument("--wait-ms", type=int, default=2000, help="(browser 엔진) 페이지를 연 뒤 기다리는 시간(ms)")
    common.add_argument("--categories", nargs="+", default=list(DEFAULT_CATEGORIES),
                        help="주소에 넣을 업종 경로 후보 (기본: restaurant place cafe)")
    common.add_argument("--url-template", default=DEFAULT_URL_TEMPLATE, help="리뷰 페이지 주소 형식")
    common.add_argument("--search-url", default=web.SEARCH_URL, help=argparse.SUPPRESS)
    common.add_argument("--salt", default=os.environ.get("REVIEW_SALT", ""),
                        help="리뷰어 구분값을 만들 비밀 문자열 (비우면 저장 안 함)")

    parser = argparse.ArgumentParser(description=f"네이버 플레이스 방문자 리뷰 수집기 (연구용 v{__version__})")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", parents=[common], help="시트의 업체(또는 링크) 리뷰 수집")
    source = p_run.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="팀 시트를 xlsx로 받은 파일 또는 CSV ('업체명' 열, 선택: '플레이스 링크'·'장소' 열)")
    source.add_argument("--place", action="append", help="공유 링크나 플레이스 주소 (여러 번 쓸 수 있음)")
    p_run.add_argument("--sheet", default=None, help="탭 이름 (예: 팀원A). 비우면 '업체명' 열이 있는 첫 탭")
    p_run.add_argument("--no-search", action="store_true", help="링크가 없을 때 업체명으로 찾지 않음")
    p_run.add_argument("--limit", type=int, default=0, help="앞에서부터 이 개수만 (0이면 전체)")
    p_run.add_argument("--no-raw", action="store_true", help="원본 JSON(개인정보 제거본) 저장 안 함")
    p_run.set_defaults(func=cmd_run)
    p_probe = sub.add_parser("probe", parents=[common], help="업체 1곳의 실제 데이터 구조 확인")
    p_probe.add_argument("--place", required=True, help="공유 링크, 플레이스 주소 또는 숫자 ID")
    p_probe.add_argument("--all-categories", action="store_true", help="리뷰를 찾아도 모든 경로 후보를 확인")
    p_probe.set_defaults(func=cmd_probe)
    p_export = sub.add_parser("export", parents=[common], help="누적 reviews.csv를 엑셀로 내보내기")
    p_export.set_defaults(func=cmd_export)
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.delay_min < 0 or args.delay_max < args.delay_min:
        print("--delay-min은 0 이상, --delay-max는 --delay-min 이상이어야 합니다.")
        return 2
    if args.max_more < 0:
        print("--max-more는 0 이상이어야 합니다.")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
