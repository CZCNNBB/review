#!/usr/bin/env python
"""联调用的假业务系统：一个支付场景的两端都在这一个脚本里。

它对外暴露两个接口：

``GET/POST /start``
    发起审批 —— 它扮演业务系统，拿租户 API Key 去调审批中心的
    ``POST /api/processes/{process_id}/instances``。调用成功后去控制台「审批任务」里同意。

``POST /pay``
    执行支付 —— 它扮演业务系统的收款接口，接收审批通过后审批中心的回调。
    不真扣款，只打印「支付成功了！」，并回一个成功响应。

``GET /``
    网页面板：当前配置、改请求体发起审批、实时看收到的回调。不想手敲带参数的
    地址就用它，终端里照样会打印一份。

**请求体分两层**（见 docs/业务系统接入指南.md §6.1）：

- ``business_key`` / ``title`` / ``applicant_person_id`` / ``action_code`` 是审批中心的入参，
  放在顶层 —— ``business_key`` 就是审批中心那侧的单号（幂等键），业务系统通常直接拿自己的
  付款单号填；
- ``approval_form`` 是给审批人看的业务数据（比如 ``JinEr``），要满足流程的表单 Schema；
- ``execution_payload`` 是审批通过后**原样回调**给 ``/pay`` 的请求体，业务数据都带上，
  业务标识用业务自己的说法 ``payment_id``。

特意**不在 execution_payload 里再放一个 ``business_key``**：那是审批中心的字段名，
出现两份只会让人分不清"审批中心的单号"和"业务系统的单号"（同一个值，但语义不同）。

``/pay`` 收到**认不出业务单号**的回调会回 400 —— 付哪张单都不知道，真实系统也该拒收。

完整闭环::

    /start → 审批中心（待办）→ 控制台同意 → 审批通过 → 回调 /pay → 打印支付成功

配置写在脚本同目录的 ``.env`` 里（照 ``.env.example`` 建一份），改一次就不用每次带参数::

    CENTER=http://127.0.0.1:8090
    API_KEY=appr_live_xxx          # 租户 API Key，控制台租户详情页签发
    PROCESS_ID=<审批流ID>
    ACTION_CODE=PAYMENT_EXECUTE    # 留空表示只审批不回调
    ADMIN_KEY=<管理密钥>            # 可选：填了启动时就列出可选的审批流与动作

然后直接::

    python test_backcall/test_backcall.py

命令行参数优先于 .env，临时改一项不用动文件，例如 ``--port 9100``、``--status 500``
（回调故意回失败，测执行记录的失败分支）、``--delay 8``（回调拖 8 秒，测动作超时）、
``--expect-token xxx``（核对 Service Token）、``--env 别的文件``。

控制台里要把租户的「回调基础地址」配成 ``http://127.0.0.1:9000``、签一个 Service Token
凭据、业务动作的相对路径配 ``/pay``（POST、成功状态码 200）。之后两种发起方式都行::

    http://127.0.0.1:9000/                                  # 网页面板，推荐
    http://127.0.0.1:9000/start?payment_id=PAY-1&JinEr=500  # 直接打接口
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# 这个文件是给人跑的脚本，不是测试用例；不加这行，pytest 会把它当测试模块收集。
__test__ = False

COUNT = 0
COUNT_LOCK = threading.Lock()

# 最近收到的回调，给网页面板用。只留最近这些条，不落盘。
EVENTS: list[dict[str, Any]] = []
EVENTS_MAX = 50


def record_event(entry: dict[str, Any]) -> None:
    """记一条回调，供 GET /_events 返回给页面轮询。"""

    with COUNT_LOCK:
        EVENTS.append(entry)
        del EVENTS[: max(0, len(EVENTS) - EVENTS_MAX)]


# 回调体里认哪个字段是业务单据标识。名字由业务系统自己定，这里认常见的几个；
# business_key 是早期版本脚本放的名字，留着认出来，免得老单子的回调被判成"缺标识"。
DOCUMENT_FIELDS = ("payment_id", "biz_no", "order_no", "order_id", "business_no", "business_key")

# 打印摘要时认哪个字段是金额。
AMOUNT_FIELDS = ("JinEr", "amount", "pay_amount", "money", "total_amount", "金额")

# /start 请求体里这几个字段是审批中心的一等入参或业务标识，不算审批表单的业务字段：
# 页头已经显示单号，表单里再来一份只会多一个没有显示名的英文键。
RESERVED_FIELDS = ("business_key", "payment_id", "title", "applicant_person_id")


def safe_print(text: str = "") -> None:
    """Windows 控制台默认是 GBK，打不出来的字符退化成占位符，不中断服务。

    每行都 flush：输出重定向到文件时是块缓冲的，不 flush 就看不到实时回调。
    """

    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"), flush=True)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def parse_json(raw: bytes) -> Any:
    """尽量把请求体解析成 JSON，解析不了就原样返回字符串。"""

    text = raw.decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def payment_summary(payload: Any) -> str:
    """从回调体里挑出付款单号与金额，拼一句给终端看的摘要（挑不到就给空串）。"""

    if not isinstance(payload, dict):
        return ""

    parts: list[str] = []
    for name in DOCUMENT_FIELDS:
        if payload.get(name) not in (None, ""):
            parts.append(f"付款单 {payload[name]}")
            break
    for name in AMOUNT_FIELDS:
        if payload.get(name) not in (None, ""):
            parts.append(f"金额 {payload[name]}")
            break
    return "，".join(parts)


def callback_status(configured: int, is_payment: bool, document_id: str) -> int:
    """回调实际返回的状态码。

    支付路径上缺业务标识（没 payment_id）一律回 400 —— 真实系统这时就该拒收，
    连"付哪张单"都不知道，不能照单付款。其余情况按 --status。
    """

    if is_payment and not document_id:
        return 400
    return configured


def same_path(request_path: str, expect_path: str) -> bool:
    """比路径时忽略查询串、末尾斜杠和大小写，少一个斜杠不该让联调卡住。"""

    def normalize(value: str) -> str:
        return value.split("?", 1)[0].rstrip("/").lower()

    return normalize(request_path) == normalize(expect_path)


def mask(secret: str) -> str:
    """密钥只露个头尾，打印到终端时不做完整回显。"""

    if len(secret) <= 8:
        return "***"
    return f"{secret[:8]}…{secret[-4:]}"


def message_of(envelope: Any, status: int) -> str:
    """把审批中心返回的错误翻成一句中文。

    口径与控制台的 api/errors.ts 一致：成功走 {code,msg,data} 信封；失败可能是
    信封里的 msg，也可能是 FastAPI 的 detail（字符串、校验数组、带 issues 的对象），
    都没有就给一句按状态码的兜底，别让终端只显示一个 None。
    """

    if isinstance(envelope, dict):
        if envelope.get("msg"):
            return str(envelope["msg"])

        detail = envelope.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if isinstance(detail, list):
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(part) for part in (item.get("loc") or []))
                    text = str(item.get("msg") or "")
                    parts.append(f"{loc}：{text}" if loc else text)
                else:
                    parts.append(str(item))
            if parts:
                return "；".join(parts)
        if isinstance(detail, dict):
            message = str(detail.get("message") or "请求未通过校验")
            issues = detail.get("issues")
            if isinstance(issues, list) and issues:
                rendered = [
                    f"{issue.get('message')}（{issue.get('field')}）" if issue.get("field") else str(issue.get("message"))
                    for issue in issues
                    if isinstance(issue, dict)
                ]
                message += "：" + "；".join(rendered)
            return message

    fallback = {
        401: "认证失败，请检查租户 API Key 是否正确",
        403: "这个租户没有该流程或动作的授权",
        404: "审批流不存在，检查 --process-id",
        422: "请求参数没通过校验",
        503: "服务端配置不完整，接口暂不可用",
    }
    return fallback.get(status, f"发起审批失败（HTTP {status}）")


# 网页版联调面板。自包含（没有外部 js/css），配色抄控制台的令牌，看着是一家人。
# __CONFIG__ 会被替换成当前配置的 JSON。
PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>假业务系统 · 联调面板</title>
<style>
  :root {
    --paper: #f2f4f5; --surface: #ffffff; --sunken: #f7f9fa;
    --ink: #16202b; --ink-2: #4a5763; --ink-3: #7c8894;
    --indigo: #2c4a73; --indigo-wash: #eaf0f7;
    --pine: #2c6b4f; --pine-wash: #e9f2ed;
    --cinnabar: #a8342a; --cinnabar-wash: #fbedeb;
    --rule: #d5dbe0; --rule-weak: #e7ebee;
    --mono: ui-monospace, 'Cascadia Mono', Consolas, 'Courier New', monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 28px 24px 64px; background: var(--paper); color: var(--ink);
    font: 14px/1.6 'PingFang SC', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
  }
  .wrap { max-width: 880px; margin: 0 auto; }
  h1 { margin: 0; font-size: 20px; font-weight: 600; }
  .sub { margin-top: 4px; color: var(--ink-3); font-size: 13px; }
  .card {
    margin-top: 18px; padding: 16px; background: var(--surface);
    border: 1px solid var(--rule); border-radius: 6px;
  }
  .card h2 { margin: 0 0 12px; font-size: 14px; font-weight: 600; }
  dl { display: grid; grid-template-columns: 120px 1fr; gap: 6px 12px; margin: 0; }
  dt { color: var(--ink-3); font-size: 13px; }
  dd { margin: 0; font-family: var(--mono); font-size: 12px; word-break: break-all; }
  textarea {
    width: 100%; padding: 10px; border: 1px solid var(--rule); border-radius: 4px;
    background: var(--sunken); color: var(--ink); font-family: var(--mono); font-size: 12px;
    line-height: 1.6; resize: vertical;
  }
  textarea:focus { outline: none; border-color: var(--indigo); background: var(--surface); }
  .row { display: flex; align-items: center; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
  button {
    height: 32px; padding: 0 14px; border: 1px solid var(--indigo); border-radius: 4px;
    background: var(--indigo); color: #fff; font: inherit; font-size: 13px; cursor: pointer;
  }
  button:hover { background: #223a5c; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .hint { color: var(--ink-3); font-size: 12px; }
  pre {
    margin: 12px 0 0; padding: 10px; border: 1px solid var(--rule-weak); border-radius: 4px;
    background: var(--sunken); font-family: var(--mono); font-size: 12px; line-height: 1.6;
    white-space: pre-wrap; word-break: break-all;
  }
  pre:empty { display: none; }
  .ok { color: var(--pine); }
  .bad { color: var(--cinnabar); }
  .event { padding: 10px 0; border-top: 1px dashed var(--rule-weak); }
  .event:first-child { border-top: none; }
  .event__head { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
  .pill {
    padding: 1px 7px; border: 1px solid var(--rule); border-radius: 3px; background: var(--sunken);
    font-size: 12px; color: var(--ink-2);
  }
  .pill--pay { border-color: #bcd4c5; background: var(--pine-wash); color: var(--pine); }
  .pill--bad { border-color: #e0cbc8; background: var(--cinnabar-wash); color: var(--cinnabar); }
  .time { font-family: var(--mono); font-size: 12px; color: var(--ink-3); }
  .empty { color: var(--ink-3); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>假业务系统 · 联调面板</h1>
  <div class="sub">扮演业务系统的两端：发起审批、接收审批通过后的支付回调。不真扣款。</div>

  <section class="card">
    <h2>当前配置</h2>
    <dl id="config"></dl>
  </section>

  <section class="card">
    <h2>发起审批</h2>
    <div class="hint">
      <code>payment_id</code> 是这张付款单的标识，同时也是审批中心那侧的业务单号；
      其余业务字段进审批表单给审批人看（比如这条流程必填的 <code>JinEr</code>，少了会被校验拒掉）。
      审批通过后，审批中心把 <code>execution_payload</code>（= <code>payment_id</code> + 这些业务字段）
      原样回调给支付接口。
    </div>
    <textarea id="payload" rows="6">{
  "payment_id": "PAY-2026-001",
  "JinEr": 500
}</textarea>
    <div class="row">
      <button id="start">发起审批</button>
      <span class="hint">
        <code>JinEr &gt; 1000</code> 会多走一个「领导审批」节点，否则一次同意就到结束。
      </span>
    </div>
    <pre id="result"></pre>
  </section>

  <section class="card">
    <h2>收到的回调 <span class="hint" id="count"></span></h2>
    <div id="events"><div class="empty">还没有收到回调。审批通过后，请求会打到这里。</div></div>
  </section>
</div>

<script>
const CONFIG = __CONFIG__;
const LABELS = {
  center: '审批中心',
  api_key: '租户 API Key',
  process_id: '审批流 ID',
  action_code: '业务动作',
  pay_path: '支付接口',
  expect_token: '核对 Service Token',
  status: '回调返回状态码',
};

const configBox = document.getElementById('config');
for (const [key, label] of Object.entries(LABELS)) {
  const dt = document.createElement('dt');
  dt.textContent = label;
  const dd = document.createElement('dd');
  dd.textContent = CONFIG[key];
  configBox.append(dt, dd);
}

const payloadBox = document.getElementById('payload');
const resultBox = document.getElementById('result');
const startButton = document.getElementById('start');

startButton.addEventListener('click', async () => {
  let payload;
  try {
    payload = JSON.parse(payloadBox.value);
  } catch (err) {
    resultBox.className = 'bad';
    resultBox.textContent = '请求体不是合法 JSON：' + err.message;
    return;
  }
  startButton.disabled = true;
  resultBox.className = '';
  resultBox.textContent = '正在发起…';
  try {
    const response = await fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (data.ok) {
      resultBox.className = 'ok';
      resultBox.textContent =
        '审批已发起\\n' +
        '实例 ID：' + data.instance_id + '\\n' +
        '当前节点：' + (data.current_node_name || '—') + '\\n' +
        '待办人数：' + (data.pending_approver_person_ids || []).length + '\\n\\n' +
        '去控制台的「审批任务」里同意，通过后这里下面就会出现支付回调。';
    } else {
      resultBox.className = 'bad';
      resultBox.textContent = '发起失败：' + (data.msg || '未知原因');
    }
  } catch (err) {
    resultBox.className = 'bad';
    resultBox.textContent = '请求出错：' + err.message;
  } finally {
    startButton.disabled = false;
  }
});

function renderEvents(data) {
  document.getElementById('count').textContent = data.count ? '共 ' + data.count + ' 次' : '';
  const box = document.getElementById('events');
  if (!data.events.length) {
    box.innerHTML = '<div class="empty">还没有收到回调。审批通过后，请求会打到这里。</div>';
    return;
  }
  box.innerHTML = '';
  for (const event of data.events) {
    const item = document.createElement('div');
    item.className = 'event';

    const head = document.createElement('div');
    head.className = 'event__head';

    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = event.at;

    const route = document.createElement('span');
    route.textContent = event.method + ' ' + event.path;

    const status = document.createElement('span');
    status.className = 'pill' + (event.status >= 200 && event.status < 300 ? '' : ' pill--bad');
    status.textContent = 'HTTP ' + event.status;

    head.append(time, route, status);

    if (event.is_payment) {
      const pay = document.createElement('span');
      const succeeded = event.status >= 200 && event.status < 300;
      pay.className = 'pill ' + (succeeded ? 'pill--pay' : 'pill--bad');
      pay.textContent = (succeeded ? '★ 支付成功了！' : '× 支付失败') +
        (event.summary ? '（' + event.summary + '）' : '');
      head.append(pay);
    }
    if (event.token_ok === true) {
      const token = document.createElement('span');
      token.className = 'pill pill--pay';
      token.textContent = '√ 凭据核对一致';
      head.append(token);
    }
    if (event.token_ok === false) {
      const token = document.createElement('span');
      token.className = 'pill pill--bad';
      token.textContent = '× 凭据核对不一致';
      head.append(token);
    }

    const body = document.createElement('pre');
    body.textContent = JSON.stringify(event.body, null, 2);

    item.append(head, body);
    box.append(item);
  }
}

async function loadEvents() {
  try {
    const response = await fetch('/_events');
    renderEvents(await response.json());
  } catch (err) {
    // 服务停了就别刷了，页面上留着最后一次的结果
  }
}

loadEvents();
setInterval(loadEvents, 2000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 调审批中心：发起审批
# ---------------------------------------------------------------------------


def call_center(options: argparse.Namespace, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """调用审批中心的发起接口，返回 (HTTP 状态码, 拆过信封的数据)。

    信封形如 ``{code, msg, data}``；连不上或返回非 2xx 时把原因整理成一句中文。
    """

    url = f"{options.center.rstrip('/')}/api/processes/{options.process_id}/instances"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-API-Key": options.api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            envelope = json.loads(response.read().decode("utf-8"))
            return response.status, envelope
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            envelope = json.loads(detail)
        except json.JSONDecodeError:
            envelope = {"code": exc.code, "msg": detail[:200] or exc.reason}
        return exc.code, envelope
    except urllib.error.URLError as exc:
        return 0, {"code": -1, "msg": f"连不上审批中心 {options.center}（{exc.reason}），后端起了吗？"}
    except json.JSONDecodeError as exc:
        return 0, {"code": -1, "msg": f"审批中心返回的不是 JSON：{exc}"}


def list_catalog(options: argparse.Namespace) -> None:
    """启动时用管理密钥列一下可选的审批流与业务动作，省得去控制台抄 ID。"""

    if not options.admin_key:
        return

    def fetch(path: str) -> list[dict[str, Any]] | None:
        request = urllib.request.Request(
            f"{options.center.rstrip('/')}{path}",
            headers={"X-Admin-Key": options.admin_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("data") or []
        except (urllib.error.URLError, json.JSONDecodeError):
            return None

    processes = fetch("/api/admin/processes?limit=50")
    actions = fetch("/api/admin/business-actions?limit=50")

    if processes:
        safe_print("可选的审批流（填 --process-id）：")
        for item in processes:
            safe_print(f"  {item.get('id')}  {item.get('name')}  状态 {item.get('status')}")
    if actions:
        safe_print("可选的业务动作（填 --action-code）：")
        for item in actions:
            safe_print(f"  {item.get('action_code')}  {item.get('name')}  状态 {item.get('status')}")
    if processes or actions:
        safe_print("")


# ---------------------------------------------------------------------------
# HTTP 处理
# ---------------------------------------------------------------------------


def make_handler(options: argparse.Namespace) -> type[BaseHTTPRequestHandler]:
    """生成请求处理器：/start 发起审批，/pay 收支付回调，其余路径只做提示。"""

    class FakeBusinessHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "test-backcall"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 规定的命名
            if same_path(self.path, "/"):
                self._page()
            elif same_path(self.path, "/favicon.ico"):
                # 浏览器打开面板时必来要一次，别把它当成一次回调打到终端里
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif same_path(self.path, "/_events"):
                self._events()
            elif same_path(self.path, "/start"):
                self._start(payload_from_query(self.path))
            else:
                self._callback()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length else b""
            if same_path(self.path, "/start"):
                self._start(parse_json(raw_body) or {})
            else:
                self._callback(parse_json(raw_body))

        def do_PUT(self) -> None:  # noqa: N802
            self._callback()

        def do_PATCH(self) -> None:  # noqa: N802
            self._callback()

        def do_DELETE(self) -> None:  # noqa: N802
            self._callback()

        # ------------------------------------------------------------------
        # 网页版联调面板
        # ------------------------------------------------------------------

        def _page(self) -> None:
            """一个自包含的页面：看当前配置、发起审批、看收到的回调。不做登录。"""

            config = {
                "center": options.center,
                "api_key": mask(options.api_key) if options.api_key else '（没配，发起不了）',
                "process_id": options.process_id or '（没配）',
                "action_code": options.action_code or '（没配 —— 只审批，通过后不回调）',
                "pay_path": options.pay_path,
                "expect_token": mask(options.expect_token) if options.expect_token else '（没核对）',
                "status": options.status,
            }
            html = PAGE.replace("__CONFIG__", json.dumps(config, ensure_ascii=False))
            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _events(self) -> None:
            """给页面轮询的回调列表（最近的在前）。"""

            with COUNT_LOCK:
                body = {"count": COUNT, "events": list(reversed(EVENTS))}
            self._json(200, body)

        # ------------------------------------------------------------------
        # /start：发起审批
        # ------------------------------------------------------------------

        def _start(self, payload: dict[str, Any]) -> None:
            if not isinstance(payload, dict):
                payload = {}

            if not options.api_key or not options.process_id:
                missing = []
                if not options.api_key:
                    missing.append("--api-key（租户 API Key，在控制台租户详情页签发）")
                if not options.process_id:
                    missing.append("--process-id（审批流 ID，加 --admin-key 启动可以直接列出来）")
                self._json(400, {"ok": False, "msg": "还差配置：" + "；".join(missing)})
                safe_print(f"× 发起审批被拒：还差 {'；'.join(missing)}")
                return

            # 付款单号：这张付款单自己的标识，同时也是审批中心那侧的 business_key
            # （业务单号通常就是单据号，所以演示里用同一个值）。
            payment_id = str(
                payload.get("payment_id")
                or payload.get("business_key")
                or f"PAY-{datetime.now():%Y%m%d%H%M%S}"
            )
            title = str(payload.get("title") or f"付款申请 {payment_id}")
            applicant = payload.get("applicant_person_id")

            # 业务字段进审批表单（审批人看得到金额）；单号/标题/发起人剔掉 —— 它们是审批中心的
            # 一等入参，页头已经显示，放进表单只会多一行没有显示名的英文键。
            form_payload = {
                key: value for key, value in payload.items() if key not in RESERVED_FIELDS
            }

            body = {
                "business_key": payment_id,
                "title": title,
                "applicant_person_id": applicant,
                "action_code": options.action_code or None,
                "approval_form": form_payload,
                # 执行参数就是业务系统真正要的那份请求体：业务标识用业务自己的说法
                # （payment_id），业务数据（金额等）照旧带上 —— 审批通过后原样回调给 /pay。
                # 注意别在这里再放一个 business_key：那是审批中心的字段名，出现两份只会让人
                # 分不清哪个是"审批中心的单号"、哪个是"业务系统的单号"。
                "execution_payload": {"payment_id": payment_id, **form_payload},
            }

            safe_print("─" * 78)
            safe_print(f"[{datetime.now():%H:%M:%S}] 收到发起审批请求：{self.command} {self.path}")
            safe_print(f"  付款单号：{payment_id}    标题：{title}")
            # 把实际发给审批中心的请求体打出来：类型不对导致的 422 只能靠这个看
            safe_print("  发给审批中心的请求体：")
            safe_print(json.dumps(body, ensure_ascii=False, indent=2))
            safe_print(
                f"  → 调审批中心 POST {options.center.rstrip('/')}/api/processes/{options.process_id}/instances"
                f"（X-API-Key: {mask(options.api_key)}）"
            )
            if options.action_code:
                safe_print(f"     审批通过后回调业务动作：{options.action_code}")
            else:
                safe_print("     没指定 --action-code：只走审批，通过后不回调")

            status, envelope = call_center(options, body)
            data = envelope.get("data") or {}

            if not data.get("instance_id"):
                reason = message_of(envelope, status)
                safe_print(f"  × 发起失败（HTTP {status}）：{reason}")
                safe_print("─" * 78)
                self._json(status or 502, {"ok": False, "msg": reason})
                return

            approvers = data.get("pending_approver_person_ids") or []
            safe_print(
                f"  √ 审批已发起：实例 {data['instance_id']}，"
                f"当前节点「{data.get('current_node_name') or '—'}」，待办 {len(approvers)} 人"
            )
            if data.get("idempotent_replay"):
                # 接入指南 §8：幂等键是 租户 + process_id + business_key，重复提交不算错
                safe_print("     （重复提交：返回的是原来那个实例，没有新建；换了内容再提交会 409）")
            safe_print(f"     去控制台审批任务里同意：/#/instances/{data['instance_id']}")
            if options.action_code:
                safe_print("     同意之后等一会儿，这个窗口会打印支付回调。")
            safe_print("─" * 78)

            self._json(
                200,
                {
                    "ok": True,
                    "instance_id": data.get("instance_id"),
                    "status": data.get("status"),
                    "current_node_name": data.get("current_node_name"),
                    "pending_approver_person_ids": approvers,
                },
            )

        # ------------------------------------------------------------------
        # /pay：接收支付回调
        # ------------------------------------------------------------------

        def _callback(self, payload: Any = None) -> None:
            global COUNT

            if payload is None:
                length = int(self.headers.get("Content-Length") or 0)
                payload = parse_json(self.rfile.read(length)) if length else None

            with COUNT_LOCK:
                COUNT += 1
                index = COUNT

            is_payment = same_path(self.path, options.pay_path)

            lines = [
                "─" * 78,
                f"[{datetime.now():%H:%M:%S}] 第 {index} 次回调：{self.command} {self.path}",
                f"  来源：{self.client_address[0]}:{self.client_address[1]}",
            ]

            # 认证头：回调复用业务系统自己的认证方式，头名与前缀都在凭据里配
            skip = {"host", "content-type", "content-length", "accept-encoding", "connection", "user-agent"}
            for name in self.headers:
                if name.lower() not in skip:
                    lines.append(f"  {name}: {self.headers[name]}")

            if options.expect_token:
                if options.expect_token in self.headers.get(options.token_header, ""):
                    lines.append("  √ Service Token 与 --expect-token 一致")
                else:
                    lines.append(f"  × Service Token 对不上：{options.token_header} 里没有期望的值")

            lines.append("  请求体：")
            lines.append(
                json.dumps(payload, ensure_ascii=False, indent=2)
                if not isinstance(payload, str)
                else (payload or "（空）")
            )
            # 接入指南 §10：回调请求体就是发起审批时保存的 execution_payload，原样发过来，
            # 审批中心不会自动补单号之类的字段 —— 业务标识得发起方自己放。
            lines.append("  （上面是发起审批时放进 execution_payload 的内容，原样发过来的）")

            # 回调体里有没有能认出来的业务单号：没有就没人知道要付哪张单，真实系统该拒收
            document_id = (
                next(
                    (str(payload[name]) for name in DOCUMENT_FIELDS if payload.get(name) not in (None, "")),
                    "",
                )
                if isinstance(payload, dict)
                else ""
            )

            # 响应体会原样落到控制台的执行记录里，所以它得说实话：
            # 路径配错时不要回"支付成功"，否则执行记录上看起来像是成功的。
            succeeded = 200 <= options.status < 300
            if not is_payment:
                message = f"收到了 {self.path}，但支付接口配的是 {options.pay_path}"
            elif not document_id:
                succeeded = False
                lines.append("")
                lines.append("  × 回调体里没有付款单号（payment_id），找不到要付哪张单 —— 真实系统这时应回 4xx")
                message = "回调请求体里缺少 payment_id，无法确定要支付哪张付款单"
            elif succeeded:
                message = "支付成功"
            else:
                message = "支付失败（脚本按参数故意返回的）"

            response_body = {
                "ok": succeeded,
                "msg": message,
                "paid_at": datetime.now().isoformat(timespec="seconds"),
            }

            record_event(
                {
                    "at": datetime.now().strftime("%H:%M:%S"),
                    "method": self.command,
                    "path": self.path,
                    "is_payment": is_payment,
                    "status": callback_status(options.status, is_payment, document_id),
                    "summary": payment_summary(payload),
                    "body": payload if not isinstance(payload, str) else {"原始内容": payload},
                    "token_ok": (
                        options.expect_token in self.headers.get(options.token_header, "")
                        if options.expect_token
                        else None
                    ),
                },
            )

            if is_payment and succeeded:
                summary = payment_summary(payload)
                lines.append("")
                lines.append(f"  ★ 支付成功了！{f'（{summary}）' if summary else ''}")
            elif is_payment and document_id:
                lines.append("")
                lines.append(f"  × 收到了支付请求，但按 --status {options.status} 回了失败（测失败分支用的）")
            elif is_payment:
                pass  # 缺付款单号的提示上面已经打过了
            else:
                lines.append("")
                lines.append(f"  ! 这不是配置的支付路径（--pay-path {options.pay_path}），动作的相对路径多半配错了")

            if options.delay:
                lines.append(f"  （故意拖 {options.delay} 秒再回，测动作的超时）")
                safe_print("\n".join(lines))
                time.sleep(options.delay)

            status = callback_status(options.status, is_payment, document_id)
            lines.append(f"  按 {status} 返回：{json.dumps(response_body, ensure_ascii=False)}")
            lines.append("─" * 78)
            safe_print("\n".join(lines))

            self._json(status, response_body)

        # ------------------------------------------------------------------

        def _json(self, status: int, body: dict[str, Any]) -> None:
            """回一个 JSON 响应。"""

            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """默认会往 stderr 打一行访问日志，我们自己的输出已经够了。"""

    return FakeBusinessHandler


def coerce_query_value(value: str) -> Any:
    """查询串里的值都是字符串，但像数字/布尔值的要按原类型发过去。

    审批表单严格按 JSON Schema 校验类型（Draft7，不认字符串形式的数字），
    ?JinEr=500 这种在 {"type": "number"} 上会直接 422。
    前导 0、正号、手机号这类不转，宁可留成字符串；复杂的类型请改用 POST JSON。
    """

    text = value.strip()
    if re.fullmatch(r"-?(0|[1-9]\d*)", text):
        return int(text)
    if re.fullmatch(r"-?(0|[1-9]\d*)\.\d+", text):
        return float(text)
    if text in ("true", "false"):
        return text == "true"
    return value


def payload_from_query(path: str) -> dict[str, Any]:
    """GET /start?... 的查询串就是这次的业务数据，方便直接用浏览器点。"""

    query = urllib.parse.urlparse(path).query
    return {
        key: coerce_query_value(value)
        for key, value in urllib.parse.parse_qsl(query, keep_blank_values=True)
    }


def default_env_path() -> Path:
    """默认配置文件放在脚本旁边，所以在哪个目录下敲命令都一样。"""

    return Path(__file__).resolve().with_name(".env")


def load_env_file(path: Path) -> dict[str, str]:
    """读一个 KEY=VALUE 的 .env：忽略空行与 # 注释，值两侧的引号去掉。"""

    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, raw = text.partition("=")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip().upper()] = value
    return values


# 每项：配置名、内置默认值、说明。.env 里的键名就是配置名的大写。
OPTIONS: list[tuple[str, Any, str]] = [
    ("center", "http://127.0.0.1:8090", "审批中心地址"),
    ("api_key", "", "租户 API Key（发起审批用，控制台租户详情页签发）"),
    ("process_id", "", "审批流 ID（发起审批用）"),
    ("action_code", "", "业务动作编码，留空表示只审批不回调"),
    ("admin_key", "", "管理密钥，填了就在启动时列出可选的审批流与动作"),
    ("host", "127.0.0.1", "监听地址"),
    ("port", 9000, "监听端口"),
    ("pay_path", "/pay", "支付回调的路径，要与业务动作的相对路径一致"),
    ("status", 200, "回调返回的状态码，填 500 可以测执行记录的失败分支"),
    ("delay", 0.0, "回调收到后先等几秒再回，用来测业务动作的超时（timeout_ms）"),
    ("token_header", "X-Service-Token", "Service Token 放在哪个请求头"),
    ("expect_token", "", "期望的 Service Token，收到回调时核对并打印 √/×"),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """命令行 > 配置文件 > 内置默认值。

    每次都要敲 --api-key --process-id 太烦，把它们写进 test_backcall/.env 就不用带了。
    """

    parser = argparse.ArgumentParser(description="假业务系统：发起审批 + 收支付回调（联调用）")
    parser.add_argument(
        "--env",
        default=None,
        help="配置文件路径，默认脚本同目录的 .env",
    )
    for name, default, help_text in OPTIONS:
        # 命令行默认给 None，才能区分"没传"和"传了空值"
        parser.add_argument(f"--{name.replace('_', '-')}", default=None, help=f"{help_text}（默认 {default!r}）")
    args = parser.parse_args(argv)

    env_path = Path(args.env) if args.env else default_env_path()
    file_values = load_env_file(env_path)

    resolved: dict[str, Any] = {"env_path": env_path, "env_found": env_path.is_file()}
    for name, default, _ in OPTIONS:
        from_cli = getattr(args, name)
        from_file = file_values.get(name.upper())
        if from_cli is not None:
            # 命令行的值也是字符串，按默认值类型转一次：--port 9011 要变成 int
            resolved[name] = type(default)(from_cli)
        elif from_file not in (None, ""):
            resolved[name] = type(default)(from_file)
        else:
            resolved[name] = default
    return argparse.Namespace(**resolved)


def main() -> int:
    """起服务，直到 Ctrl+C。"""

    options = parse_args()
    server = ThreadingHTTPServer((options.host, options.port), make_handler(options))
    base = f"http://{options.host}:{options.port}"

    safe_print("假业务系统（联调用）：发起审批 + 收支付回调")
    safe_print(f"  网页面板：{base}/（点按钮发起审批、看收到的回调）")
    safe_print(f"  发起审批：GET/POST {base}/start")
    safe_print(f"  支付回调：POST {base}{options.pay_path}")
    safe_print(f"  回调返回：{options.status}{f'，先拖 {options.delay} 秒' if options.delay else ''}")
    if options.expect_token:
        safe_print(f"  核对：{options.token_header} 里应含 {options.expect_token}")
    safe_print("")
    # 一眼看出配置是从哪儿来的，省得改了 .env 却没生效还在这儿找原因
    safe_print(f"配置来源：{options.env_path}{'' if options.env_found else '（没有这个文件，走内置默认值）'}")
    safe_print(f"  审批中心：{options.center}")
    safe_print(f"  租户 API Key：{mask(options.api_key) if options.api_key else '（没配 —— /start 发起不了）'}")
    safe_print(f"  审批流 ID：{options.process_id or '（没配 —— /start 发起不了）'}")
    safe_print(f"  业务动作：{options.action_code or '（没配 —— 只审批，通过后不回调）'}")
    safe_print("")
    safe_print(f"租户的「回调基础地址」配成 {base}，业务动作相对路径配 {options.pay_path}（POST、成功状态码 200）。")
    safe_print(f"然后访问 {base}/start?payment_id=PAY-1&JinEr=12000 就能发起一笔审批。")
    safe_print("")
    list_catalog(options)
    safe_print("Ctrl+C 退出。")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        safe_print(f"\n共收到 {COUNT} 次回调，已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
