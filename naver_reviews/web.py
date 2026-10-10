"""브라우저 없이 수집하는 방식(기본 엔진)과 업체명 검색.

네이버 모바일 플레이스의 리뷰 페이지는 처음 내려받는 HTML 안에 데이터(window.__APOLLO_STATE__)를 담고 있다.
여기에 업체 정보, 쿠폰 수, 최신 방문자 리뷰 10개가 들어 있다(2026-10-09 실제 페이지로 확인).
더 많은 리뷰(더보기)는 브라우저 엔진(--engine browser)으로만 시도할 수 있다.
"""

import json
import re
import unicodedata
import urllib.parse

from . import net
from .browser import DEFAULT_URL_TEMPLATE
from .ids import MOBILE_UA

SEARCH_URL = "https://map.naver.com/p/api/search/instant-search"
DEFAULT_COORDS = "37.5665,126.9780"  # 서울시청 (위도,경도)

_APOLLO_RE = re.compile(r"window\.__APOLLO_STATE__\s*=\s*")
_PAGE_HEADERS = {"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"}


def parse_apollo(html):
    """HTML에서 window.__APOLLO_STATE__ 객체를 꺼낸다. 없거나 깨졌으면 None."""
    m = _APOLLO_RE.search(html or "")
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[m.end():])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def is_captcha(html):
    """네이버가 자동 접속 확인(캡차) 화면을 보냈는지."""
    text = html or ""
    return "WtmCaptcha" in text or 'title="captcha"' in text


def fetch_place_http(place_id, category="restaurant", url_template=DEFAULT_URL_TEMPLATE, timeout=20):
    """리뷰 페이지 HTML을 받아 browser.fetch_place와 같은 모양의 결과를 돌려준다."""
    url = url_template.format(category=category, place_id=place_id)
    result = {
        "place_id": place_id, "category": category, "url": url, "final_url": "",
        "http_status": None, "apollo_state": None, "graphql": [], "graphql_ops": [],
        "more_clicks": 0, "error": "",
    }
    try:
        status, final_url, body = net.open_url(url, headers=_PAGE_HEADERS, timeout=timeout)
        html = body.decode("utf-8", "replace")
        result.update(http_status=status, final_url=final_url)
        if is_captcha(html):
            result["error"] = "captcha: 네이버가 자동 접속 확인을 요구했습니다. 시간을 두고 다시 시도하세요."
        elif status >= 400:
            result["error"] = f"HTTP {status}"
        else:
            result["apollo_state"] = parse_apollo(html)
            if result["apollo_state"] is None:
                result["error"] = "페이지에서 데이터를 찾지 못했습니다"
    except Exception as e:  # 한 업체가 실패해도 나머지는 계속 수집
        result["error"] = f"{type(e).__name__}: {e}"[:300]
    return result


def search_places(query, coords=DEFAULT_COORDS, search_url=SEARCH_URL, timeout=15):
    """네이버지도 자동완성 검색으로 업체 후보를 찾는다. [{id, title, category, road_address, review_count}]"""
    url = search_url + "?" + urllib.parse.urlencode({"query": query, "coords": coords})
    headers = {"User-Agent": net.DESKTOP_UA, "Referer": "https://map.naver.com/",
               "Accept-Language": "ko-KR,ko;q=0.9"}
    status, _, body = net.open_url(url, headers=headers, timeout=timeout)
    if status >= 400:
        raise RuntimeError(f"검색 HTTP {status}")
    data = json.loads(body.decode("utf-8"))
    out = []
    for p in data.get("place") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        out.append({
            "id": str(p["id"]),
            "title": str(p.get("title") or ""),
            "category": str(p.get("ctg") or ""),
            "road_address": str(p.get("roadAddress") or p.get("jibunAddress") or ""),
            "review_count": (p.get("review") or {}).get("count") if isinstance(p.get("review"), dict) else None,
        })
    return out


def _norm_name(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(s or ""))).lower()


def pick_candidate(name, candidates):
    """업체명과 정확히 같은 후보만 고른다(띄어쓰기·대소문자는 무시). 없으면 None. 비슷한 이름은 고르지 않는다."""
    target = _norm_name(name)
    if not target:
        return None
    for c in candidates:
        if _norm_name(c.get("title")) == target:
            return c
    return None
