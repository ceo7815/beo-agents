"""Live status for Beo Hermes agents. Never print secrets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "catalog" / "agents.json"


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def agent_by_id(agent_id: str) -> dict[str, Any] | None:
    for row in load_catalog().get("agents") or []:
        if str(row.get("id")) == agent_id:
            return row
    return None


def _home(row: dict[str, Any]) -> Path:
    return REPO / str(row.get("folder") or f"agents/{row['id']}")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid(home: Path) -> int | None:
    path = home / "gateway.pid"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        pid = int(raw.get("pid") or 0)
        return pid or None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _env_flags(home: Path) -> dict[str, bool]:
    path = home / ".env"
    flags = {"openai": False, "telegram": False, "gmail": False}
    secrets = home / "secrets"
    if (secrets / "gmail-token.json").is_file():
        flags["gmail"] = True
    if not path.is_file():
        return flags
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return flags
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "OPENAI_API_KEY" and value:
            flags["openai"] = True
        if key == "TELEGRAM_BOT_TOKEN" and value:
            flags["telegram"] = True
        if key == "GMAIL_REFRESH_TOKEN" and value:
            flags["gmail"] = True
    return flags


def _last_log(home: Path) -> str | None:
    log = home / "logs" / "gateway.log"
    if not log.is_file():
        return None
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-80:]):
        line = line.strip()
        if line:
            return line[:180]
    return None


def snapshot(row: dict[str, Any]) -> dict[str, Any]:
    home = _home(row)
    live = str(row.get("status") or "") == "live"
    pid = _read_pid(home) if live else None
    running = bool(pid and _pid_alive(pid))
    env = _env_flags(home) if live else {"openai": False, "telegram": False, "gmail": False}
    publish = str(row.get("publish") or "preview")
    agent_id = str(row.get("id") or "")
    if agent_id == "leads-beo":
        connections = [
            {
                "kind": "telegram",
                "label": "טלגרם (עדכונים בלבד)",
                "connected": env["telegram"],
            },
            {"kind": "openai", "label": "OpenAI", "connected": env["openai"]},
            {"kind": "gmail", "label": "Gmail API", "connected": env["gmail"]},
        ]
    else:
        connections = [
            {"kind": "telegram", "label": "טלגרם", "connected": env["telegram"]},
            {"kind": "openai", "label": "OpenAI", "connected": env["openai"]},
            {
                "kind": "instagram",
                "label": "אינסטגרם (פרסום)",
                "connected": publish == "meta",
            },
            {
                "kind": "facebook",
                "label": "פייסבוק (פרסום)",
                "connected": publish == "meta",
            },
        ]
    return {
        **row,
        "exists": home.is_dir(),
        "running": running,
        "pid": pid if running else None,
        "last_log": _last_log(home) if live else None,
        "connections": connections,
    }


def fleet() -> dict[str, Any]:
    catalog = load_catalog()
    agents = [snapshot(row) for row in catalog.get("agents") or []]
    running = sum(1 for a in agents if a.get("running"))
    live = sum(1 for a in agents if a.get("status") == "live")
    planned = sum(1 for a in agents if a.get("status") != "live")
    down = sum(1 for a in agents if a.get("status") == "live" and not a.get("running"))
    return {
        "company": catalog.get("company"),
        "line": catalog.get("line"),
        "site": catalog.get("site"),
        "counts": {
            "total": len(agents),
            "live": live,
            "running": running,
            "down": down,
            "planned": planned,
        },
        "agents": agents,
    }


def _hermes(row: dict[str, Any], action: str) -> dict[str, Any]:
    home = _home(row)
    profile = str(row.get("hermes_profile") or row["id"])
    if str(row.get("status")) != "live":
        return {"ok": False, "error": "הסוכן עדיין לא חי"}
    if not home.is_dir():
        return {"ok": False, "error": "תיקיית הסוכן חסרה"}
    env_file = home / ".env"
    if action == "start" and not env_file.is_file():
        return {"ok": False, "error": "חסר קובץ .env בתיקיית הסוכן"}
    if action == "start" and str(row.get("id")) == "leads-beo":
        # Telegram Q&A is the control API poller. Hermes gateway would duplicate replies.
        return {
            "ok": True,
            "action": "start",
            "agent": row["id"],
            "message": "Beo Leads רץ מ-Control. טלגרם לשאלות, Beo OS לאישורים.",
        }

    creation = 0
    if os.name == "nt" and action == "start":
        creation = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    (home / "logs").mkdir(parents=True, exist_ok=True)
    hermes = shutil.which("hermes")
    if not hermes:
        return {"ok": False, "error": "hermes לא נמצא ב-PATH"}
    cmd = [hermes, "-p", profile, "gateway", action]
    try:
        if action == "start":
            log_path = home / "logs" / "gateway-control.log"
            handle = log_path.open("a", encoding="utf-8")
            subprocess.Popen(
                cmd,
                cwd=str(home),
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=creation,
                close_fds=os.name != "nt",
            )
            return {"ok": True, "action": "start", "agent": row["id"]}
        completed = subprocess.run(
            cmd,
            cwd=str(home),
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "").strip()[:300]
            return {"ok": False, "error": err or "gateway stop נכשל"}
        return {"ok": True, "action": "stop", "agent": row["id"]}
    except FileNotFoundError:
        return {"ok": False, "error": "hermes לא נמצא ב-PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}


def start_agent(agent_id: str) -> dict[str, Any]:
    row = agent_by_id(agent_id)
    if not row:
        return {"ok": False, "error": "סוכן לא בקטלוג"}
    return _hermes(row, "start")


def stop_agent(agent_id: str) -> dict[str, Any]:
    row = agent_by_id(agent_id)
    if not row:
        return {"ok": False, "error": "סוכן לא בקטלוג"}
    return _hermes(row, "stop")


if __name__ == "__main__":
    json.dump(fleet(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
