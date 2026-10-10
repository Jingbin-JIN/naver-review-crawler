"""실제 네이버 페이지 구조(2026-10-09 확인)를 본뜬 데이터로 하는 회귀 테스트. 브라우저가 필요 없다."""

import json
import unittest
from datetime import date

from naver_reviews import extract, places, web
from tests import fixtures_real as fr

TODAY = date(2026, 10, 9)


class RealStructureTests(unittest.TestCase):
    def setUp(self):
        self.state = fr.apollo_state()

    def test_only_main_review_list_is_used(self):
        rows = extract.extract_all(self.state, [], today=TODAY)
        self.assertEqual([r["review_id"] for r in rows], ["aaa111", "bbb222"])  # includeContent:false 목록 제외

    def test_review_fields(self):
        rows = {r["review_id"]: r for r in extract.extract_all(self.state, [], today=TODAY)}
        a, b = rows["aaa111"], rows["bbb222"]
        self.assertEqual((a["created"], a["visited"], a["created_raw"]), ("2026-10-08", "2026-10-07", "10.8.목"))
        self.assertEqual((a["origin"], a["visit_count"], a["rating"]), ("영수증", 1, 5))
        self.assertEqual(a["photo_count"], 2)  # 영수증 사진은 세지 않는다
        self.assertEqual(a["keywords"], "음식이 맛있어요; 친절해요")
        self.assertEqual((a["reviewer_review_count"], a["reviewer_photo_count"]), (15, 13))  # 작성자 참조를 따라감
        self.assertEqual(a["event_mention"], 1)
        self.assertEqual((b["created"], b["visited"]), ("2025-12-10", "2025-12-09"))  # 연도가 붙은 표기
        self.assertEqual((b["photo_count"], b["rating"], b["body_len"]), (1, 4, 0))
        self.assertEqual((b["reviewer_review_count"], b["reviewer_photo_count"]), (0, 0))

    def test_place_info(self):
        info = extract.place_info(self.state)
        self.assertEqual(info, {"place_title": "가짜식당 종각점", "place_category": "육류,고기요리",
                                "road_address": "서울 종로구 가짜로 1 1층", "review_total": 1178, "coupon_count": 2})
        self.assertEqual(extract.place_info(None)["coupon_count"], None)

    def test_scrub_removes_people_and_ids(self):
        cleaned = json.dumps(extract.scrub(self.state), ensure_ascii=False)
        for nick in fr.NICKNAMES:
            self.assertNotIn(nick, cleaned)
        for secret in ("123456789", "987654321", "example.invalid/receipt", "border.png", "VisitorReviewAuthor",
                       "fakeblogger", "가짜블로거", "fakeownerblog", "FsasReview:"):
            self.assertNotIn(secret, cleaned)
        self.assertIn("고기 맛있어요", cleaned)  # 리뷰 본문은 남는다
        self.assertIn("메뉴판", cleaned)  # 사진 항목은 남고 블로그 주소만 빠진다

    def test_parsed_rows_have_no_personal_data(self):
        dumped = json.dumps(extract.extract_all(self.state, [], today=TODAY), ensure_ascii=False)
        for nick in fr.NICKNAMES:
            self.assertNotIn(nick, dumped)
        self.assertNotIn("123456789", dumped)

    def test_parse_apollo_and_captcha(self):
        self.assertEqual(web.parse_apollo(fr.page_html(self.state)), self.state)
        self.assertIsNone(web.parse_apollo("<html>데이터 없음</html>"))
        self.assertIsNone(web.parse_apollo("window.__APOLLO_STATE__ = {깨진"))
        self.assertTrue(web.is_captcha(fr.CAPTCHA_HTML))
        self.assertFalse(web.is_captcha(fr.page_html(self.state)))

    def test_pick_candidate_exact_only(self):
        cands = [{"id": "1", "title": "가짜식당 종각2호점"}, {"id": "2", "title": "가짜식당 종각점"}]
        self.assertEqual(web.pick_candidate("가짜식당  종각점", cands)["id"], "2")  # 띄어쓰기 무시
        self.assertEqual(web.pick_candidate("가짜식당종각점", cands)["id"], "2")
        self.assertIsNone(web.pick_candidate("가짜식당", cands))  # 비슷한 이름은 고르지 않는다
        self.assertIsNone(web.pick_candidate("", cands))

    def test_region_codes(self):
        self.assertEqual(places.region_coords(4.0), places.REGION_COORDS["4"])
        self.assertEqual(places.region_coords("３"), places.REGION_COORDS["3"])  # 전각 숫자
        self.assertIsNone(places.region_coords("강서"))
        self.assertEqual(places.region_coords("", "기본"), "기본")


if __name__ == "__main__":
    unittest.main()
