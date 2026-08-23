"""On/off for Beo agents. Never print secrets."""

from __future__ import annotations

import json
import os
import socket
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LEADS_POWER = REPO / "agents" / "leads-beo" / "home" / "power.json"
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
SOCIAL_CONTAINER = os.environ.get("BEO_SOCIAL_CONTAINER", "beo-social")


class _UnixHTTPConnection(HTTPConnection):
    def __init__(self, sock_path: str, timeout: float = 8.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._sock_path = sock_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._sock_path)
        self.sock = sock


def _docker(method: str, path: str) -> tuple[int, Any]:
    if os.name == "nt" or not os.path.exists(DOCKER_SOCK):
        return 0, None
    try:
        conn = _UnixHTTPConnection(DOCKER_SOCK)
        conn.request(method, path)
        res = conn.getresponse()
        raw = res.read()
        code = res.status
        conn.close()
    except OSError:
        return 0, None
    if not raw:
        return code, None
    try:
        return code, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return code, None


def docker_container_running(name: str) -> bool | None:
    """True/False if Docker answers; None if the socket is unavailable."""
    code, data = _docker("GET", f"/containers/{name}/json")
    if code == 0:
        return None
    if code == 404 or not isinstance(data, dict):
        return False
    if code != 200:
        return None
    state = data.get("State") or {}
    return bool(state.get("Running"))


def docker_start(name: str) -> bool:
    code, _ = _docker("POST", f"/containers/{name}/start")
    return code in {204, 304}


def docker_stop(name: str) -> bool:
    code, _ = _docker("POST", f"/containers/{name}/stop?t=15")
    return code in {204, 304}


def leads_is_on() -> bool:
    if not LEADS_POWER.is_file():
        return True
    try:
        data = json.loads(LEADS_POWER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(data.get("on", True))


def set_leads_on(on: bool) -> None:
    LEADS_POWER.parent.mkdir(parents=True, exist_ok=True)
    LEADS_POWER.write_text(
        json.dumps({"on": bool(on)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _pid_file_running(home: Path) -> bool:
    path = home / "gateway.pid"
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        pid = int(raw.get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def social_is_running(home: Path) -> bool:
    docker = docker_container_running(SOCIAL_CONTAINER)
    if docker is not None:
        return docker
    state_path = home / "gateway_state.json"
    if state_path.is_file():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if str(data.get("gateway_state") or "").lower() == "running":
                return True
        except (OSError, json.JSONDecodeError):
            pass
    if _pid_file_running(home):
        return True
    # Compose on the server binds control to 0.0.0.0 and keeps beo-social up.
    return (os.environ.get("BEO_CONTROL_HOST") or "").strip() == "0.0.0.0"
