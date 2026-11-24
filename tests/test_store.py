import os
import tempfile
import unittest

from shouwang import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_add_and_get(self):
        wid = store.add_watch(self.conn, "耳机", "https://example.com/p", "价格", 15)
        w = store.get_watch(self.conn, "耳机")
        self.assertEqual(w["id"], wid)
        self.assertEqual(w["focus"], "价格")
        self.assertEqual(w["interval_min"], 15)
        self.assertEqual(store.get_watch(self.conn, str(wid))["name"], "耳机")

    def test_duplicate_name(self):
        store.add_watch(self.conn, "耳机", "a", "价格")
        with self.assertRaises(ValueError):
            store.add_watch(self.conn, "耳机", "b", "价格")
        store.add_watch(self.conn, "耳机", "b", "价格", replace=True)
        self.assertEqual(store.get_watch(self.conn, "耳机")["url"], "b")

    def test_remove(self):
        store.add_watch(self.conn, "耳机", "a", "价格")
        self.assertEqual(store.remove_watch(self.conn, "耳机"), 1)
        self.assertEqual(store.list_watches(self.conn), [])
        self.assertEqual(store.remove_watch(self.conn, "没有"), 0)

    def test_toggle(self):
        store.add_watch(self.conn, "耳机", "a", "价格")
        store.set_enabled(self.conn, "耳机", False)
        self.assertEqual(store.get_watch(self.conn, "耳机")["enabled"], 0)
        store.set_enabled(self.conn, "耳机", True)
        self.assertEqual(store.get_watch(self.conn, "耳机")["enabled"], 1)

    def test_snapshot(self):
        wid = store.add_watch(self.conn, "耳机", "a", "价格")
        snap = {"fetched_at": "2026-11-24 10:00:00", "status": 200, "elapsed_ms": 120, "text": "价格 499"}
        sid = store.save_snapshot(self.conn, wid, snap, "fp1")
        last = store.latest_snapshot(self.conn, wid)
        self.assertEqual(last["id"], sid)
        self.assertEqual(last["fp"], "fp1")
        self.assertEqual(last["chars"], 6)

    def test_events_and_stats(self):
        wid = store.add_watch(self.conn, "耳机", "a", "价格")
        v_imp = {"important": True, "level": "high", "title": "降价", "reason": "499→399", "advice": "买"}
        v_no = {"important": False, "level": "low", "title": "排版", "reason": "无关", "advice": ""}
        ch = {"added": ["价格 399"], "removed": ["价格 499"]}
        store.add_event(self.conn, wid, v_imp, ch)
        store.add_event(self.conn, wid, v_no, ch)
        evs = store.list_events(self.conn, wid)
        self.assertEqual(len(evs), 2)
        self.assertTrue(evs[0]["important"] is False)  # 倒序，最后一条在前
        self.assertEqual(evs[0]["added"], ["价格 399"])
        only_imp = store.list_events(self.conn, wid, only_important=True)
        self.assertEqual(len(only_imp), 1)
        st = store.stats(self.conn)
        self.assertEqual(st["events"], 2)
        self.assertEqual(st["important"], 1)


if __name__ == "__main__":
    unittest.main()
