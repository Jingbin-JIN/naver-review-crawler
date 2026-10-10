"""브라우저 없이 확인할 수 있는 명령어 처리(입력 오류 안내 등)."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

import crawl


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = crawl.main(argv)
        except SystemExit as e:  # argparse 오류
            code = e.code
    return code, buf.getvalue()


class CliTests(unittest.TestCase):
    def test_run_needs_input_or_place(self):
        code, _ = _run(["run"])
        self.assertEqual(code, 2)

    def test_run_rejects_input_and_place_together(self):
        code, _ = _run(["run", "--input", "a.xlsx", "--place", "1234567"])
        self.assertEqual(code, 2)

    def test_missing_input_file_message(self):
        code, out = _run(["run", "--input", "/nonexistent/team.xlsx"])
        self.assertEqual(code, 2)
        self.assertIn("입력 파일을 찾지 못했습니다", out)

    def test_unknown_sheet_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            wb = Workbook()
            wb.active.title = "팀원A"
            wb.active.append(["업체명", "플레이스 링크"])
            path = Path(tmp) / "team.xlsx"
            wb.save(path)
            code, out = _run(["run", "--input", str(path), "--sheet", "팀원A2"])
        self.assertEqual(code, 2)
        self.assertIn("'팀원A2' 시트가 없습니다", out)
        self.assertIn("팀원A", out)

    def test_delay_validation(self):
        code, out = _run(["run", "--place", "1234567", "--delay-min", "5", "--delay-max", "1"])
        self.assertEqual(code, 2)
        self.assertIn("--delay-max", out)

    def test_shape_hides_values(self):
        state = {"A:1": {"__typename": "VisitorReviewAuthor", "nickname": "홍길동", "review": {"totalCount": 3}}}
        review = {"id": "r1", "body": "맛있어요", "author": {"__ref": "A:1"}, "media": [{"type": "image"}]}
        shape = crawl._shape(review, state, 3)
        self.assertEqual(shape["body"], "str")
        self.assertEqual(shape["author"]["nickname"], "str")
        self.assertEqual(shape["author"]["review"], {"totalCount": "int"})
        self.assertEqual(shape["media"], [{"type": "str"}, "1개"])
        self.assertNotIn("홍길동", str(shape))
        self.assertNotIn("맛있어요", str(shape))


if __name__ == "__main__":
    unittest.main()
