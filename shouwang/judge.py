"""让模型判断"这次变化值不值得吵人"。

整个项目的性格就在这里：diff 只是原材料，模型才有权按下提醒按钮。
它被要求宁可漏报也别烦人——一个天天喊"页面变了"的监控，三天就会被关掉。
"""

from __future__ import annotations

from . import llm
from .diff import summarize

SYSTEM = """你是网页监控助理。用户会告诉你他在关注什么，以及页面这次的变化。
你要判断：这个变化对用户的关注点是否重要，重要就提醒，不重要就当没发生。

判断标准：
- 价格、库存、政策条款、开放时间、联系方式、错误码、截止日期变了 → 重要
- 纯排版、广告位、推荐位、随机内容、时间戳、访问量数字、无关的新闻列表 → 不重要
- 只是措辞改写、意思没变 → 不重要
- 拿不准时给 important=false（宁可漏报，也不要天天喊"页面变了"）

只输出 JSON，不要解释：
{
  "important": true/false,
  "level": "high" | "medium" | "low",
  "title": "不超过 20 字的提醒标题",
  "reason": "为什么重要 / 为什么不重要，一两句话，必须提到具体变了什么",
  "advice": "建议用户做什么（不重要时可以写空字符串）"
}"""


def judge(focus: str, old_text: str, new_text: str, changes: dict, config: dict | None = None) -> dict:
    """返回判断结果；模型抽风时给一个保守的默认值，而不是抛异常。"""
    user = (
        f"【关注点】{focus}\n\n"
        f"【这次的变化】\n{summarize(changes)}\n\n"
        f"（旧内容共 {len(old_text)} 字，新内容共 {len(new_text)} 字）\n\n"
        "按要求输出 JSON。"
    )
    try:
        raw = llm.chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            config=config,
            temperature=0.1,
            max_tokens=600,
        )
        data = llm.extract_json(raw)
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            raise llm.LLMError("模型没有返回对象")
    except llm.LLMError as e:
        return {
            "important": False,
            "level": "low",
            "title": "判断失败",
            "reason": f"模型没能给出可用判断：{e}",
            "advice": "",
            "error": True,
        }

    important = bool(data.get("important"))
    level = str(data.get("level") or "low").lower()
    if level not in {"high", "medium", "low"}:
        level = "low"
    return {
        "important": important,
        "level": level,
        "title": str(data.get("title") or ("有变化" if important else "无实质变化"))[:60],
        "reason": str(data.get("reason") or ""),
        "advice": str(data.get("advice") or ""),
        "error": False,
    }
