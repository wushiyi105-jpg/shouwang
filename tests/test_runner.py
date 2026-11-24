import os
import tempfile
import unittest
from unittest import mock

from shouwang import store
from shouwang.runner import check_once

SNAP_A = {"url": "x", "status": 200, "fetched_at": "2026-11-24 10:00:00", "elapsed_ms": 30,
          "text": "价格：¥499\n库存：12 件"}
SNAP_B = {"url": "x", "status": 200, "fetched_at": "2026-11-24 10:05:00", "elapsed_ms": 30,
          "text": "价格：¥399\n库存：3 件"}
VERDICT = {"important": True, "level": "high", "title": "降价", "reason": "499→399", "advice": "可以买", "error": False}


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "t.db"))
        store.add_watch(self.conn, "耳机", "x", "价格")
        self.watch = store.get_watch(self.conn, "耳机")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_first_run_sets_baseline(self):
        with mock.patch("shouwang.runner.fetch", return_value=SNAP_A):
            r = check_once(self.conn, self.watch)
        self.assertTrue(r["ok"])
        self.assertTrue(r["first"])
        self.assertFalse(r["changed"])

    def test_same_content_no_model_call(self):
        with mock.patch("shouwang.runner.fetch", return_value=SNAP_A):
            check_once(self.conn, self.watch)
        with mock.patch("shouwang.runner.fetch", return_value=SNAP_A), \
             mock.patch("shouwang.runner.judge_mod.judge") as m:
            r = check_once(self.conn, self.watch)
        m.assert_not_called()
        self.assertFalse(r["changed"])

    def test_change_triggers_judge_and_event(self):
        with mock.patch("shouwang.runner.fetch", return_value=SNAP_A):
            check_once(self.conn, self.watch)
        with mock.patch("shouwang.runner.fetch", return_value=SNAP_B), \
             mock.patch("shouwang.runner.judge_mod.judge", return_value=VERDICT) as m:
            r = check_once(self.conn, self.watch)
        m.assert_called_once()
        self.assertTrue(r["changed"])
        self.assertTrue(r["verdict"]["important"])
        evs = store.list_events(self.conn, self.watch["id"])
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["title"], "降价")

    def test_fetch_error(self):
        from shouwang.fetch import FetchError

        with mock.patch("shouwang.runner.fetch", side_effect=FetchError("连不上")):
            r = check_once(self.conn, self.watch)
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "fetch")

    def test_snapshot_pruned(self):
        from shouwang.runner import KEEP_SNAPSHOTS

        for i in range(KEEP_SNAPSHOTS + 5):
            snap = dict(SNAP_A, text=f"价格：¥{499 - i}\n内容 {i}")
            with mock.patch("shouwang.runner.fetch", return_value=snap), \
                 mock.patch("shouwang.runner.judge_mod.judge", return_value=VERDICT):
                check_once(self.conn, self.watch)
        rows = self.conn.execute(
            "SELECT COUNT(*) n FROM snapshots WHERE watch_id = ?", (self.watch["id"],)
        ).fetchone()
        self.assertEqual(rows["n"], KEEP_SNAPSHOTS)


if __name__ == "__main__":
    unittest.main()
