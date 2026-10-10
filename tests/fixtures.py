"""테스트용 가짜 데이터. 네이버 응답 구조를 흉내 냈을 뿐 실제 데이터가 아니다."""

import json

NICKNAMES = ("홍길동", "이영희", "김철수")


def apollo_state():
    return {
        "ROOT_QUERY": {
            "__typename": "Query",
            "visitorReviews": {"items": [{"__ref": "VisitorReview:r1"}, {"__ref": "VisitorReview:r2"}], "total": 3},
        },
        "VisitorReview:r1": {
            "__typename": "VisitorReview", "id": "r1",
            "body": "리뷰 이벤트로 음료 받았어요. 고기가 정말 맛있어요!",
            "created": "10.8.목", "visited": "10.7.수", "originType": "영수증", "visitCount": 1,
            "media": [{"__ref": "Media:m1"}, {"__ref": "Media:m2"}],
            "author": {"__ref": "VisitorReviewAuthor:a1"},
            "votedKeywords": [{"__typename": "VotedKeyword", "code": "food", "name": "음식이 맛있어요"},
                              {"__typename": "VotedKeyword", "code": "kind", "name": "친절해요"}],
        },
        "VisitorReview:r2": {
            "__typename": "VisitorReview", "id": "r2",
            "body": "=점심으로 들렀는데 서비스로 계란찜 주셨어요",
            "created": "10.7.수", "visited": "10.7.수", "originType": "영수증", "visitCount": 3,
            "media": [], "author": {"__ref": "VisitorReviewAuthor:a2"}, "votedKeywords": [],
        },
        "Media:m1": {"__typename": "Media", "type": "image", "thumbnail": "x1"},
        "Media:m2": {"__typename": "Media", "type": "image", "thumbnail": "x2"},
        "VisitorReviewAuthor:a1": {"__typename": "VisitorReviewAuthor", "id": "a1", "nickname": NICKNAMES[0],
                                   "imageUrl": "https://example.invalid/a1.png",
                                   "review": {"totalCount": 12, "imageCount": 5}},
        "VisitorReviewAuthor:a2": {"__typename": "VisitorReviewAuthor", "id": "a2", "nickname": NICKNAMES[1],
                                   "review": {"totalCount": 0, "imageCount": 0}},
    }


def graphql_payload():
    return {"data": {"visitorReviews": {"total": 3, "items": [{
        "__typename": "VisitorReview", "id": "r3",
        "body": "리뷰 쓰고 사이다 받았습니다. 재방문 의사 있어요",
        "created": "10.6.화", "visited": "10.5.월", "originType": "예약", "visitCount": 2,
        "media": [{"__typename": "Media", "type": "image"}],
        "author": {"__typename": "VisitorReviewAuthor", "id": "a3", "nickname": NICKNAMES[2],
                   "review": {"totalCount": 40, "imageCount": 22}},
        "votedKeywords": [{"__typename": "VotedKeyword", "name": "가성비가 좋아요"}],
    }]}}}


def review_page_html():
    """네이버 모바일 리뷰 페이지처럼 Apollo 상태를 품고, '펼쳐서 더보기'를 누르면 /graphql을 부르는 페이지."""
    state = json.dumps(apollo_state(), ensure_ascii=False)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>test</title></head>
<body>
<ul id="list"><li>첫 리뷰 본문 <a href="#" class="expand">더보기</a></li><li>두 번째 리뷰</li></ul>
<a href="#" id="pager">펼쳐서 더보기</a>
<script>
window.__APOLLO_STATE__ = {state};
document.querySelectorAll('.expand').forEach(function (a) {{
  a.addEventListener('click', function (e) {{ e.preventDefault(); a.textContent = '접기'; }});
}});
document.getElementById('pager').addEventListener('click', async function (e) {{
  e.preventDefault();
  const r = await fetch('/graphql', {{method: 'POST', headers: {{'content-type': 'application/json'}},
                                     body: JSON.stringify({{operationName: 'getVisitorReviews'}})}});
  const j = await r.json();
  for (const it of j.data.visitorReviews.items) {{
    const li = document.createElement('li'); li.textContent = it.body;
    document.getElementById('list').appendChild(li);
  }}
  document.getElementById('pager').remove();
}});
</script>
</body></html>"""
