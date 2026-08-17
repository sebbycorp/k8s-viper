#!/usr/bin/env python3
"""F5 BIG-IP iControl REST MCP tools (STREAMABLE_HTTP :8084 /mcp).

Read-only VIP / pool monitor for the lab BIG-IP at 172.16.10.10.
Auth: HTTP Basic $F5_USERNAME / $F5_PASSWORD. TLS verify off for the lab
self-signed cert (F5_VERIFY_TLS=false). Never log or return the password.
No tmsh, no generic path tool, no delete, no UCS backup.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_HOST = "https://172.16.10.10"
MAX_ITEMS = 40
TIMEOUT = 25.0

EXPECTED_TOOLS = (
    "f5_system",
    "f5_list_vips",
    "f5_vip_status",
    "f5_list_pools",
    "f5_pool_status",
    "f5_vip_brief",
)


def _host() -> str:
    return (os.environ.get("F5_HOST") or DEFAULT_HOST).rstrip("/")


def _user() -> str:
    return (os.environ.get("F5_USERNAME") or "").strip()


def _password() -> str:
    return os.environ.get("F5_PASSWORD") or ""


def _verify() -> bool:
    return os.environ.get("F5_VERIFY_TLS", "false").lower() in ("1", "true", "yes")


def _err(msg: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": msg}
    out.update(extra)
    return out


def _tm_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    if raw.startswith("~"):
        return raw
    if raw.startswith("/"):
        return "~" + raw.strip("/").replace("/", "~")
    return f"~Common~{raw}"


def _stat(entries: dict[str, Any], key: str) -> Any:
    node = (entries or {}).get(key) or {}
    if "description" in node:
        return node.get("description")
    if "value" in node:
        return node.get("value")
    nested = node.get("nestedStats", {}).get("entries")
    if isinstance(nested, dict):
        return nested
    return None


def _request(path: str) -> dict[str, Any]:
    if not _user() or not _password():
        return _err("F5_USERNAME or F5_PASSWORD is not set")
    url = _host() + path
    try:
        with httpx.Client(
            verify=_verify(),
            timeout=TIMEOUT,
            auth=(_user(), _password()),
        ) as client:
            r = client.get(url, headers={"Accept": "application/json"})
    except httpx.RequestError as exc:
        return _err(f"request failed: {type(exc).__name__}")
    if r.status_code in (401, 403):
        return _err("Unauthenticated", http=r.status_code)
    if r.status_code == 404:
        return _err("not found", http=404, path=path)
    if r.status_code >= 400:
        return _err(f"HTTP {r.status_code}", http=r.status_code)
    try:
        return {"ok": True, "data": r.json()}
    except ValueError:
        return _err("response was not JSON", http=r.status_code)


def f5_system() -> dict[str, Any]:
    """BIG-IP version and product (read-only)."""
    res = _request("/mgmt/tm/sys/version")
    if not res.get("ok"):
        return res
    entries = (res["data"] or {}).get("entries") or {}
    rows = []
    for key, val in list(entries.items())[:MAX_ITEMS]:
        nested = ((val or {}).get("nestedStats") or {}).get("entries") or {}
        rows.append(
            {
                "key": key.split("/")[-1],
                "product": _stat(nested, "product"),
                "version": _stat(nested, "version"),
                "build": _stat(nested, "build"),
            }
        )
    return {"ok": True, "host": _host(), "entries": rows}


def f5_list_vips() -> dict[str, Any]:
    """List LTM virtual servers (name, destination, pool, protocol)."""
    res = _request("/mgmt/tm/ltm/virtual")
    if not res.get("ok"):
        return res
    items = (res["data"] or {}).get("items") or []
    rows = []
    for it in items[:MAX_ITEMS]:
        rows.append(
            {
                "name": it.get("name"),
                "fullPath": it.get("fullPath"),
                "destination": it.get("destination"),
                "pool": it.get("pool"),
                "ipProtocol": it.get("ipProtocol"),
                "disabled": bool(it.get("disabled")),
                "enabled": not bool(it.get("disabled")),
            }
        )
    return {"ok": True, "count": len(items), "shown": len(rows), "vips": rows}


def f5_vip_status(name: str) -> dict[str, Any]:
    """Availability and enabled state for one virtual server."""
    tm = _tm_name(name)
    if not tm:
        return _err("name is required")
    path = f"/mgmt/tm/ltm/virtual/{quote(tm, safe='~')}/stats"
    res = _request(path)
    if not res.get("ok"):
        return res
    entries = (res["data"] or {}).get("entries") or {}
    if not entries:
        return _err("no stats entries", name=name)
    _, first = next(iter(entries.items()))
    nested = ((first or {}).get("nestedStats") or {}).get("entries") or {}
    return {
        "ok": True,
        "name": name,
        "availability": _stat(nested, "status.availabilityState"),
        "enabled": _stat(nested, "status.enabledState"),
        "reason": _stat(nested, "status.statusReason"),
        "destination": _stat(nested, "destination"),
        "clientside_bits_in": _stat(nested, "clientside.bitsIn"),
        "clientside_bits_out": _stat(nested, "clientside.bitsOut"),
        "clientside_cur_conns": _stat(nested, "clientside.curConns"),
    }


def f5_list_pools() -> dict[str, Any]:
    """List LTM pools (name, monitor, member count)."""
    res = _request("/mgmt/tm/ltm/pool")
    if not res.get("ok"):
        return res
    items = (res["data"] or {}).get("items") or []
    rows = []
    for it in items[:MAX_ITEMS]:
        members = it.get("membersReference") or {}
        rows.append(
            {
                "name": it.get("name"),
                "fullPath": it.get("fullPath"),
                "monitor": it.get("monitor"),
                "loadBalancingMode": it.get("loadBalancingMode"),
                "member_count": members.get("size"),
            }
        )
    return {"ok": True, "count": len(items), "shown": len(rows), "pools": rows}


def f5_pool_status(name: str) -> dict[str, Any]:
    """Pool availability plus member up/down."""
    tm = _tm_name(name)
    if not tm:
        return _err("name is required")
    stats = _request(f"/mgmt/tm/ltm/pool/{quote(tm, safe='~')}/stats")
    members = _request(f"/mgmt/tm/ltm/pool/{quote(tm, safe='~')}/members")
    out: dict[str, Any] = {"ok": True, "name": name}
    if stats.get("ok"):
        entries = (stats["data"] or {}).get("entries") or {}
        if entries:
            _, first = next(iter(entries.items()))
            nested = ((first or {}).get("nestedStats") or {}).get("entries") or {}
            out["availability"] = _stat(nested, "status.availabilityState")
            out["enabled"] = _stat(nested, "status.enabledState")
            out["reason"] = _stat(nested, "status.statusReason")
    else:
        out["stats_error"] = stats.get("error")
    if members.get("ok"):
        items = (members["data"] or {}).get("items") or []
        rows = []
        for it in items[:MAX_ITEMS]:
            rows.append(
                {
                    "name": it.get("name"),
                    "address": it.get("address"),
                    "state": it.get("state"),
                    "session": it.get("session"),
                }
            )
        out["members"] = rows
        out["member_count"] = len(items)
    else:
        out["members_error"] = members.get("error")
    if not stats.get("ok") and not members.get("ok"):
        return _err("pool stats and members both failed", name=name)
    return out


def f5_vip_brief() -> dict[str, Any]:
    """One-shot VIP list with availability. Never invent a VIP."""
    listed = f5_list_vips()
    if not listed.get("ok"):
        return listed
    rows = []
    for vip in listed.get("vips") or []:
        name = vip.get("fullPath") or vip.get("name") or ""
        st = f5_vip_status(name) if name else {"ok": False, "error": "missing name"}
        rows.append(
            {
                "name": vip.get("name"),
                "destination": vip.get("destination"),
                "pool": vip.get("pool"),
                "enabled": vip.get("enabled"),
                "availability": st.get("availability") if st.get("ok") else "unavailable",
                "status_error": None if st.get("ok") else st.get("error"),
            }
        )
    return {"ok": True, "count": listed.get("count"), "vips": rows}


TOOL_FUNCS = {
    "f5_system": f5_system,
    "f5_list_vips": f5_list_vips,
    "f5_vip_status": f5_vip_status,
    "f5_list_pools": f5_list_pools,
    "f5_pool_status": f5_pool_status,
    "f5_vip_brief": f5_vip_brief,
}


def _self_check() -> None:
    if set(TOOL_FUNCS) != set(EXPECTED_TOOLS):
        raise SystemExit("tool set mismatch")
    source = open(__file__, encoding="utf-8").read()
    if "subprocess" in source or "os.system" in source:
        raise SystemExit("generic command execution is not allowed")


def build_mcp():
    from fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    mcp = FastMCP(name="f5-bigip")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    for name, func in TOOL_FUNCS.items():
        mcp.tool(name=name)(func)
    return mcp


def main() -> None:
    _self_check()
    if not _user() or not _password():
        print("F5 creds not set; tools will error until the Secret exists", file=sys.stderr)
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8084"))
    mcp = build_mcp()
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check()
        print("f5-bigip-mcp self-check ok")
        sys.exit(0)
    main()
