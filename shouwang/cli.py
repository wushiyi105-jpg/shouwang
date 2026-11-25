"""命令行：python -m shouwang <子命令>。"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__, store
from .llm import LLMError
from .runner import check_once

DEFAULT_DB = os.path.join("data", "shouwang.db")


def _conn(args):
    return store.connect(args.db)


def cmd_add(args) -> int:
    conn = _conn(args)
    try:
        wid = store.add_watch(conn, args.name, args.url, args.focus, args.interval, replace=args.replace)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"✓ [{wid}] {args.name} → {args.url}")
    print(f"   关注：{args.focus}    每 {args.interval} 分钟看一次")
    print("   先跑一次建立基线：python -m shouwang run --only " + args.name)
    return 0


def cmd_list(args) -> int:
    conn = _conn(args)
    ws = store.list_watches(conn)
    if not ws:
        print("还没有监控。用 add 加一个。")
        return 0
    for w in ws:
        last = store.latest_snapshot(conn, w["id"])
        state = "开" if w["enabled"] else "关"
        tail = f"上次 {last['fetched_at']}（{last['chars']} 字）" if last else "还没跑过"
        print(f"[{w['id']}] {w['name']}  [{state}]  {w['interval_min']}min")
        print(f"     {w['url']}")
        print(f"     关注：{w['focus']}")
        print(f"     {tail}")
    return 0


def _print_result(r: dict) -> None:
    name = r["watch"]
    if not r["ok"]:
        print(f"✗ {name}  抓取失败（{r['stage']}）：{r['error']}")
        return
    if r.get("first"):
        print(f"· {name}  建立基线，{r['chars']} 字。之后的变化都会拿来比。")
        return
    if not r["changed"]:
        print(f"· {name}  没变化（{r['chars']} 字），不打扰。")
        return
    v = r["verdict"]
    ch = r["changes"]
    tag = f"重要[{v['level']}]" if v["important"] else "不重要"
    print(f"{'!' if v['important'] else '·'} {name}  有变化：+{ch['added_count']} / -{ch['removed_count']} 行")
    print(f"   模型判断：{tag} — {v['title']}")
    print(f"   理由：{v['reason']}")
    if v["advice"]:
        print(f"   建议：{v['advice']}")
    for line in ch["added"][:5]:
        print(f"   + {line[:100]}")
    for line in ch["removed"][:5]:
        print(f"   - {line[:100]}")


def cmd_run(args) -> int:
    conn = _conn(args)
    if args.loop:
        print(f"常驻模式：每 {args.every} 秒扫一遍，Ctrl+C 停。")
        try:
            while True:
                _run_all(conn, args)
                time.sleep(max(args.every, 30))
        except KeyboardInterrupt:
            print("停了。")
        return 0
    return _run_all(conn, args)


def _run_all(conn, args) -> int:
    ws = store.list_watches(conn)
    if args.only:
        w = store.get_watch(conn, args.only)
        if not w:
            print(f"没有叫 {args.only} 的监控。", file=sys.stderr)
            return 1
        ws = [w]
    if not args.all:
        ws = [w for w in ws if w["enabled"]]
    if not ws:
        print("没有可跑的监控。")
        return 0

    failed = 0
    for w in ws:
        try:
            r = check_once(conn, w)
        except LLMError as e:
            print(f"✗ {w['name']}  模型调用失败：{e}", file=sys.stderr)
            failed += 1
            continue
        _print_result(r)
        if not r["ok"]:
            failed += 1
    print()
    print("统计：", store.stats(conn))
    return 1 if failed else 0


def cmd_events(args) -> int:
    conn = _conn(args)
    evs = store.list_events(conn, limit=args.limit, only_important=args.important_only)
    if not evs:
        print("还没有事件记录。")
        return 0
    for e in evs:
        flag = f"重要[{e['level']}]" if e["important"] else "不重要"
        print(f"[{e['created_at']}] {e['watch_name']} · {flag} · {e['title']}")
        print(f"    {e['reason']}")
        if e["advice"]:
            print(f"    建议：{e['advice']}")
    return 0


def cmd_show(args) -> int:
    conn = _conn(args)
    w = store.get_watch(conn, args.key)
    if not w:
        print("没有这个监控。", file=sys.stderr)
        return 1
    print(f"[{w['id']}] {w['name']}  {w['url']}")
    print(f"关注：{w['focus']}    间隔 {w['interval_min']} 分钟    {'开' if w['enabled'] else '关'}")
    snaps = conn.execute(
        "SELECT id, fetched_at, chars, status FROM snapshots WHERE watch_id = ? ORDER BY id DESC LIMIT 10",
        (w["id"],),
    ).fetchall()
    print(f"\n最近 {len(snaps)} 次抓取：")
    for s in snaps:
        print(f"  {s['fetched_at']}  {s['chars']} 字  HTTP {s['status']}")
    evs = store.list_events(conn, w["id"], limit=10)
    print(f"\n最近 {len(evs)} 条事件：")
    for e in evs:
        print(f"  {e['created_at']}  {'重要' if e['important'] else '不重要'}  {e['title']}")
    return 0


def cmd_toggle(args) -> int:
    conn = _conn(args)
    n = store.set_enabled(conn, args.key, args.action == "enable")
    print("已切换。" if n else "没有这个监控。")
    return 0 if n else 1


def cmd_rm(args) -> int:
    conn = _conn(args)
    n = store.remove_watch(conn, args.key)
    print("删了。" if n else "没有这个监控。")
    return 0 if n else 1


def cmd_serve(args) -> int:
    from .web import serve

    conn = _conn(args)
    print(f"守望 Web：http://127.0.0.1:{args.port}  （Ctrl+C 停）")
    serve(conn, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shouwang",
        description="盯着一个网页，变了就让模型判断值不值得提醒你。",
    )
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--version", action="version", version=f"shouwang {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="加一个监控")
    a.add_argument("name")
    a.add_argument("url")
    a.add_argument("--focus", required=True, help="你关注什么，例如「价格」「库存」「报名截止日」")
    a.add_argument("--interval", type=int, default=30, help="建议检查间隔（分钟）")
    a.add_argument("--replace", action="store_true")
    a.set_defaults(func=cmd_add)

    ls = sub.add_parser("list", help="列出监控")
    ls.set_defaults(func=cmd_list)

    r = sub.add_parser("run", help="跑一次检查")
    r.add_argument("--only", help="只跑某个监控（名字或 id）")
    r.add_argument("--all", action="store_true", help="连停用的也跑")
    r.add_argument("--loop", action="store_true", help="常驻循环")
    r.add_argument("--every", type=int, default=300, help="常驻模式下的间隔秒数")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("events", help="看事件")
    e.add_argument("--limit", type=int, default=20)
    e.add_argument("--important-only", action="store_true")
    e.set_defaults(func=cmd_events)

    sh = sub.add_parser("show", help="看某个监控的历史")
    sh.add_argument("key")
    sh.set_defaults(func=cmd_show)

    for name in ("enable", "disable"):
        t = sub.add_parser(name, help=f"{name} 一个监控")
        t.add_argument("key")
        t.set_defaults(func=cmd_toggle)
        t.set_defaults(action=name)

    rm = sub.add_parser("rm", help="删一个监控")
    rm.add_argument("key")
    rm.set_defaults(func=cmd_rm)

    sv = sub.add_parser("serve", help="起 Web")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8766)
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "action"):
        args.action = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
