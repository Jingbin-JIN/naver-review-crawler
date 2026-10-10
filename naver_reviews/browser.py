"""브라우저(Playwright)로 업체 리뷰 페이지를 열고, 리뷰가 담긴 데이터를 모은다.

모으는 것: 페이지에 들어 있는 Apollo 상태(window.__APOLLO_STATE__)와
'더보기'를 누를 때 오가는 GraphQL 응답. 화면 글자를 긁지 않아서 화면 디자인이 바뀌어도 덜 깨진다.
"""

from contextlib import contextmanager

from .ids import MOBILE_UA, extract_place_id

DEFAULT_URL_TEMPLATE = "https://m.place.naver.com/{category}/{place_id}/review/visitor?reviewSort=recent"
DEFAULT_CATEGORIES = ("restaurant", "place", "cafe")
# 목록 맨 아래 '더보기' 문구 후보 (앞에 있는 것부터 찾는다)
MORE_TEXTS = ("펼쳐서 더보기", "더보기")


@contextmanager
def open_browser(headed=False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            user_agent=MOBILE_UA,
            viewport={"width": 390, "height": 844},
            locale="ko-KR",
            is_mobile=True,
            has_touch=True,
        )
        try:
            yield context
        finally:
            context.close()
            browser.close()


def final_url(context, url, timeout_ms=15000):
    """단축 링크를 브라우저로 열어 최종 주소를 돌려준다. 주소에 플레이스 ID가 보일 때까지 잠깐 기다린다."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_url(lambda u: extract_place_id(u) is not None, timeout=5000)
        except Exception:
            pass
        return page.url
    finally:
        page.close()


def _click_more(page):
    """화면에 보이는 '더보기' 중 가장 아래에 있는 것(목록 더보기)을 누른다."""
    for text in MORE_TEXTS:
        locator = page.get_by_text(text, exact=True)
        try:
            count = locator.count()
        except Exception:
            continue
        best, best_y = None, None
        for i in range(count):
            el = locator.nth(i)
            try:
                if not el.is_visible():
                    continue
                box = el.bounding_box()
            except Exception:
                continue
            if box and (best_y is None or box["y"] > best_y):
                best, best_y = el, box["y"]
        if best is not None:
            try:
                best.scroll_into_view_if_needed(timeout=5000)
                best.click(timeout=5000)
                return True
            except Exception:
                return False
    return False


def _operation_names(request):
    """GraphQL 요청 본문에서 작업 이름(operationName)만 꺼낸다. 확인용."""
    try:
        body = request.post_data_json
    except Exception:
        return []
    items = body if isinstance(body, list) else [body]
    return [str(x["operationName"]) for x in items if isinstance(x, dict) and x.get("operationName")]


def fetch_place(context, place_id, category="restaurant", url_template=DEFAULT_URL_TEMPLATE,
                max_more=2, wait_ms=2000, timeout_ms=30000):
    url = url_template.format(category=category, place_id=place_id)
    result = {
        "place_id": place_id, "category": category, "url": url, "final_url": "",
        "http_status": None, "apollo_state": None, "graphql": [], "graphql_ops": [],
        "more_clicks": 0, "error": "",
    }
    page = context.new_page()
    responses = []

    def remember(response):
        if "graphql" in response.url:
            responses.append(response)

    page.on("response", remember)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        result["http_status"] = resp.status if resp else None
        page.wait_for_timeout(wait_ms)
        result["apollo_state"] = page.evaluate("() => window.__APOLLO_STATE__ || null")
        clicks = 0
        for _ in range(max_more):
            if not _click_more(page):
                break
            clicks += 1
            page.wait_for_timeout(wait_ms)
        result["more_clicks"] = clicks
        payloads, ops = [], []
        for r in responses:
            ops.extend(_operation_names(r.request))
            try:
                if "json" not in (r.headers.get("content-type") or ""):
                    continue
                payloads.append(r.json())
            except Exception:
                continue
        result["graphql"] = payloads
        result["graphql_ops"] = ops
        result["final_url"] = page.url
    except Exception as e:  # 한 업체가 실패해도 나머지는 계속 수집
        result["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        page.close()
    return result
