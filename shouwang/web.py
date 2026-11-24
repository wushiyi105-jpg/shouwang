"""Web 界面：一个页面看所有监控和它们的变化记录。

"立即检查"是同步执行的——点了会转圈十几秒（要抓页面、要调模型）。
这不是偷懒，是我不想引入任务队列；单用户的东西，等一会儿比多一个后台进程划算。
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import store
from .llm import LLMError
from .runner import check_once

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>守望 · 网页变化监控</title>
<style>
  :root { --ink:#1b1f24; --muted:#6b7280; --line:#e6e8eb; --bg:#f6f7f9; --accent:#b1541f; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  header { background:#fff; border-bottom:1px solid var(--line); padding:16px 28px;
           display:flex; align-items:baseline; gap:12px; }
  header h1 { margin:0; font-size:19px; letter-spacing:1px; }
  header span { color:var(--muted); font-size:12px; }
  main { display:grid; grid-template-columns:340px 1fr; min-height:calc(100vh - 57px); }
  aside { background:#fff; border-right:1px solid var(--line); padding:16px; overflow:auto; }
  aside h2 { font-size:12px; font-weight:500; color:var(--muted); margin:0 0 10px; letter-spacing:.5px; }
  .w { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-bottom:8px; }
  .w .name { font-weight:600; font-size:14px; }
  .w .focus { color:var(--muted); font-size:12px; margin:4px 0 8px; }
  .w .row { display:flex; gap:6px; flex-wrap:wrap; }
  .w button { font-size:12px; padding:5px 10px; }
  button { font:inherit; font-size:13px; border:0; border-radius:8px; padding:7px 13px;
           background:var(--accent); color:#fff; cursor:pointer; }
  button.ghost { background:#f3ece7; color:var(--accent); }
  button:disabled { opacity:.45; cursor:default; }
  input, textarea { width:100%; padding:7px 9px; font:inherit; font-size:13px; border:1px solid var(--line);
                    border-radius:7px; margin-bottom:6px; background:#fff; }
  section { padding:20px 26px; }
  .stats { display:flex; gap:18px; margin-bottom:16px; color:var(--muted); font-size:13px; }
  .stats b { color:var(--ink); font-size:18px; font-weight:600; }
  .ev { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:10px;
        border-left:4px solid #cfd4da; }
  .ev.imp { border-left-color:var(--accent); }
  .ev .head { display:flex; justify-content:space-between; gap:10px; font-size:13px; }
  .ev .title { font-weight:600; font-size:14px; }
  .ev .meta { color:var(--muted); font-size:12px; }
  .ev .reason { margin-top:6px; font-size:13px; line-height:1.7; }
  .ev .advice { margin-top:6px; font-size:13px; color:#8a4a12; }
  .ev pre { margin:8px 0 0; font:inherit; font-size:12px; color:#4b5563; white-space:pre-wrap; }
  .tag { font-size:11px; padding:2px 7px; border-radius:99px; background:#f0f1f3; color:#555; }
  .tag.high { background:#fdece4; color:#a3401a; }
  #hint { color:var(--muted); font-size:12px; margin-left:10px; }
</style>
</head>
<body>
<header>
  <h1>守望</h1>
  <span>盯着网页，变了先问模型值不值得吵你</span>
</header>
<main>
<aside>
  <h2>监控</h2>
  <div id="watches"></div>
  <div style="border-top:1px solid var(--line); margin-top:14px; padding-top:12px">
    <h2>加一个</h2>
    <input id="n" placeholder="名字，例如 BTC 价格">
    <input id="u" placeholder="网址，http(s):// 或本地文件路径">
    <input id="f" placeholder="关注点，例如 价格 / 库存 / 截止日期">
    <input id="i" type="number" value="30" placeholder="检查间隔（分钟）">
    <button onclick="add()">加进监控</button>
  </div>
</aside>
<section>
  <div class="stats" id="stats"></div>
  <div id="events"></div>
</section>
</main>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'},
                                      body: JSON.stringify(body)} : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function load() {
  const [w, s] = await Promise.all([api('/api/watches'), api('/api/events?limit=40')]);
  $('stats').innerHTML = `<span><b>${s.stats.watches}</b> 个监控</span>
    <span><b>${s.stats.snapshots}</b> 次抓取</span>
    <span><b>${s.stats.events}</b> 次变化</span>
    <span><b>${s.stats.important}</b> 次值得提醒</span>
    <span style="color:#8b949e">（模型替你挡掉了 ${s.stats.events - s.stats.important} 次噪音）</span>`;

  $('watches').innerHTML = w.watches.length ? w.watches.map(x => `
    <div class="w">
      <div class="name">${esc(x.name)} <span class="tag">${x.enabled ? '开' : '关'}</span></div>
      <div class="focus">${esc(x.focus)} · ${x.interval_min}min</div>
      <div class="meta" style="color:#8b949e;font-size:11px;margin-bottom:8px">${esc(x.url)}</div>
      <div class="row">
        <button onclick="check('${esc(x.name)}', this)">立刻检查</button>
        <button class="ghost" onclick="toggle('${esc(x.name)}')">${x.enabled ? '停用' : '启用'}</button>
        <button class="ghost" onclick="rm('${esc(x.name)}')">删除</button>
      </div>
    </div>`).join('') : '<div style="color:#8b949e;font-size:13px">还没有监控。</div>';

  $('events').innerHTML = s.events.length ? s.events.map(e => `
    <div class="ev ${e.important ? 'imp' : ''}">
      <div class="head">
        <span class="title">${esc(e.title)}</span>
        <span class="meta">${esc(e.watch_name)} · ${esc(e.created_at)}</span>
      </div>
      <div class="reason">${esc(e.reason)}</div>
      ${e.advice ? `<div class="advice">建议：${esc(e.advice)}</div>` : ''}
      ${(e.added.length || e.removed.length) ? `<pre>${e.added.map(x => '+ ' + esc(x)).join('\\n')}${e.removed.length ? '\\n' + e.removed.map(x => '- ' + esc(x)).join('\\n') : ''}</pre>` : ''}
    </div>`).join('') : '<div style="color:#8b949e">还没有记录。加一个监控，跑一次试试。</div>';
}

async function check(name, btn) {
  btn.disabled = true; btn.textContent = '检查中…';
  try {
    const r = await api('/api/check', {key: name});
    if (!r.ok) { alert('抓取失败：' + r.error); }
    else if (r.first) { alert('已建立基线。下次再检查时才有对比。'); }
    else if (!r.changed) { alert('没变化，模型没被打扰。'); }
    else { alert('模型判断：' + (r.verdict.important ? '值得提醒' : '不重要') + '\\n' + r.verdict.reason); }
    await load();
  } catch (e) { alert('失败：' + e.message); }
  finally { btn.disabled = false; btn.textContent = '立刻检查'; }
}

async function add() {
  const name = $('n').value.trim(), url = $('u').value.trim(), focus = $('f').value.trim();
  if (!name || !url || !focus) { alert('名字、网址、关注点都要填'); return; }
  try {
    await api('/api/add', {name, url, focus, interval: Number($('i').value) || 30});
    $('n').value = $('u').value = $('f').value = '';
    await load();
  } catch (e) { alert('失败：' + e.message); }
}

async function toggle(name) { await api('/api/toggle', {key: name}); await load(); }
async function rm(name) {
  if (!confirm('删掉这个监控？历史和事件一起删。')) return;
  await api('/api/rm', {key: name}); await load();
}
load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    conn = None
    lock = threading.Lock()
    server_version = "shouwang/0.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if parsed.path == "/api/watches":
            with self.lock:
                ws = store.list_watches(self.conn)
                for w in ws:
                    last = store.latest_snapshot(self.conn, w["id"])
                    w["last"] = last["fetched_at"] if last else None
                    w["enabled"] = bool(w["enabled"])
            return self._json({"watches": ws})
        if parsed.path == "/api/events":
            qs = urllib.parse.parse_qs(parsed.query)
            wid = int(qs.get("watch_id", [0])[0] or 0)
            with self.lock:
                evs = store.list_events(self.conn, wid or None, limit=int(qs.get("limit", [40])[0]))
                st = store.stats(self.conn)
            return self._json({"events": evs, "stats": st})
        return self._json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)

        if parsed.path == "/api/add":
            name = (body.get("name") or "").strip()
            url = (body.get("url") or "").strip()
            focus = (body.get("focus") or "").strip()
            if not (name and url and focus):
                return self._json({"error": "名字、网址、关注点都不能空"}, status=400)
            try:
                with self.lock:
                    wid = store.add_watch(self.conn, name, url, focus, int(body.get("interval") or 30))
            except ValueError as e:
                return self._json({"error": str(e)}, status=400)
            return self._json({"id": wid})

        if parsed.path == "/api/rm":
            with self.lock:
                n = store.remove_watch(self.conn, str(body.get("key") or ""))
            return self._json({"removed": n})

        if parsed.path == "/api/toggle":
            with self.lock:
                w = store.get_watch(self.conn, str(body.get("key") or ""))
                if not w:
                    return self._json({"error": "没有这个监控"}, status=404)
                store.set_enabled(self.conn, w["name"], not bool(w["enabled"]))
            return self._json({"ok": True})

        if parsed.path == "/api/check":
            key = str(body.get("key") or "")
            with self.lock:
                w = store.get_watch(self.conn, key)
            if not w:
                return self._json({"error": "没有这个监控"}, status=404)
            try:
                with self.lock:
                    r = check_once(self.conn, w)
            except LLMError as e:
                return self._json({"error": f"模型调用失败：{e}"}, status=502)
            return self._json({k: v for k, v in r.items() if k != "watch"})

        return self._json({"error": "not found"}, status=404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4 * 1024 * 1024:
            raise ValueError("请求太大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, payload: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(conn, host: str = "127.0.0.1", port: int = 8766) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"conn": conn, "lock": threading.Lock()})
    return ThreadingHTTPServer((host, port), handler)


def serve(conn, host: str = "127.0.0.1", port: int = 8766):
    httpd = make_server(conn, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停了。")
    finally:
        httpd.server_close()
