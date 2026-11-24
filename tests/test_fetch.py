import os
import tempfile
import unittest

from shouwang.fetch import FetchError, extract_text, fetch


class TestExtract(unittest.TestCase):
    def test_drops_script_and_style(self):
        html = """<html><head><style>.x{color:red}</style>
        <script>var a=1;</script></head>
        <body><h1>标题</h1><p>正文一段</p></body></html>"""
        text = extract_text(html)
        self.assertIn("标题", text)
        self.assertIn("正文一段", text)
        self.assertNotIn("var a=1", text)
        self.assertNotIn("color:red", text)

    def test_block_tags_become_lines(self):
        text = extract_text("<p>第一行</p><p>第二行</p>")
        self.assertEqual(text.split("\n"), ["第一行", "第二行"])

    def test_empty_html(self):
        self.assertEqual(extract_text("<html><body></body></html>"), "")


class TestFetchLocal(unittest.TestCase):
    def test_local_path(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write("<p>价格：499</p>")
            path = f.name
        try:
            snap = fetch(path)
            self.assertEqual(snap["status"], 200)
            self.assertIn("499", snap["text"])
            self.assertIn("fetched_at", snap)
            self.assertGreaterEqual(snap["elapsed_ms"], 0)
        finally:
            os.unlink(path)

    def test_file_url(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("纯文本内容")
            path = f.name
        try:
            snap = fetch("file://" + path.replace("\\", "/"))
            self.assertEqual(snap["text"].strip(), "纯文本内容")
        finally:
            os.unlink(path)

    def test_missing_file(self):
        with self.assertRaises(FetchError):
            fetch("不存在.html")

    def test_bad_scheme(self):
        with self.assertRaises(FetchError):
            fetch("ftp://example.com/a")

    def test_empty_page(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write("<script>only script</script>")
            path = f.name
        try:
            with self.assertRaises(FetchError):
                fetch(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
