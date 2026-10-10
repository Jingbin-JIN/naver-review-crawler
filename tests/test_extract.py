import json
import unittest
from datetime import date

from naver_reviews import extract
from tests import fixtures

TODAY = date(2026, 10, 9)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.state = fixtures.apollo_state()
        self.gql = [fixtures.graphql_payload()]

    def test_finds_reviews_from_both_sources_once(self):
        rows = extract.extract_all(self.state, self.gql + self.gql, today=TODAY)
        self.assertEqual([r["review_id"] for r in rows], ["r1", "r2", "r3"])

    def test_fields(self):
        rows = {r["review_id"]: r for r in extract.extract_all(self.state, self.gql, today=TODAY)}
        r1, r2, r3 = rows["r1"], rows["r2"], rows["r3"]
        self.assertEqual(r1["created"], "2026-10-08")
        self.assertEqual(r1["visited"], "2026-10-07")
        self.assertEqual(r1["photo_count"], 2)
        self.assertEqual(r1["origin"], "영수증")
        self.assertEqual(r1["visit_count"], 1)
        self.assertEqual(r1["keywords"], "음식이 맛있어요; 친절해요")
        self.assertEqual((r1["reviewer_review_count"], r1["reviewer_photo_count"]), (12, 5))
        self.assertEqual((r2["reviewer_review_count"], r2["reviewer_photo_count"]), (0, 0))
        self.assertEqual(r2["photo_count"], 0)
        self.assertEqual(r3["created"], "2026-10-06")
        self.assertEqual(r3["visited"], "2026-10-05")
        self.assertEqual(r3["photo_count"], 1)
        self.assertEqual(r3["origin"], "예약")
        self.assertEqual(r3["reviewer_review_count"], 40)

    def test_event_and_service_flags(self):
        rows = {r["review_id"]: r for r in extract.extract_all(self.state, self.gql, today=TODAY)}
        self.assertEqual((rows["r1"]["event_mention"], rows["r1"]["service_mention"]), (1, 0))
        self.assertEqual((rows["r2"]["event_mention"], rows["r2"]["service_mention"]), (0, 1))
        self.assertEqual((rows["r3"]["event_mention"], rows["r3"]["service_mention"]), (1, 0))

    def test_event_patterns(self):
        positives = ["리뷰이벤트 참여했어요", "영수증 리뷰 쿠폰 써서 할인", "리뷰 작성 시 음료 서비스 주셔서 좋았어요",
                     "리뷰 쓰면 음료수 준대요", "리뷰를 남기면 계란찜 드려요"]
        negatives = ["리뷰 보고 찾아왔어요", "리뷰 쓰고 싶었던 곳이에요", "직원분들이 친절하고 서비스가 좋아요", ""]
        for t in positives:
            self.assertEqual(extract.event_mention(t), 1, t)
        for t in negatives:
            self.assertEqual(extract.event_mention(t), 0, t)

    def test_no_personal_data_in_parsed_rows(self):
        rows = extract.extract_all(self.state, self.gql, today=TODAY)
        dumped = json.dumps(rows, ensure_ascii=False)
        for nick in fixtures.NICKNAMES:
            self.assertNotIn(nick, dumped)
        self.assertTrue(all(r["reviewer_key"] == "" for r in rows))

    def test_reviewer_key_only_with_salt(self):
        rows = {r["review_id"]: r for r in extract.extract_all(self.state, self.gql, today=TODAY, salt="s3cret")}
        self.assertEqual(len(rows["r1"]["reviewer_key"]), 12)
        self.assertNotEqual(rows["r1"]["reviewer_key"], rows["r2"]["reviewer_key"])
        again = {r["review_id"]: r for r in extract.extract_all(self.state, self.gql, today=TODAY, salt="s3cret")}
        self.assertEqual(rows["r1"]["reviewer_key"], again["r1"]["reviewer_key"])

    def test_scrub_removes_people(self):
        cleaned = json.dumps(extract.scrub({"state": self.state, "gql": self.gql}), ensure_ascii=False)
        for nick in fixtures.NICKNAMES:
            self.assertNotIn(nick, cleaned)
        self.assertNotIn("example.invalid", cleaned)
        self.assertIn("고기가 정말 맛있어요", cleaned)  # 리뷰 본문은 남는다

    def test_parse_date(self):
        self.assertEqual(extract.parse_date("10.8.목", TODAY), date(2026, 10, 8))
        self.assertEqual(extract.parse_date("2025.10.8.수", TODAY), date(2025, 10, 8))
        self.assertEqual(extract.parse_date("24.3.1", TODAY), date(2024, 3, 1))
        self.assertEqual(extract.parse_date("2026-10-07T12:00:00+09:00", TODAY), date(2026, 10, 7))
        self.assertEqual(extract.parse_date("12.30.화", date(2026, 1, 3)), date(2025, 12, 30))
        self.assertIsNone(extract.parse_date("2.30.월", TODAY))
        self.assertIsNone(extract.parse_date("", TODAY))
        self.assertIsNone(extract.parse_date("어제", TODAY))

    def test_unknown_structure_returns_nothing(self):
        self.assertEqual(extract.extract_all({"ROOT_QUERY": {"x": 1}}, [{"data": {}}], today=TODAY), [])
        self.assertEqual(extract.extract_all(None, [], today=TODAY), [])

    def test_first_review_keys(self):
        keys = extract.first_review_keys(self.state, self.gql)
        self.assertIn("body", keys)
        self.assertIn("created", keys)


if __name__ == "__main__":
    unittest.main()
