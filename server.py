#!/usr/bin/env python3
"""本地 Agent Runtime HTTP 服务（零第三方依赖，Python 标准库即可）。

启动：
    python server.py                # 默认 http://127.0.0.1:8765/
    python server.py --port 9000
    python server.py --data-dir /tmp/demo --prefer-rule

打开页面后，除了浏览器本地的解析演示，还能看到「Agent Runtime 对话」面板：
    用户输入 → HTTPChannel → MessageBus → AgentLoop 多轮工具调用 → 回复 + trace
这正是面试官能现场点开、能解释每一层在干什么的形态。

静态页发布到公网时没有 Python 后端，页面会自动降级为纯浏览器模式，
不会报错——两种模式共用同一份前端代码。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deadline_bot.runtime.app import DeadlineAgent  # noqa: E402
from deadline_bot.runtime.channels import HTTPChannel  # noqa: E402

AGENT: DeadlineAgent
CHANNEL = HTTPChannel()

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "DeadlineBotRuntime/0.2"

    # ---------- 工具方法 ----------

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _static(self, relative: str) -> None:
        target = (DOCS / relative).resolve()
        # 目录穿越防护
        if DOCS.resolve() not in target.parents and target != DOCS.resolve():
            self._json({"error": "forbidden"}, 403)
            return
        if not target.is_file():
            self._json({"error": "not found", "path": relative}, 404)
            return
        content = target.read_bytes()
        ctype = STATIC_TYPES.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[http] " + (fmt % args) + "\n")

    # ---------- 路由 ----------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._static("index.html")
        elif path == "/api/health":
            info = AGENT.info()
            self._json({"ok": True, "runtime": info.to_dict(),
                        "turns": AGENT.turn_count, "mode": "agent-runtime"})
        elif path == "/api/state":
            self._json(AGENT.state())
        elif path == "/api/tasks":
            self._json({"tasks": AGENT.state()["tasks"]})
        elif path == "/api/trace":
            last = AGENT.last_result
            self._json({
                "trace": AGENT.last_trace.to_list(),
                "tools_used": last.tools_used if last else [],
                "session_key": last.session_key if last else "",
            })
        elif path == "/api/tools":
            self._json({"tools": AGENT.registry.definitions()})
        elif path == "/api/jobs":
            self._json({"jobs": [j.__dict__ for j in AGENT.scheduler.list()]})
        elif path.startswith("/"):
            self._static(path.lstrip("/"))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        payload = self._body()
        if path == "/api/chat":
            result, status = CHANNEL.handle(AGENT, payload)
            self._json(result, status)
        elif path == "/api/tick":
            replies = AGENT.tick()
            self._json({"replies": replies, "count": len(replies)})
        elif path == "/api/schedule":
            expr = str(payload.get("cron_expr") or "")
            message = str(payload.get("message") or "")
            if not expr or not message:
                self._json({"error": "需要 cron_expr 和 message"}, 400)
                return
            job = AGENT.scheduler.add(expr, message)
            self._json({"job": job.__dict__})
        else:
            self._json({"error": "not found"}, 404)


def main() -> None:
    global AGENT
    parser = argparse.ArgumentParser(description="DeadlineBot Agent Runtime HTTP 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None, help="任务/会话/定时数据目录")
    parser.add_argument("--prefer-rule", action="store_true", help="强制使用离线 RulePlanner")
    args = parser.parse_args()

    AGENT = DeadlineAgent(
        data_dir=args.data_dir or str(ROOT / "data"),
        prefer_rule=args.prefer_rule,
    )
    info = AGENT.info()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print("DeadlineBot Agent Runtime")
    print(f"  页面      {url}")
    print(f"  健康检查 {url}api/health")
    print(f"  对话 API  POST {url}api/chat  {{\"text\": \"今天先做什么\"}}")
    print(f"  模型      {info.llm}")
    print(f"  工具      {', '.join(info.tools)}")
    print(f"  数据目录  {info.data_dir}")
    print("Ctrl+C 停止\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
