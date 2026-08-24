"""Beo Agents control API. Local bind by default; 0.0.0.0 in Docker."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import agent_by_id, fleet, snapshot, start_agent, stop_agent
import leads_api
from leads_telegram import start_telegram_thread
from leads_schedule import start_schedule_thread

HOST = os.environ.get("BEO_CONTROL_HOST", "127.0.0.1")
PORT = int(os.environ.get("BEO_CONTROL_PORT", "8788"))


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _body(handler: BaseHTTPRequestHandler) -> bytes:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return b""
    return handler.rfile.read(min(length, 2_000_000))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[beo-control] " + (fmt % args) + "\n")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path in {"/", "/api/health"}:
                _json(
                    self,
                    200,
                    {
                        "ok": True,
                        "service": "beo-agents-control",
                        "daily_research": "server",
                    },
                )
                return
            if path == "/api/fleet":
                _json(self, 200, fleet())
                return
            if path.startswith("/api/leads"):
                code, payload = leads_api.handle_get(self.path)
                _json(self, code, payload)
                return
            if path.startswith("/api/agents/"):
                agent_id = path.split("/")[-1]
                row = agent_by_id(agent_id)
                if not row:
                    _json(self, 404, {"ok": False, "error": "סוכן לא בקטלוג"})
                    return
                _json(self, 200, snapshot(row))
                return
            _json(self, 404, {"ok": False, "error": "not found"})
        except Exception as exc:
            _json(self, 500, {"ok": False, "error": str(exc)[:400]})

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path.rstrip("/")
            if path.startswith("/api/leads"):
                code, payload = leads_api.handle_post(self.path, _body(self))
                _json(self, code, payload)
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[1] == "api" and parts[2] == "agents":
                agent_id, action = parts[3], parts[4]
                if action == "start":
                    _json(self, 200, start_agent(agent_id))
                    return
                if action == "stop":
                    _json(self, 200, stop_agent(agent_id))
                    return
            _json(self, 404, {"ok": False, "error": "not found"})
        except Exception as exc:
            _json(self, 500, {"ok": False, "error": str(exc)[:400]})


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Beo control http://{HOST}:{PORT}", flush=True)
    start_telegram_thread()
    start_schedule_thread()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
