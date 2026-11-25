import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from shouwang import store
from shouwang.web import make_server

HTML_A = "<p>价格：¥499</p><p>库存：12 件</p>"


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.conn = store.connect(os.path.join(cls.tmp.name, "w.db"))
        cls.httpd = make_server(cls.conn, port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.conn.close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, obj):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_page(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode("utf-8")
        self.assertIn("守望", html)
        self.assertIn("/api/check", html)

    def test_add_and_list(self):
        self.post("/api/add", {"name": "耳机", "url": "x", "focus": "价格", "interval": 15})
        ws = self.get("/api/watches")["watches"]
        self.assertEqual(ws[0]["name"], "耳机")

    def test_check_flow_with_local_page(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "a.html")
            with open(p1, "w", encoding="utf-8") as f:
                f.write(HTML_A)
            self.post("/api/add", {"name": "本地页", "url": p1, "focus": "价格"})
            r = self.post("/api/check", {"key": "本地页"})
            self.assertTrue(r["first"])

    def test_bad_add(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/add", {"name": "", "url": "", "focus": ""})
        self.assertEqual(ctx.exception.code, 400)

    def test_events_endpoint(self):
        j = self.get("/api/events?limit=5")
        self.assertIn("events", j)
        self.assertIn("stats", j)


if __name__ == "__main__":
    unittest.main()
