"""抓取与正文抽取：只用标准库。

有意做的事：
1. HTTP 和 file:// 都能抓——演示时用本地页面造一个"价格变了"的场景，不用去爬别人家网站；
2. 抽正文时把 script/style/注释全扔掉，只留人眼能看到的话，否则 diff 会被埋在一堆 JS 里；
3. 记下 HTTP 状态和耗时，抓失败要能说清是超时、404 还是证书问题。
"""

from __future__ import annotations

import gzip
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) shouwang/0.1 (+https://github.com/wushiyi105-jpg/shouwang)"

MAX_TEXT = 60000  # 单次快照保留的正文上限，防止一个页面几百 KB 把库撑爆


class FetchError(Exception):
    """抓不到，或者抓到了但不是能用的话。"""


class _TextExtractor(HTMLParser):
    # 注意别把 meta / link 这类自闭合标签放进来：
    # 它们没有结束标签，计数减不掉，后面的正文会被整段吞掉。
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BREAK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def extract_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - 半截 HTML 也要能出东西
        pass
    lines = [ln.strip() for ln in p.text().split("\n")]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    # 压缩连续空行，去掉只剩标点的行
    text = "\n".join(ln for ln in text.split("\n") if len(ln.strip(" -|·•\t")) > 0)
    return text[:MAX_TEXT]


def fetch(url: str, timeout: int = 20) -> dict:
    """抓一个 URL（或本地文件），返回 {url, status, text, fetched_at, elapsed_ms}。"""
    started = time.time()
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if url.startswith("file://") or os.path.isfile(url):
        path = url.removeprefix("file://")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError as e:
            raise FetchError(f"读不到本地文件 {path}：{e}") from e
        text = extract_text(raw) if raw.lstrip().startswith("<") else raw.strip()[:MAX_TEXT]
        if not text:
            raise FetchError("文件里没有可读的正文")
        return {
            "url": url,
            "status": 200,
            "text": text,
            "fetched_at": fetched_at,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    if not url.startswith(("http://", "https://")):
        raise FetchError(f"只支持 http/https/file 地址，收到：{url}")

    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            encoding = resp.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}：{e.reason}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"连不上：{e.reason}") from e
    except TimeoutError as e:
        raise FetchError("超时") from e

    if encoding == "gzip":
        try:
            body = gzip.decompress(body)
        except OSError:
            pass

    charset = "utf-8"
    if "charset=" in ctype:
        charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    raw_text = body.decode(charset, errors="replace")

    if "html" in ctype.lower() or raw_text.lstrip().startswith("<"):
        text = extract_text(raw_text)
    else:
        text = raw_text.strip()[:MAX_TEXT]

    if not text:
        raise FetchError("抓到了，但正文是空的（可能需要登录，或者页面全是脚本）")

    return {
        "url": url,
        "status": status,
        "text": text,
        "fetched_at": fetched_at,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
