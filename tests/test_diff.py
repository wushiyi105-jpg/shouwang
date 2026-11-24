import unittest

from shouwang.diff import diff, fingerprint, lines, summarize

OLD = """青梧降噪耳机 Pro
价格：¥499
库存：12 件
配送：48 小时内发货"""
NEW = """青梧降噪耳机 Pro
价格：¥399
库存：3 件
配送：72 小时内发货"""


class TestDiff(unittest.TestCase):
    def test_detects_changes(self):
        d = diff(OLD, NEW)
        self.assertTrue(d["changed"])
        self.assertIn("价格：¥399", d["added"])
        self.assertIn("价格：¥499", d["removed"])
        self.assertEqual(d["added_count"], 3)
        self.assertEqual(d["removed_count"], 3)

    def test_no_change(self):
        d = diff(OLD, OLD)
        self.assertFalse(d["changed"])
        self.assertEqual(d["added"], [])

    def test_short_lines_ignored(self):
        d = diff("首页\n价格 499", "首页\n价格 399")
        self.assertEqual(len(d["added"]), 1)

    def test_whitespace_does_not_count(self):
        self.assertEqual(fingerprint("价格：499"), fingerprint("  价格：499  "))
        self.assertEqual(diff("价格：499", "价格：  499")["changed"], False)

    def test_fingerprint_stable_and_different(self):
        self.assertEqual(fingerprint(OLD), fingerprint(OLD))
        self.assertNotEqual(fingerprint(OLD), fingerprint(NEW))

    def test_report_is_capped(self):
        old = "\n".join(f"第{i}行原来的内容" for i in range(40))
        new = "\n".join(f"第{i}行新的内容" for i in range(40))
        d = diff(old, new)
        self.assertLessEqual(len(d["added"]), 15)
        self.assertLessEqual(len(d["removed"]), 15)

    def test_lines_filter(self):
        self.assertEqual(lines("a\n\n很长的一行文字内容"), ["很长的一行文字内容"])

    def test_summary_marks_plus_minus(self):
        s = summarize(diff(OLD, NEW))
        self.assertIn("+ 价格：¥399", s)
        self.assertIn("- 价格：¥499", s)


if __name__ == "__main__":
    unittest.main()
