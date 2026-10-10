import unittest

from naver_reviews.ids import extract_place_id, is_short_link, name_from_share_text, resolve_place_id


class PlaceIdTests(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(extract_place_id(" 1234567890 "), "1234567890")

    def test_mobile_place_urls(self):
        self.assertEqual(extract_place_id("https://m.place.naver.com/restaurant/1234567/home"), "1234567")
        self.assertEqual(extract_place_id("https://m.place.naver.com/place/9876543/review/visitor"), "9876543")

    def test_map_entry_url(self):
        url = "https://map.naver.com/p/entry/place/1122334455?c=15.00,0,0,0,dh"
        self.assertEqual(extract_place_id(url), "1122334455")

    def test_not_a_place(self):
        self.assertIsNone(extract_place_id("가짜식당 종각점"))
        self.assertIsNone(extract_place_id(""))
        self.assertIsNone(extract_place_id(None))
        self.assertIsNone(extract_place_id("123"))

    def test_share_text_with_short_link(self):
        share = "[네이버지도]\n가짜식당 종각점\n서울 종로구 어딘가\nhttps://naver.me/AbCdEf12"
        calls = []

        def fake_follow(url, timeout):
            calls.append(url)
            return "https://map.naver.com/p/entry/place/5555555?c=1"

        self.assertEqual(resolve_place_id(share, follow=fake_follow), "5555555")
        self.assertEqual(calls, ["https://naver.me/AbCdEf12"])

    def test_short_link_failure_returns_none(self):
        def broken(url, timeout):
            raise OSError("network down")

        self.assertIsNone(resolve_place_id("https://naver.me/zzz", follow=broken))

    def test_direct_url_does_not_need_network(self):
        def must_not_call(url, timeout):
            raise AssertionError("should not follow")

        text = "가게 링크 https://m.place.naver.com/restaurant/7654321/home 입니다"
        self.assertEqual(resolve_place_id(text, follow=must_not_call), "7654321")

    def test_only_short_links_are_followed(self):
        def must_not_call(url, timeout):
            raise AssertionError("should not follow")

        self.assertIsNone(resolve_place_id("https://example.com/abc", follow=must_not_call))
        self.assertIsNone(resolve_place_id("https://notnaver.me.example.com/x", follow=must_not_call))
        self.assertTrue(is_short_link("https://naver.me/AbCdEf12"))
        self.assertFalse(is_short_link("https://m.place.naver.com/restaurant/1/home"))

    def test_name_from_share_text(self):
        share = "[네이버지도]\n가짜식당 종각점\n서울 종로구 어딘가\nhttps://naver.me/AbCdEf12"
        self.assertEqual(name_from_share_text(share), "가짜식당 종각점")
        self.assertEqual(name_from_share_text("[네이버지도] 가짜순대국 종각직영점\nhttps://naver.me/x"),
                         "가짜순대국 종각직영점")
        self.assertEqual(name_from_share_text("[네이버지도]\nhttps://naver.me/x"), "")
        self.assertEqual(name_from_share_text("https://naver.me/AbCdEf12"), "")
        self.assertEqual(name_from_share_text(None), "")


if __name__ == "__main__":
    unittest.main()
