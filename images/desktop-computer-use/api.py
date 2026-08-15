#!/usr/bin/env python3
"""Tiny computer-use HTTP API for the lab desktop.

Talks to DISPLAY=:99 via xdotool / scrot. No auth in this process —
agentgateway is the front door.

  GET  /health
  GET  /screenshot          → image/png
  POST /click   {x, y, button?}
  POST /type    {text}
  POST /key     {key}

Also accepts the same paths under /desktop-api/ so a missing URLRewrite
still works.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DISPLAY = os.environ.get("DISPLAY", ":99")
SCREENSHOT_PATH = Path(os.environ.get("SCREENSHOT_PATH", "/tmp/desktop-screenshot.png"))
XDOTOOL = os.environ.get("XDOTOOL", "xdotool")
SCROT = os.environ.get("SCROT", "scrot")

BUTTON_ALIASES = {
    "left": "1",
    "middle": "2",
    "right": "3",
    "1": "1",
    "2": "2",
    "3": "3",
}


def env() -> dict[str, str]:
    out = os.environ.copy()
    out["DISPLAY"] = DISPLAY
    return out


def run(cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        env=env(),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def display_up() -> bool:
    try:
        proc = run(["xdpyinfo", "-display", DISPLAY], timeout=3.0)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def normalize_path(path: str) -> str:
    prefixes = ("/desktop-api/", "/desktop-api")
    for prefix in prefixes:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            rest = path[len(prefix) :] if path.startswith(prefix) else ""
            path = "/" + rest.lstrip("/") if rest else "/"
            break
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def parse_json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "viper-desktop-computer-use/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send(status, raw, "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def do_GET(self) -> None:  # noqa: N802
        path = normalize_path(urlparse(self.path).path)
        if path == "/health":
            ready = display_up()
            self._json(
                200 if ready else 503,
                {
                    "ok": ready,
                    "status": "ok" if ready else "display-unavailable",
                    "display": DISPLAY,
                },
            )
            return
        if path == "/screenshot":
            self._screenshot()
            return
        self._error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = normalize_path(urlparse(self.path).path)
        length = int(self.headers.get("Content-Length") or "0")
        if length > 1_000_000:
            self._error(413, "body too large")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            payload = parse_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(400, f"invalid json: {exc}")
            return

        if path == "/click":
            self._click(payload)
            return
        if path == "/type":
            self._type(payload)
            return
        if path == "/key":
            self._key(payload)
            return
        self._error(404, "not found")

    def _screenshot(self) -> None:
        SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SCREENSHOT_PATH.exists():
            SCREENSHOT_PATH.unlink()
        proc = run([SCROT, "-o", str(SCREENSHOT_PATH)])
        if proc.returncode != 0 or not SCREENSHOT_PATH.is_file():
            self._error(
                500,
                f"scrot failed: {proc.stderr.strip() or proc.stdout.strip() or proc.returncode}",
            )
            return
        png = SCREENSHOT_PATH.read_bytes()
        self._send(200, png, "image/png")

    def _click(self, payload: dict[str, Any]) -> None:
        try:
            x = int(payload["x"])
            y = int(payload["y"])
        except (KeyError, TypeError, ValueError):
            self._error(400, "click requires integer x and y")
            return
        button_raw = payload.get("button", "1")
        button = BUTTON_ALIASES.get(str(button_raw).lower())
        if button is None:
            self._error(400, "button must be 1/2/3 or left/middle/right")
            return
        proc = run([XDOTOOL, "mousemove", str(x), str(y), "click", button])
        if proc.returncode != 0:
            self._error(500, f"xdotool click failed: {proc.stderr.strip() or proc.returncode}")
            return
        self._json(200, {"ok": True, "x": x, "y": y, "button": button})

    def _type(self, payload: dict[str, Any]) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or text == "":
            self._error(400, "type requires non-empty string text")
            return
        proc = run([XDOTOOL, "type", "--delay", "12", "--", text])
        if proc.returncode != 0:
            self._error(500, f"xdotool type failed: {proc.stderr.strip() or proc.returncode}")
            return
        self._json(200, {"ok": True, "chars": len(text)})

    def _key(self, payload: dict[str, Any]) -> None:
        key = payload.get("key")
        if not isinstance(key, str) or key == "":
            self._error(400, "key requires non-empty string key")
            return
        # xdotool key names (Return, ctrl+c, …). Do not treat this as a shell.
        proc = run([XDOTOOL, "key", "--", key])
        if proc.returncode != 0:
            self._error(500, f"xdotool key failed: {proc.stderr.strip() or proc.returncode}")
            return
        self._json(200, {"ok": True, "key": key})


def main() -> int:
    parser = argparse.ArgumentParser(description="computer-use HTTP API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "18790")))
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"computer-use api listening on {args.host}:{args.port} DISPLAY={DISPLAY}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _self_check() -> None:
    assert normalize_path("/health") == "/health"
    assert normalize_path("/desktop-api/health") == "/health"
    assert normalize_path("/desktop-api/screenshot") == "/screenshot"
    assert normalize_path("/desktop-api/") == "/"
    assert normalize_path("/desktop-api") == "/"
    assert normalize_path("/click") == "/click"


if __name__ == "__main__":
    raise SystemExit(main())
