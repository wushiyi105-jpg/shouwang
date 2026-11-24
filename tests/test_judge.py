import unittest
from unittest import mock

from shouwang.diff import diff
from shouwang.judge import judge

OLD = "价格：¥499\n库存：12 件"
NEW = "价格：¥399\n库存：3 件"


class TestJudge(unittest.TestCase):
    def test_important_verdict(self):
        payload = '{"important": true, "level": "high", "title": "降价 20%", "reason": "价格从 499 降到 399", "advice": "可以下手"}'
        with mock.patch("shouwang.llm.chat", return_value=payload):
            v = judge("价格", OLD, NEW, diff(OLD, NEW))
        self.assertTrue(v["important"])
        self.assertEqual(v["level"], "high")
        self.assertEqual(v["title"], "降价 20%")
        self.assertEqual(v["advice"], "可以下手")
        self.assertFalse(v["error"])

    def test_not_important(self):
        payload = '{"important": false, "level": "low", "title": "排版调整", "reason": "只是推荐位换了个顺序"}'
        with mock.patch("shouwang.llm.chat", return_value=payload):
            v = judge("价格", OLD, NEW, diff(OLD, NEW))
        self.assertFalse(v["important"])
        self.assertEqual(v["advice"], "")

    def test_bad_json_falls_back(self):
        with mock.patch("shouwang.llm.chat", return_value="我觉得不太重要"):
            v = judge("价格", OLD, NEW, diff(OLD, NEW))
        self.assertFalse(v["important"])
        self.assertTrue(v["error"])

    def test_invalid_level_becomes_low(self):
        payload = '{"important": true, "level": "URGENT", "title": "x", "reason": "y"}'
        with mock.patch("shouwang.llm.chat", return_value=payload):
            v = judge("价格", OLD, NEW, diff(OLD, NEW))
        self.assertEqual(v["level"], "low")

    def test_list_payload_accepted(self):
        payload = '[{"important": true, "level": "medium", "title": "库存紧张", "reason": "库存从 12 掉到 3"}]'
        with mock.patch("shouwang.llm.chat", return_value=payload):
            v = judge("库存", OLD, NEW, diff(OLD, NEW))
        self.assertTrue(v["important"])
        self.assertEqual(v["title"], "库存紧张")

    def test_prompt_contains_focus_and_changes(self):
        with mock.patch("shouwang.llm.chat", return_value='{"important": false}') as m:
            judge("库存", OLD, NEW, diff(OLD, NEW))
        user_msg = m.call_args[0][0][1]["content"]
        self.assertIn("库存", user_msg)
        self.assertIn("价格：¥399", user_msg)


if __name__ == "__main__":
    unittest.main()
