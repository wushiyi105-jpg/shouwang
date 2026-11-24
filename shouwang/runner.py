"""一次检查的完整流程：抓 → 比 → 判 → 记。

顺序是刻意排的：
先抓再比，比出来没变化就直接结束，连模型都不调——省钱，也省得模型对着"没变化"编话。
"""

from __future__ import annotations

from . import diff as diff_mod
from . import judge as judge_mod
from . import store
from .fetch import FetchError, fetch

KEEP_SNAPSHOTS = 50


def check_once(conn, watch: dict, config: dict | None = None) -> dict:
    """跑一次，返回结构化结果（给 CLI 和 Web 共用）。"""
    base = {"watch": watch["name"], "url": watch["url"]}
    try:
        snap = fetch(watch["url"])
    except FetchError as e:
        return {**base, "ok": False, "stage": "fetch", "error": str(e)}

    fp = diff_mod.fingerprint(snap["text"])
    prev = store.latest_snapshot(conn, watch["id"])
    store.save_snapshot(conn, watch["id"], snap, fp)
    _prune(conn, watch["id"])

    if prev is None:
        return {
            **base,
            "ok": True,
            "first": True,
            "changed": False,
            "chars": len(snap["text"]),
        }

    if prev["fp"] == fp:
        return {
            **base,
            "ok": True,
            "first": False,
            "changed": False,
            "chars": len(snap["text"]),
        }

    changes = diff_mod.diff(prev["text"], snap["text"])
    verdict = judge_mod.judge(watch["focus"], prev["text"], snap["text"], changes, config=config)
    store.add_event(conn, watch["id"], verdict, changes)

    return {
        **base,
        "ok": True,
        "first": False,
        "changed": True,
        "chars": len(snap["text"]),
        "changes": changes,
        "verdict": verdict,
    }


def _prune(conn, watch_id: int) -> None:
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM snapshots WHERE watch_id = ? ORDER BY id DESC", (watch_id,)
    ).fetchall()]
    for old_id in ids[KEEP_SNAPSHOTS:]:
        conn.execute("DELETE FROM snapshots WHERE id = ?", (old_id,))
    conn.commit()
