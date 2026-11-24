"""变化检测：先把页面切成"行"，再做集合差。

为什么不用 difflib 的字符 diff：网页改一个版本号，字符级 diff 会把整段都标成改动，
人看着像天塌了。按行比，改哪句就只报哪句。

比较时用的是"去掉所有空白的行"（keys），展示时用原行——
不然改个缩进、多打一个空格，也会被当成内容变化。
"""

from __future__ import annotations

import hashlib
import re

MIN_LINE_LEN = 6      # 太短的行（"登录"、"首页"）被改也不值得报
MAX_REPORT = 15       # 一次最多报多少条变化，防止整页重排时刷屏
MAX_LINE_LEN = 240


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def lines(text: str) -> list[str]:
    """展示用的行：压缩多余空格，过滤太短的行。"""
    out = []
    for ln in normalize(text).split("\n"):
        ln = ln.strip()
        if len(ln) >= MIN_LINE_LEN:
            out.append(ln[:MAX_LINE_LEN])
    return out


def keys(text: str) -> list[str]:
    """比较用的行：把所有空白都去掉，只留内容。"""
    return [re.sub(r"\s+", "", ln) for ln in lines(text)]


def fingerprint(text: str) -> str:
    payload = "\n".join(keys(text)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def diff(old_text: str, new_text: str) -> dict:
    old_lines, new_lines = lines(old_text), lines(new_text)
    old_keys, new_keys = keys(old_text), keys(new_text)
    old_key_set, new_key_set = set(old_keys), set(new_keys)

    added = [ln for ln, k in zip(new_lines, new_keys) if k not in old_key_set]
    removed = [ln for ln, k in zip(old_lines, old_keys) if k not in new_key_set]

    added = _uniq(added)[:MAX_REPORT]
    removed = _uniq(removed)[:MAX_REPORT]

    return {
        "changed": bool(added or removed),
        "added": added,
        "removed": removed,
        "added_count": len(added),
        "removed_count": len(removed),
    }


def _uniq(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def summarize(d: dict) -> str:
    """给模型看的紧凑变化摘要。"""
    parts = []
    if d["added"]:
        parts.append("新增/变成：\n" + "\n".join(f"+ {x}" for x in d["added"]))
    if d["removed"]:
        parts.append("消失/原本是：\n" + "\n".join(f"- {x}" for x in d["removed"]))
    return "\n\n".join(parts) or "（没有足够长的行发生变化）"
