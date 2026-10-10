"""실제 네이버 모바일 리뷰 페이지(2026-10-09 확인)의 데이터 구조를 그대로 본뜬 테스트 데이터.

키 이름·참조 방식·두 가지 visitorReviews 목록은 실제와 같고, 값은 모두 가짜다.
"""

import json

PLACE_ID = "2000000001"
NICKNAMES = ("가짜닉네임하나", "가짜닉네임둘", "가짜닉네임셋")
_MAIN_INPUT = {"bookingBusinessId": "1000001", "businessId": PLACE_ID, "businessType": "restaurant",
               "cidList": ["220036", "220037"], "getReactions": True, "getTrailer": True, "getUserStats": True,
               "includeContent": True, "includeReceiptPhotos": True, "isPhotoUsed": False, "item": "0",
               "size": 10, "sort": "recent"}
_OTHER_INPUT = dict(_MAIN_INPUT, includeContent=False)
_OTHER_INPUT.pop("isPhotoUsed")


def _key(name, payload):
    return f"{name}({json.dumps({'input': payload}, ensure_ascii=False, separators=(',', ':'))})"


def _author(i, total, images):
    return {"__typename": "VisitorReviewAuthor", "id": f"fake{i}", "nickname": NICKNAMES[i - 1], "from": "fake",
            "imageUrl": None, "borderImageUrl": "https://example.invalid/border.png", "objectId": f"obj{i:024d}",
            "url": f"https://m.place.naver.com/my/obj{i}/review", "review": {"__typename": "AuthorReview",
            "totalCount": total, "imageCount": images, "avgRating": 4.5}, "theme": {"__typename": "AuthorTheme",
            "totalCount": 0}, "isFollowing": None, "followerCount": "0", "followRequested": None}


def _media(kind="image", cls="notReceipt"):
    return {"__typename": "VisitorReviewMedia", "type": kind, "thumbnail": "https://example.invalid/t.jpg",
            "thumbnailRatio": "square", "class": cls, "videoId": None, "videoUrl": None, "trailerUrl": None}


def _review(rid, author_key, body, created, visited, origin, visit_count, media, keywords, rating=5):
    return {
        "__typename": "VisitorReview", "id": rid, "cursor": rid, "reviewId": rid, "rating": rating,
        "author": {"__ref": author_key}, "body": body, "thumbnail": "https://example.invalid/t.jpg",
        "media": media, "tags": None, "status": "ACTIVE", "visitCount": visit_count, "viewCount": 3,
        "visited": visited, "created": created,
        "reply": {"__typename": "VisitorReviewReply", "editUrl": "https://example.invalid/edit", "body": None,
                  "editedBy": None, "created": None, "date": None, "replyTitle": None, "isReported": False,
                  "isSuspended": False, "status": None},
        "originType": origin, "item": None, "language": "ko", "highlightRanges": None,
        "apolloCacheId": rid, "translatedText": None, "businessName": "가짜식당", "showBookingItemName": False,
        "bookingItemName": "", "votedKeywords": [{"__typename": "VisitorReviewVotedKeyword", "code": f"k{i}",
                                                   "iconUrl": "https://example.invalid/i.png", "iconCode": "x",
                                                   "name": k} for i, k in enumerate(keywords)],
        "userIdno": "123456789", "loginIdno": "987654321", "receiptInfoUrl": "https://example.invalid/receipt",
        "reactionStat": {"__ref": f"ReactionStat:{rid}"}, "hasViewerReacted": {"__ref": f"HasViewerReacted:{rid}"},
        "nickname": "가짜닉네임하나", "showPaymentInfo": False,
        "visitCategories": [{"__typename": "VisitCategory", "code": "v_with_reservation", "name": "",
                             "keywords": [{"__typename": "VisitCategoryKeyword", "code": "예약 없이 이용",
                                           "name": "예약 없이 이용"}]}],
        "representativeVisitDateTime": "2026-10-07T11:05:57.000Z", "showRepresentativeVisitDateTime": False,
    }


def apollo_state():
    a1, a2, a3 = "VisitorReviewAuthor:fake1", "VisitorReviewAuthor:fake2", "VisitorReviewAuthor:fake3"
    main_items = ["VisitorReview:aaa111:true", "VisitorReview:bbb222:true"]
    state = {
        "ROOT_QUERY": {
            "__typename": "Query",
            _key("placeDetail", {"deviceType": "mobile", "id": PLACE_ID, "isNx": False}): {
                "__typename": "PlaceDetail", "base": {"__ref": f"PlaceDetailBase:{PLACE_ID}"},
                "hasCoupon": {"__typename": "HasCoupon", "count": 2},
                "tabs": [{"__typename": "PlaceDetailTab", "tabId": "home", "name": "홈", "externalUrl": None}],
                "fsasReviews": {"__typename": "FsasReviewsResult", "total": 1,
                                "items": [{"__ref": "FsasReview:blog_가짜블로거_1234_가짜 후기"}]},
            },
            _key("visitorReviews", _MAIN_INPUT): {
                "__typename": "VisitorReviewsResult", "items": [{"__ref": k} for k in main_items],
                "starDistribution": None, "hideProductSelectBox": True, "total": 1161,
                "showRecommendationSort": False, "itemReviewStats": None,
            },
            _key("visitorReviews", _OTHER_INPUT): {
                "__typename": "VisitorReviewsResult", "total": 17, "items": [{"__ref": "VisitorReview:ccc333"}],
            },
            _key("reviewAwardCoupons", {"businessId": PLACE_ID}): {"__typename": "ReviewAwardsCouponsResult",
                                                                    "total": 0},
        },
        f"PlaceDetailBase:{PLACE_ID}": {"__typename": "PlaceDetailBase", "id": PLACE_ID, "name": "가짜식당 종각점",
                                        "category": "육류,고기요리", "roadAddress": "서울 종로구 가짜로 1 1층",
                                        "visitorReviewsTotal": 1178, "visitorReviewsScore": 4.89},
        main_items[0]: _review("aaa111", a1, "리뷰 이벤트 참여하고 음료 받았어요. 고기 맛있어요", "10.8.목", "10.7.수", "영수증",
                               1, [_media(), _media(), _media(cls="receipt")], ["음식이 맛있어요", "친절해요"]),
        main_items[1]: _review("bbb222", a2, "", "25.12.10.수", "25.12.9.화", "결제내역", 2,
                               [_media("video", None)], [], rating=4),
        "VisitorReview:ccc333": {  # includeContent:false 목록의 리뷰: 본문·작성일이 없다
            "__typename": "VisitorReview", "id": "ccc333", "author": {"__ref": a3}, "businessName": "가짜식당",
            "cursor": "ccc333", "visited": "10.1.목", "originType": "예약", "rating": 5, "visitCount": 1,
            "votedKeywords": [], "nickname": NICKNAMES[2], "userIdno": "1", "loginIdno": "2",
            "receiptInfoUrl": "https://example.invalid/r", "status": "ACTIVE", "reply": None,
            "reactionStat": None, "hasViewerReacted": None,
        },
        "FsasReview:blog_가짜블로거_1234_가짜 후기": {  # 블로그 리뷰: 작성자 이름·블로그 주소가 들어 있다
            "__typename": "FsasReview", "name": "가짜블로거", "type": "blog", "typeName": "블로그",
            "url": "https://m.blog.naver.com/fakeblogger/1234", "home": "https://m.blog.naver.com/fakeblogger",
            "authorName": "가짜블로거", "title": "가짜 후기", "contents": "가짜 블로그 내용",
        },
        f"PlaceDetailTopPhotoItem:{PLACE_ID}_visitor_1": {
            "__typename": "PlaceDetailTopPhotoItem", "id": f"{PLACE_ID}_visitor_1", "title": "메뉴판",
            "linkUrl": "https://blog.naver.com/fakeblogger2/5678", "date": "2026.10.01",
        },
        "BaseNaverBlog:fakeownerblog": {"__typename": "BaseNaverBlog", "id": "fakeownerblog", "categoryNo": "1"},
        a1: _author(1, 15, 13),
        a2: _author(2, 0, 0),
        a3: _author(3, 7, 1),
    }
    return state


def page_html(state=None):
    """실제 페이지처럼 Apollo 상태 뒤에 다른 스크립트가 이어지는 HTML."""
    state = apollo_state() if state is None else state
    return ("<!DOCTYPE html><html lang=\"ko\"><head><title>네이버 플레이스</title></head><body><div id=\"app\">로딩중</div>"
            "<script>window.__APOLLO_STATE__ = " + json.dumps(state, ensure_ascii=False)
            + ";\nwindow.__PLACE_STATE__ = {\"x\": 1};</script></body></html>")


CAPTCHA_HTML = ('<!doctype html><html><head title="captcha"><meta charset="UTF-8"/></head><body><div id="app"></div>'
                "<script>window.addEventListener('load', function () { WtmCaptcha.renderCaptcha(); });</script>"
                "</body></html>")


def search_payload(title=None, place_id=PLACE_ID):
    """네이버지도 자동완성 검색 응답(instant-search)의 실제 모양."""
    title = title or "가짜식당 종각점"
    return {"meta": {"model": "2.3.0", "query": title, "requestId": "x"}, "ac": [], "bookingKeyword": [],
            "place": [{"id": "1999999999", "title": "가짜식당 종각2호점", "ctg": "한식", "roadAddress": "서울 어딘가",
                       "review": {"count": "10"}, "type": "place"},
                      {"id": place_id, "title": title, "x": "126.98", "y": "37.56", "ctg": "육류,고기요리",
                       "jibunAddress": "서울 종로구 가짜동 1", "roadAddress": "서울특별시 종로구 가짜로 1 1층",
                       "review": {"count": "1178"}, "hasBooking": True, "type": "place"}],
            "address": [], "bus": [], "menu": [], "all": []}
