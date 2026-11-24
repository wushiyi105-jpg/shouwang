"""生成 assets/demo.gif：守望的终端演示（960×600）。

开发期脚本，依赖 Pillow（不进 requirements）。跑法：
    python scripts/make_demo_gif.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = "#0b0f14"
BAR = "#161b22"
LINE = "#21262d"
GREEN = "#7ee787"
TEXT = "#c9d1d9"
DIM = "#8b949e"
BLUE = "#79c0ff"
ORANGE = "#ffa657"

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
LINE_H = 24


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


def render(rows, cursor_row=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=BAR)
    for i, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([14 + i * 20, 11, 25 + i * 20, 22], fill=color)
    d.text((84, 8), "shouwang — 网页变化监控", font=font(14), fill=DIM)
    d.line([0, 34, W, 34], fill=LINE)

    y = 50
    for idx, (style, text) in enumerate(rows):
        color = {"cmd": GREEN, "out": TEXT, "dim": DIM, "imp": ORANGE, "cite": BLUE}[style]
        d.text((24, y), text, font=font(15), fill=color)
        if cursor_row == idx:
            w = d.textlength(text, font=font(15))
            d.rectangle([24 + w + 4, y + 2, 24 + w + 12, y + 17], fill=GREEN)
        y += LINE_H
        if y > H - 16:
            break
    return img


SCRIPT = [
    ("cmd", '> python -m shouwang add 青梧耳机·价格 data/price.html --focus "价格、库存、发货时效"'),
    ("out", "✓ [1] 青梧耳机·价格 → data/price.html"),
    ("dim", "   关注：价格、库存、发货时效    每 30 分钟看一次"),
    ("dim", ""),
    ("cmd", "> python -m shouwang run --only 青梧耳机·价格"),
    ("out", "· 青梧耳机·价格  建立基线，133 字。之后的变化都会拿来比。"),
    ("dim", ""),
    ("dim", "（商家把页面改了：499→399，库存 12→3，发货 48h→72h）"),
    ("dim", ""),
    ("cmd", "> python -m shouwang run --only 青梧耳机·价格"),
    ("imp", "! 青梧耳机·价格  有变化：+4 / -4 行"),
    ("imp", "   模型判断：重要[high] — 降价至399，库存仅3件"),
    ("out", "   理由：价格从499降到399，库存从12件减到3件，促销截止日提前到11月30日，"),
    ("out", "        发货时效从48小时延长到72小时。"),
    ("out", "   建议：要买就尽快，库存只剩3件；留意发货已变成72小时内。"),
]
TAIL = [
    ("dim", ""),
    ("dim", "另一条监控盯着随机名言页：两次内容不同，模型判「不重要」——"),
    ("dim", "它认出了那是语录库的正常轮换，没有为这点变化吵人。"),
]


def build():
    frames = []
    typed = ""
    for ch in SCRIPT[0][1][::3]:
        typed += ch
        frames.append(render([("cmd", typed)], cursor_row=0))

    rows = [SCRIPT[0]]
    for row in SCRIPT[1:5]:
        rows = rows + [row]
        frames.append(render(rows))

    typed = ""
    for ch in SCRIPT[4][1][::3]:
        typed += ch
        frames.append(render(rows[:-1] + [("cmd", typed)], cursor_row=len(rows) - 1))

    rows = [SCRIPT[0]] + SCRIPT[1:]
    for i in range(5, len(SCRIPT)):
        frames.append(render(rows[: i + 1]))

    full = rows + TAIL
    for _ in range(5):
        frames.append(render(full))

    frames = [f.quantize(colors=32, method=Image.MEDIANCUT) for f in frames]
    os.makedirs("assets", exist_ok=True)
    out = os.path.join("assets", "demo.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=150, loop=0, optimize=True)
    print(f"ok -> {out}  {len(frames)} 帧  {os.path.getsize(out)/1024:.1f} KB")


if __name__ == "__main__":
    build()
