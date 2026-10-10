"""수집한 페이지 데이터(Apollo 상태, GraphQL 응답)에서 방문자 리뷰를 찾아 정리한다.

네이버 페이지 구조는 바뀔 수 있다. 그래서 리뷰 객체의 이름과 필드 이름을 후보 목록으로 두었다.
2026-10-09 실제 모바일 리뷰 페이지로 확인한 구조: ROOT_QUERY의 visitorReviews(input…includeContent:true…)에
최신 리뷰 10개가 VisitorReview 참조로 들어 있고, 작성자는 VisitorReviewAuthor 참조다.
같은 페이지의 includeContent:false 목록(본문 없는 다른 묶음)은 섞지 않는다.
"""

import hashlib
import json
import re
from collections import Counter
from datetime import date

# 방문자 리뷰 객체의 __typename 후보
REVIEW_TYPENAMES = {"VisitorReview"}

# 필드별 후보 이름 (앞에 있는 것부터 찾는다)
FIELD_CANDIDATES = {
    "body": ("body", "content", "text"),
    "created": ("created", "createdString", "createdAt"),
    "visited": ("visited", "visitedString", "visitedAt", "representativeVisitDateTime"),
    "origin": ("originType", "origin", "verifyType"),
    "visit_count": ("visitCount",),
    "media": ("media", "photos", "images"),
    "thumbnail": ("thumbnail",),
    "keywords": ("votedKeywords", "keywords"),
    "author": ("author", "writer", "user"),
    "rating": ("rating",),
}

# 저장 전에 지울 개인 식별 정보 키
PERSONAL_KEYS = {
    "nickname", "author", "writer", "user", "userIdno", "loginIdno", "userId", "authorId",
    "objectId", "idno", "imageUrl", "profileImageUrl", "profileUrl", "url", "from",
    "followerCount", "followRequested", "isFollowing", "receiptInfoUrl", "borderImageUrl",
    # 블로그·카페 글 주소와 작성자 이름 (주소에 작성자 ID가 들어 있다)
    "linkUrl", "home", "authorName", "blogUrl", "cafeUrl", "writerUrl",
}

_REWARD = r"(?:받|주|준|줘|줌|증정|서비스|제공|드려|드립|드림|무료)"
_EVENT_RE = re.compile(
    r"리뷰\s*(?:이벤트|쿠폰)"
    r"|리뷰\s*(?:를\s*)?(?:쓰고|쓰면|써서|작성하고|작성하면|작성\s*시|남기고|남기면|남겨서)"
    r"[^.!?\n]{0,20}?" + _REWARD
)
_SERVICE_RE = re.compile(
    r"(?:서비스로|서비스\s*(?:음료|메뉴|안주)|무료로)[^.!?\n]{0,15}?(?:받|주|준|줘|나왔|나와|제공)"
)


def _first(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _int(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def deref(value, state):
    """Apollo 정규화 데이터의 {"__ref": key} 참조를 실제 객체로 바꾼다."""
    if isinstance(value, dict) and "__ref" in value and isinstance(state, dict):
        return state.get(value["__ref"], {})
    return value


def looks_like_review(d):
    if not isinstance(d, dict):
        return False
    typename = d.get("__typename")
    if typename in REVIEW_TYPENAMES:
        return True
    if typename is None and "id" in d:
        has_body = _first(d, FIELD_CANDIDATES["body"]) is not None
        has_date = _first(d, FIELD_CANDIDATES["created"] + FIELD_CANDIDATES["visited"]) is not None
        return has_body and has_date
    return False


def iter_reviews(payload, state=None):
    """payload 안의 리뷰 객체를 한 번씩만 돌려준다. __ref 참조도 따라간다."""
    seen_refs = set()
    seen_ids = set()
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "__ref" in cur:
                key = cur["__ref"]
                if isinstance(state, dict) and key not in seen_refs:
                    seen_refs.add(key)
                    target = state.get(key)
                    if target is not None:
                        stack.append(target)
                continue
            if looks_like_review(cur):
                rid = str(cur.get("id"))
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    yield cur
                continue
            stack.extend(reversed(list(cur.values())))
        elif isinstance(cur, list):
            stack.extend(reversed(cur))


def parse_date(raw, today):
    """'10.8.목', '2025.10.8.수', '24.10.8', '2025-10-08T...' 같은 표기를 날짜로 바꾼다."""
    if raw in (None, ""):
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(?:(\d{2,4})\.)?(\d{1,2})\.(\d{1,2})", s)
    if not m:
        return None
    year_txt, month, day = m.group(1), int(m.group(2)), int(m.group(3))
    try:
        if year_txt:
            year = int(year_txt)
            if year < 100:
                year += 2000
            return date(year, month, day)
        candidate = date(today.year, month, day)
        if candidate > today:
            candidate = date(today.year - 1, month, day)
        return candidate
    except ValueError:
        return None


def event_mention(text):
    """본문에 리뷰 이벤트 참여를 직접 밝힌 표현이 있으면 1 (사람이 다시 확인해야 하는 표시)."""
    return int(bool(_EVENT_RE.search(str(text or ""))))


def service_mention(text):
    """'서비스로 ○○ 주셨어요' 같은 무료 제공 언급이면 1 (이벤트와 무관할 수도 있는 약한 신호)."""
    return int(bool(_SERVICE_RE.search(str(text or ""))))


def _count_items(value, state):
    """사진·영상 개수. 영수증 사진(class가 receipt)은 세지 않는다."""
    value = deref(value, state)
    if not isinstance(value, list):
        return None
    count = 0
    for item in value:
        item = deref(item, state)
        if item is None:
            continue
        if isinstance(item, dict) and str(item.get("class") or "").lower() == "receipt":
            continue
        count += 1
    return count


def parse_review(d, state=None, today=None, salt=None):
    today = today or date.today()
    body = str(_first(d, FIELD_CANDIDATES["body"]) or "")
    created_raw = _first(d, FIELD_CANDIDATES["created"])
    visited_raw = _first(d, FIELD_CANDIDATES["visited"])

    photo_count = _count_items(_first(d, FIELD_CANDIDATES["media"]), state)
    if photo_count is None:
        photo_count = 1 if _first(d, FIELD_CANDIDATES["thumbnail"]) else 0

    names = []
    keywords = deref(_first(d, FIELD_CANDIDATES["keywords"]), state)
    if isinstance(keywords, list):
        for k in keywords:
            k = deref(k, state)
            if isinstance(k, dict):
                name = k.get("name") or k.get("displayName")
                if name:
                    names.append(str(name))
            elif isinstance(k, str) and k:
                names.append(k)

    review_count = photo_count_author = None
    reviewer_key = ""
    author = deref(_first(d, FIELD_CANDIDATES["author"]), state)
    if isinstance(author, dict):
        stats = deref(author.get("review"), state)
        if isinstance(stats, dict):
            review_count = _int(stats.get("totalCount"))
            photo_count_author = _int(stats.get("imageCount"))
        if review_count is None:
            review_count = _int(author.get("reviewCount"))
        if photo_count_author is None:
            photo_count_author = _int(_first(author, ("imageCount", "photoCount")))
        author_id = _first(author, ("id", "objectId", "idno"))
        if salt and author_id is not None:
            reviewer_key = hashlib.sha256(f"{salt}:{author_id}".encode("utf-8")).hexdigest()[:12]

    created = parse_date(created_raw, today)
    visited = parse_date(visited_raw, today)
    return {
        "review_id": str(d.get("id")),
        "created": created.isoformat() if created else "",
        "created_raw": "" if created_raw is None else str(created_raw),
        "visited": visited.isoformat() if visited else "",
        "body": body,
        "body_len": len(body),
        "photo_count": photo_count,
        "origin": str(_first(d, FIELD_CANDIDATES["origin"]) or ""),
        "visit_count": _int(_first(d, FIELD_CANDIDATES["visit_count"])),
        "rating": _int(_first(d, FIELD_CANDIDATES["rating"])),
        "keywords": "; ".join(names),
        "reviewer_review_count": review_count,
        "reviewer_photo_count": photo_count_author,
        "reviewer_key": reviewer_key,
        "event_mention": event_mention(body),
        "service_mention": service_mention(body),
    }


def _query_input(key):
    """'visitorReviews({"input":{...}})' 같은 키에서 input 부분을 꺼낸다. 인자가 없으면 {}."""
    i = key.find("(")
    if i < 0 or not key.endswith(")"):
        return {}
    try:
        args = json.loads(key[i + 1:-1])
    except ValueError:
        return {}
    value = args.get("input") if isinstance(args, dict) else None
    return value if isinstance(value, dict) else {}


def main_review_query(apollo_state):
    """Apollo 상태에서 본문이 포함된 방문자 리뷰 목록(visitorReviews)을 고른다. 없으면 None."""
    root = apollo_state.get("ROOT_QUERY") if isinstance(apollo_state, dict) else None
    if not isinstance(root, dict):
        return None
    chosen = None
    for key, value in root.items():
        if not (key == "visitorReviews" or key.startswith("visitorReviews(")):
            continue
        value = deref(value, apollo_state)
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            continue
        include = _query_input(key).get("includeContent")
        if include is False:
            continue
        if chosen is None or include is True:
            chosen = value
    return chosen


def _review_sources(apollo_state, graphql_payloads):
    main = main_review_query(apollo_state)
    if main is not None:
        sources = [main]
    elif isinstance(apollo_state, dict):
        sources = [apollo_state]
    else:
        sources = []
    return sources + list(graphql_payloads or [])


def extract_all(apollo_state, graphql_payloads, today=None, salt=None):
    """한 업체 페이지에서 모은 데이터 전체에서 리뷰를 뽑는다. 같은 리뷰 ID는 한 번만."""
    rows = {}
    for payload in _review_sources(apollo_state, graphql_payloads):
        for d in iter_reviews(payload, state=apollo_state):
            row = parse_review(d, state=apollo_state, today=today, salt=salt)
            rows.setdefault(row["review_id"], row)
    return sorted(rows.values(), key=lambda r: (r["created"], r["review_id"]), reverse=True)


# 통째로 지우는 객체 종류: 블로그·카페 리뷰(작성자 이름·블로그 주소가 들어 있음)와 블로그 주인 정보
DROP_TYPENAMES = {"FsasReview", "BaseNaverBlog"}


def _is_person_typename(typename):
    return isinstance(typename, str) and (
        typename.endswith("Author") or typename.endswith("User") or "Profile" in typename
    )


def _drop_typename(typename):
    return isinstance(typename, str) and (typename in DROP_TYPENAMES or _is_person_typename(typename))


def _dropped(value):
    """지울 종류의 객체이거나, 그런 객체를 가리키는 {"__ref": ...} 참조인지. 참조 문자열에도 이름·ID가 들어 있다."""
    if not isinstance(value, dict):
        return False
    if _drop_typename(value.get("__typename")):
        return True
    ref = value.get("__ref")
    return isinstance(ref, str) and _drop_typename(ref.split(":", 1)[0])


def scrub(obj):
    """저장 전에 닉네임·프로필·블로그 작성자 같은 개인 식별 정보를 지운다."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in PERSONAL_KEYS:
                continue
            if isinstance(k, str) and _drop_typename(k.split(":", 1)[0]):
                continue
            if _dropped(v):
                continue
            out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(v) for v in obj if not _dropped(v)]
    return obj


def first_review(apollo_state, graphql_payloads):
    """probe 출력용: 처음 찾은 리뷰 객체. 없으면 None."""
    for payload in _review_sources(apollo_state, graphql_payloads):
        for d in iter_reviews(payload, state=apollo_state):
            return d
    return None


def place_info(apollo_state):
    """업체 단위 정보: 네이버 업체명·업종·도로명 주소·방문자 리뷰 수·쿠폰 수. 없는 값은 빈칸/None."""
    info = {"place_title": "", "place_category": "", "road_address": "", "review_total": None, "coupon_count": None}
    if not isinstance(apollo_state, dict):
        return info
    root = apollo_state.get("ROOT_QUERY") if isinstance(apollo_state.get("ROOT_QUERY"), dict) else {}
    detail = next((deref(v, apollo_state) for k, v in root.items() if k.startswith("placeDetail")), None)
    base = None
    if isinstance(detail, dict):
        base = deref(detail.get("base"), apollo_state)
        coupon = deref(detail.get("hasCoupon"), apollo_state)
        if isinstance(coupon, dict):
            info["coupon_count"] = _int(coupon.get("count"))
    if not isinstance(base, dict) or not base:
        base = next((v for k, v in apollo_state.items()
                     if isinstance(k, str) and k.startswith("PlaceDetailBase:") and isinstance(v, dict)), None)
    if isinstance(base, dict):
        info["place_title"] = str(base.get("name") or "")
        info["place_category"] = str(base.get("category") or "")
        info["road_address"] = str(base.get("roadAddress") or base.get("address") or "")
        info["review_total"] = _int(base.get("visitorReviewsTotal"))
    if info["review_total"] is None:
        main = main_review_query(apollo_state)
        if main is not None:
            info["review_total"] = _int(main.get("total"))
    return info


def first_review_keys(apollo_state, graphql_payloads):
    """probe 출력용: 처음 찾은 리뷰 객체의 키 목록."""
    d = first_review(apollo_state, graphql_payloads)
    return sorted(d.keys()) if d is not None else []


def body_like_typenames(apollo_state, graphql_payloads, top=10):
    """probe 진단용: 본문 후보 필드(body 등)를 가진 객체의 __typename 빈도. 리뷰를 못 찾았을 때 단서가 된다."""
    counter = Counter()
    stack = ([apollo_state] if isinstance(apollo_state, dict) else []) + list(graphql_payloads or [])
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if any(k in cur for k in FIELD_CANDIDATES["body"]):
                counter[str(cur.get("__typename"))] += 1
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return counter.most_common(top)
