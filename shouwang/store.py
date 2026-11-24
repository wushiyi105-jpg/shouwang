"""SQLite：watches / snapshots / events 三张表。

events 里留了 important 字段而不是只存"提醒"，
这样你能回头看见模型替你挡掉了多少次噪音——这也是我判断它有没有在干活的方式。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    url         TEXT NOT NULL,
    focus       TEXT NOT NULL,
    interval_min INTEGER NOT NULL DEFAULT 30,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,
    fp          TEXT NOT NULL,
    chars       INTEGER NOT NULL,
    status      INTEGER NOT NULL,
    elapsed_ms  INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_watch ON snapshots(watch_id, id DESC);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    important   INTEGER NOT NULL,
    level       TEXT NOT NULL,
    title       TEXT NOT NULL,
    reason      TEXT NOT NULL,
    advice      TEXT NOT NULL,
    added       TEXT NOT NULL,
    removed     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_watch ON events(watch_id, id DESC);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_watch(conn, name: str, url: str, focus: str, interval_min: int = 30, replace: bool = False) -> int:
    old = conn.execute("SELECT id FROM watches WHERE name = ?", (name,)).fetchone()
    if old and not replace:
        raise ValueError(f"监控名已存在：{name}（要覆盖加 --replace）")
    if old:
        conn.execute("DELETE FROM snapshots WHERE watch_id = ?", (old["id"],))
        conn.execute("DELETE FROM events WHERE watch_id = ?", (old["id"],))
        conn.execute("DELETE FROM watches WHERE id = ?", (old["id"],))
    cur = conn.execute(
        "INSERT INTO watches(name, url, focus, interval_min, enabled, created_at) VALUES (?,?,?,?,1,?)",
        (name, url, focus, interval_min, now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_watches(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM watches ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_watch(conn, key: str) -> dict | None:
    row = conn.execute("SELECT * FROM watches WHERE name = ?", (key,)).fetchone()
    if not row and str(key).isdigit():
        row = conn.execute("SELECT * FROM watches WHERE id = ?", (int(key),)).fetchone()
    return dict(row) if row else None


def remove_watch(conn, key: str) -> int:
    w = get_watch(conn, key)
    if not w:
        return 0
    conn.execute("DELETE FROM snapshots WHERE watch_id = ?", (w["id"],))
    conn.execute("DELETE FROM events WHERE watch_id = ?", (w["id"],))
    conn.execute("DELETE FROM watches WHERE id = ?", (w["id"],))
    conn.commit()
    return 1


def set_enabled(conn, key: str, enabled: bool) -> int:
    w = get_watch(conn, key)
    if not w:
        return 0
    conn.execute("UPDATE watches SET enabled = ? WHERE id = ?", (1 if enabled else 0, w["id"]))
    conn.commit()
    return 1


def latest_snapshot(conn, watch_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM snapshots WHERE watch_id = ? ORDER BY id DESC LIMIT 1", (watch_id,)
    ).fetchone()
    return dict(row) if row else None


def save_snapshot(conn, watch_id: int, snap: dict, fp: str) -> int:
    cur = conn.execute(
        "INSERT INTO snapshots(watch_id, fetched_at, fp, chars, status, elapsed_ms, text) "
        "VALUES (?,?,?,?,?,?,?)",
        (watch_id, snap["fetched_at"], fp, len(snap["text"]), snap["status"], snap["elapsed_ms"], snap["text"]),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_event(conn, watch_id: int, verdict: dict, changes: dict) -> int:
    cur = conn.execute(
        "INSERT INTO events(watch_id, created_at, important, level, title, reason, advice, added, removed) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            watch_id,
            now(),
            1 if verdict["important"] else 0,
            verdict["level"],
            verdict["title"],
            verdict["reason"],
            verdict["advice"],
            json.dumps(changes["added"], ensure_ascii=False),
            json.dumps(changes["removed"], ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_events(conn, watch_id: int | None = None, limit: int = 30, only_important: bool = False) -> list[dict]:
    sql = "SELECT e.*, w.name AS watch_name, w.url AS url FROM events e JOIN watches w ON w.id = e.watch_id"
    cond, args = [], []
    if watch_id:
        cond.append("e.watch_id = ?")
        args.append(watch_id)
    if only_important:
        cond.append("e.important = 1")
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY e.id DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["added"] = json.loads(d["added"] or "[]")
        d["removed"] = json.loads(d["removed"] or "[]")
        d["important"] = bool(d["important"])
        out.append(d)
    return out


def stats(conn) -> dict:
    w = conn.execute("SELECT COUNT(*) n FROM watches").fetchone()["n"]
    s = conn.execute("SELECT COUNT(*) n FROM snapshots").fetchone()["n"]
    e = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(important),0) imp FROM events"
    ).fetchone()
    return {"watches": w, "snapshots": s, "events": e["total"], "important": e["imp"]}
