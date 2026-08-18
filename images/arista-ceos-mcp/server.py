#!/usr/bin/env python3
"""Arista EOS eAPI MCP tools (STREAMABLE_HTTP :8084 /mcp).

Read-only show-command wrappers for the isolated Containerlab cEOS demo
(spine1 / leaf1 / leaf2). Auth: HTTP Basic. Node names come from env
(ARISTA_HOSTS_JSON / ARISTA_HOSTS + ARISTA_ALLOWED_NODES). The model
never supplies a URL or host. TLS verify defaults ON; disable only when
ARISTA_VERIFY_TLS is explicitly false. Never log or return the password.
No config commands, no generic CLI tool.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

DEFAULT_ALLOWED = ("spine1", "leaf1", "leaf2")
DEFAULT_EAPI_PATH = "/command-api"
MAX_ITEMS = 40
TIMEOUT = 25.0
NODE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
PREFIX_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?$")
RESERVED_HOST_KEYS = frozenset(
    {
        "username",
        "password",
        "user",
        "pass",
        "hosts",
        "nodes",
        "verify_tls",
        "allowed_nodes",
        "hosts_json",
    }
)

EXPECTED_TOOLS = (
    "arista_inventory",
    "arista_bgp_summary",
    "arista_interfaces",
    "arista_lldp_neighbors",
    "arista_routes",
    "arista_health",
)


def _err(msg: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": _redact(msg)}
    out.update(extra)
    return out


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _verify_tls() -> bool:
    """TLS verify is on unless explicitly disabled for this lab."""
    raw = os.environ.get("ARISTA_VERIFY_TLS")
    if raw is None or raw.strip() == "":
        return True
    return _truthy(raw)


def _timeout() -> float:
    raw = (os.environ.get("ARISTA_TIMEOUT") or "").strip()
    if not raw:
        return TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return TIMEOUT
    return value if value > 0 else TIMEOUT


def _shared_username() -> str:
    return (os.environ.get("ARISTA_USERNAME") or "").strip()


def _shared_password() -> str:
    return os.environ.get("ARISTA_PASSWORD") or ""


def _secret_values() -> list[str]:
    values = [_shared_password()]
    for node in _configured_hosts().values():
        password = node.get("password") or ""
        if password:
            values.append(password)
    return [v for v in values if v]


def _redact(text: Any) -> str:
    raw = str(text)
    for secret in _secret_values():
        if secret:
            raw = raw.replace(secret, "***")
    raw = re.sub(r"(?i)(authorization:\s*basic\s+)\S+", r"\1***", raw)
    raw = re.sub(r"(?i)(password|passwd|secret|token)\s*[:=]\s*\S+", r"\1=***", raw)
    raw = re.sub(r"://([^/@\s]+):([^/@\s]+)@", r"://\1:***@", raw)
    return raw


def _hosts_raw() -> str:
    return (
        os.environ.get("ARISTA_HOSTS_JSON")
        or os.environ.get("ARISTA_HOSTS")
        or ""
    ).strip()


def _allowed_nodes() -> tuple[str, ...]:
    raw = (os.environ.get("ARISTA_ALLOWED_NODES") or "").strip()
    if not raw:
        return DEFAULT_ALLOWED
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    return names or DEFAULT_ALLOWED


def _looks_like_url(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        "://" in lowered
        or lowered.startswith("//")
        or "/" in value
        or "@" in value
        or lowered.startswith("http")
    )


def _normalize_url(raw: str) -> tuple[str, str, str]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty host url")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("host url must be http(s) with a hostname")
    username = parsed.username or ""
    password = parsed.password or ""
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{parsed.hostname}:{parsed.port}"
    path = parsed.path if parsed.path and parsed.path != "/" else ""
    clean = urlunparse((parsed.scheme, netloc, path, "", "", "")).rstrip("/")
    return clean, username, password


def _node_entry(name: str, spec: Any) -> dict[str, str] | None:
    username = _shared_username()
    password = _shared_password()
    url = ""
    if isinstance(spec, str):
        url = spec
    elif isinstance(spec, dict):
        url = str(spec.get("url") or spec.get("host") or spec.get("eapi") or "")
        username = str(spec.get("username") or spec.get("user") or username)
        password = str(spec.get("password") or spec.get("pass") or password)
    else:
        return None
    if not url:
        return None
    clean, url_user, url_pass = _normalize_url(url)
    return {
        "name": name,
        "url": clean,
        "username": url_user or username,
        "password": url_pass or password,
    }


def _parse_hosts_mapping(payload: Any) -> dict[str, dict[str, str]]:
    hosts: dict[str, dict[str, str]] = {}
    if isinstance(payload, dict):
        nested = payload.get("hosts")
        if nested is None:
            nested = payload.get("nodes")
        if isinstance(nested, (dict, list)):
            return _parse_hosts_mapping(nested)
        for name, spec in payload.items():
            key = str(name).strip()
            if key.lower() in RESERVED_HOST_KEYS:
                continue
            entry = _node_entry(key, spec)
            if entry:
                hosts[key] = entry
        return hosts
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("node") or "").strip()
            if not name:
                continue
            entry = _node_entry(name, item)
            if entry:
                hosts[name] = entry
        return hosts
    return hosts


def _parse_hosts_pairs(raw: str) -> dict[str, dict[str, str]]:
    hosts: dict[str, dict[str, str]] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        name, url = part.split("=", 1)
        name = name.strip()
        entry = _node_entry(name, url.strip())
        if name and entry:
            hosts[name] = entry
    return hosts


def _configured_hosts() -> dict[str, dict[str, str]]:
    raw = _hosts_raw()
    if not raw:
        return {}
    if raw[0] in "[{":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return _parse_hosts_mapping(payload)
    return _parse_hosts_pairs(raw)


def _inventory() -> dict[str, dict[str, str]]:
    allowed = set(_allowed_nodes())
    return {name: spec for name, spec in _configured_hosts().items() if name in allowed}


def _resolve_node(node: str | None) -> dict[str, Any]:
    name = (node or "").strip()
    if not name:
        return _err("node is required")
    if _looks_like_url(name) or not NODE_NAME_RE.match(name):
        return _err("node must be an allowlisted name, not a URL or host")
    if name not in _allowed_nodes():
        return _err("node is not on the allowlist", node=name)
    spec = _inventory().get(name)
    if not spec:
        return _err("node is not in the configured inventory", node=name)
    return {"ok": True, "node": spec}


def _nodes_for(node: str | None) -> dict[str, Any]:
    if node is None or str(node).strip().lower() in {"", "all", "*"}:
        inventory = _inventory()
        if not inventory:
            return _err("no allowlisted nodes in ARISTA_HOSTS_JSON")
        return {"ok": True, "nodes": list(inventory.values())}
    resolved = _resolve_node(node)
    if not resolved.get("ok"):
        return resolved
    return {"ok": True, "nodes": [resolved["node"]]}


def _assert_show_only(command: str) -> str:
    cmd = " ".join((command or "").split())
    if not cmd:
        raise ValueError("empty command")
    if re.search(r"[;\n`|&]|\$\(|&&", cmd):
        raise ValueError("refusing metacharacters in command")
    head = cmd.split(None, 1)[0].lower()
    if head != "show":
        raise ValueError("only show commands are allowed")
    return cmd


def _eapi_path() -> str:
    path = (os.environ.get("ARISTA_EAPI_PATH") or DEFAULT_EAPI_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def _eapi(node_spec: dict[str, str], commands: list[str]) -> dict[str, Any]:
    name = node_spec.get("name") or ""
    try:
        cmds = [_assert_show_only(cmd) for cmd in commands]
    except ValueError as exc:
        return _err(str(exc), node=name)
    username = node_spec.get("username") or ""
    password = node_spec.get("password") or ""
    if not username or not password:
        return _err("ARISTA_USERNAME or ARISTA_PASSWORD is not set", node=name)
    url = (node_spec.get("url") or "") + _eapi_path()
    payload = {
        "jsonrpc": "2.0",
        "method": "runCmds",
        "params": {"version": 1, "cmds": cmds, "format": "json"},
        "id": 1,
    }
    import httpx

    try:
        with httpx.Client(verify=_verify_tls(), timeout=_timeout()) as client:
            response = client.post(
                url,
                json=payload,
                auth=(username, password),
                headers={"Accept": "application/json"},
            )
    except Exception as exc:  # noqa: BLE001 — redact any transport error
        return _err(f"request failed: {type(exc).__name__}: {_redact(exc)}", node=name)
    if response.status_code in (401, 403):
        return _err("Unauthenticated", node=name, http=response.status_code)
    if response.status_code >= 400:
        return _err(f"HTTP {response.status_code}", node=name, http=response.status_code)
    try:
        body = response.json()
    except ValueError:
        return _err("response was not JSON", node=name, http=response.status_code)
    if not isinstance(body, dict):
        return _err("response was not a JSON object", node=name)
    if body.get("error"):
        err = body["error"]
        if isinstance(err, dict):
            return _err(str(err.get("message") or "eAPI error"), node=name, code=err.get("code"))
        return _err("eAPI error", node=name)
    result = body.get("result")
    if not isinstance(result, list):
        return _err("eAPI result missing", node=name)
    return {"ok": True, "node": name, "url": node_spec.get("url"), "result": result}


def _call_node(node_spec: dict[str, str], commands: list[str]) -> dict[str, Any]:
    return _eapi(node_spec, commands)


def _uptime(version: dict[str, Any]) -> Any:
    for key in ("uptime", "upTime", "bootupTimestamp"):
        if key in version:
            return version.get(key)
    return None


def _compact_version(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "hostname": data.get("hostname") or data.get("hostName"),
        "model": data.get("modelName") or data.get("model"),
        "version": data.get("version"),
        "uptime": _uptime(data),
        "serial": data.get("serialNumber") or data.get("serial"),
        "architecture": data.get("architecture"),
        "system_mac": data.get("systemMacAddress"),
    }


def _vrf_default(payload: dict[str, Any]) -> dict[str, Any]:
    vrfs = payload.get("vrfs") or {}
    if isinstance(vrfs, dict):
        if "default" in vrfs and isinstance(vrfs["default"], dict):
            return vrfs["default"]
        for value in vrfs.values():
            if isinstance(value, dict):
                return value
    return payload if isinstance(payload, dict) else {}


def _compact_bgp(data: dict[str, Any]) -> dict[str, Any]:
    vrf = _vrf_default(data)
    peers_in = vrf.get("peers") or data.get("peers") or {}
    rows = []
    if isinstance(peers_in, dict):
        items = list(peers_in.items())
    elif isinstance(peers_in, list):
        items = [(p.get("peerAddress") or p.get("address") or "", p) for p in peers_in]
    else:
        items = []
    for address, peer in items[:MAX_ITEMS]:
        if not isinstance(peer, dict):
            continue
        rows.append(
            {
                "peer": address or peer.get("peerAddress"),
                "asn": peer.get("asn") or peer.get("peerAsn") or peer.get("remoteAs"),
                "state": peer.get("peerState") or peer.get("state"),
                "prefixes": peer.get("prefixAccepted")
                if "prefixAccepted" in peer
                else peer.get("prefixReceived"),
                "up_down": peer.get("upDownTime") or peer.get("upDown"),
            }
        )
    return {
        "router_id": vrf.get("routerId") or data.get("routerId"),
        "asn": vrf.get("asn") or data.get("asn"),
        "vrf": "default",
        "peers": rows,
        "peer_count": len(items),
    }


def _interface_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    interfaces = data.get("interfaceStatuses") or data.get("interfaces") or {}
    rows = []
    if isinstance(interfaces, dict):
        items = list(interfaces.items())
    elif isinstance(interfaces, list):
        items = [(i.get("name") or "", i) for i in interfaces]
    else:
        items = []
    for name, spec in items[:MAX_ITEMS]:
        if not isinstance(spec, dict):
            continue
        addrs = spec.get("interfaceAddress") or spec.get("addresses") or []
        ipv4 = []
        if isinstance(addrs, list):
            for addr in addrs:
                if isinstance(addr, dict):
                    primary = addr.get("primaryIp") or addr
                    ip = primary.get("address") if isinstance(primary, dict) else None
                    mask = primary.get("maskLen") if isinstance(primary, dict) else None
                    if ip:
                        ipv4.append(f"{ip}/{mask}" if mask is not None else ip)
        rows.append(
            {
                "name": name or spec.get("name"),
                "description": spec.get("description"),
                "status": spec.get("linkStatus")
                or spec.get("interfaceStatus")
                or spec.get("status"),
                "line": spec.get("lineProtocolStatus") or spec.get("protocolStatus"),
                "vlan": spec.get("vlan") or spec.get("vlanId"),
                "addresses": ipv4,
            }
        )
    return rows


def _compact_lldp(data: dict[str, Any]) -> list[dict[str, Any]]:
    neighbors = (
        data.get("lldpNeighbors")
        or data.get("tables")
        or data.get("neighbors")
        or []
    )
    rows = []
    if isinstance(neighbors, dict):
        iterable = []
        for port, entries in neighbors.items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        iterable.append({"port": port, **entry})
            elif isinstance(entries, dict):
                iterable.append({"port": port, **entries})
    elif isinstance(neighbors, list):
        iterable = neighbors
    else:
        iterable = []
    for item in iterable[:MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "port": item.get("port") or item.get("interface") or item.get("localPort"),
                "neighbor": item.get("neighborDevice")
                or item.get("neighbor")
                or item.get("systemName")
                or item.get("chassisId"),
                "neighbor_port": item.get("neighborPort")
                or item.get("portId")
                or item.get("remotePort"),
            }
        )
    return rows


def _compact_routes(data: dict[str, Any], prefix: str | None = None) -> dict[str, Any]:
    vrf = _vrf_default(data)
    routes_in = vrf.get("routes") or data.get("routes") or {}
    rows = []
    if isinstance(routes_in, dict):
        items = list(routes_in.items())
    elif isinstance(routes_in, list):
        items = [(r.get("prefix") or r.get("network") or "", r) for r in routes_in]
    else:
        items = []
    for dest, spec in items:
        if prefix and dest != prefix and not str(dest).startswith(prefix):
            continue
        if not isinstance(spec, dict):
            continue
        vias = spec.get("vias") or spec.get("via") or []
        hops = []
        if isinstance(vias, list):
            for via in vias[:8]:
                if isinstance(via, dict):
                    hops.append(
                        {
                            "nexthop": via.get("nexthopAddr") or via.get("nexthop"),
                            "interface": via.get("interface"),
                        }
                    )
        rows.append(
            {
                "prefix": dest or spec.get("prefix"),
                "type": spec.get("routeType") or spec.get("type"),
                "protocol": spec.get("routeLeaked") or spec.get("protocol"),
                "metric": spec.get("metric"),
                "preference": spec.get("preference"),
                "vias": hops,
            }
        )
        if len(rows) >= MAX_ITEMS:
            break
    return {"count": len(items), "shown": len(rows), "routes": rows, "prefix": prefix}


def _validate_prefix(prefix: str | None) -> dict[str, Any] | None:
    if prefix is None or str(prefix).strip() == "":
        return None
    value = str(prefix).strip()
    if not PREFIX_RE.match(value):
        return _err("prefix must be an IPv4 address or CIDR")
    octets = value.split("/", 1)[0].split(".")
    if any(not 0 <= int(part) <= 255 for part in octets):
        return _err("prefix must be an IPv4 address or CIDR")
    if "/" in value:
        mask = int(value.split("/", 1)[1])
        if mask > 32:
            return _err("prefix must be an IPv4 address or CIDR")
    return {"ok": True, "prefix": value}


def _map_nodes(node: str | None, commands: list[str], formatter) -> dict[str, Any]:
    selected = _nodes_for(node)
    if not selected.get("ok"):
        return selected
    rows = []
    for spec in selected["nodes"]:
        res = _call_node(spec, commands)
        if not res.get("ok"):
            rows.append({"ok": False, "node": spec.get("name"), "error": res.get("error")})
            continue
        formatted = formatter(res)
        if isinstance(formatted, dict):
            formatted.setdefault("ok", True)
            formatted.setdefault("node", spec.get("name"))
            rows.append(formatted)
        else:
            rows.append({"ok": True, "node": spec.get("name"), "data": formatted})
    return {"ok": True, "count": len(rows), "nodes": rows}


def arista_inventory() -> dict[str, Any]:
    """Hostname, model, EOS version, and uptime for every allowlisted node."""

    def fmt(res: dict[str, Any]) -> dict[str, Any]:
        version = (res.get("result") or [{}])[0] or {}
        return _compact_version(version if isinstance(version, dict) else {})

    return _map_nodes(None, ["show version"], fmt)


def arista_bgp_summary(node: str | None = None) -> dict[str, Any]:
    """eBGP neighbor state for one allowlisted node, or all nodes."""

    def fmt(res: dict[str, Any]) -> dict[str, Any]:
        data = (res.get("result") or [{}])[0] or {}
        return _compact_bgp(data if isinstance(data, dict) else {})

    return _map_nodes(node, ["show ip bgp summary"], fmt)


def arista_interfaces(node: str) -> dict[str, Any]:
    """Interface status and addresses for one allowlisted node."""
    selected = _nodes_for(node)
    if not selected.get("ok"):
        return selected
    if len(selected["nodes"]) != 1:
        return _err("arista_interfaces requires exactly one node")
    spec = selected["nodes"][0]
    res = _call_node(spec, ["show interfaces"])
    if not res.get("ok"):
        return res
    data = (res.get("result") or [{}])[0] or {}
    rows = _interface_rows(data if isinstance(data, dict) else {})
    return {"ok": True, "node": spec.get("name"), "count": len(rows), "interfaces": rows}


def arista_lldp_neighbors(node: str | None = None) -> dict[str, Any]:
    """LLDP neighbors for one allowlisted node, or all nodes."""

    def fmt(res: dict[str, Any]) -> dict[str, Any]:
        data = (res.get("result") or [{}])[0] or {}
        neighbors = _compact_lldp(data if isinstance(data, dict) else {})
        return {"neighbors": neighbors, "count": len(neighbors)}

    return _map_nodes(node, ["show lldp neighbors"], fmt)


def arista_routes(node: str, prefix: str | None = None) -> dict[str, Any]:
    """IPv4 routes for one allowlisted node. Optional CIDR/address filter."""
    selected = _nodes_for(node)
    if not selected.get("ok"):
        return selected
    if len(selected["nodes"]) != 1:
        return _err("arista_routes requires exactly one node")
    checked = _validate_prefix(prefix)
    if checked is not None and not checked.get("ok"):
        return checked
    want = None if checked is None else checked["prefix"]
    commands = ["show ip route"] if want is None else [f"show ip route {want}"]
    spec = selected["nodes"][0]
    res = _call_node(spec, commands)
    if not res.get("ok"):
        return res
    data = (res.get("result") or [{}])[0] or {}
    compact = _compact_routes(data if isinstance(data, dict) else {}, want)
    compact.update({"ok": True, "node": spec.get("name")})
    return compact


def arista_health() -> dict[str, Any]:
    """Concise reachability, version, BGP, and interface overview for all nodes."""

    def fmt(res: dict[str, Any]) -> dict[str, Any]:
        results = res.get("result") or []
        version = results[0] if len(results) > 0 and isinstance(results[0], dict) else {}
        bgp = results[1] if len(results) > 1 and isinstance(results[1], dict) else {}
        ifaces = results[2] if len(results) > 2 and isinstance(results[2], dict) else {}
        bgp_c = _compact_bgp(bgp)
        iface_rows = _interface_rows(ifaces)
        up = 0
        down = 0
        for row in iface_rows:
            status = str(row.get("status") or "").lower()
            line = str(row.get("line") or "").lower()
            if "up" in status or "connected" in status or line == "up":
                up += 1
            else:
                down += 1
        established = sum(
            1
            for peer in bgp_c.get("peers") or []
            if str(peer.get("state") or "").lower() == "established"
        )
        ident = _compact_version(version)
        return {
            "hostname": ident.get("hostname"),
            "model": ident.get("model"),
            "version": ident.get("version"),
            "uptime": ident.get("uptime"),
            "bgp_asn": bgp_c.get("asn"),
            "bgp_established": established,
            "bgp_peers": bgp_c.get("peer_count"),
            "interfaces_up": up,
            "interfaces_down": down,
        }

    return _map_nodes(
        None,
        ["show version", "show ip bgp summary", "show interfaces"],
        fmt,
    )


TOOL_FUNCS = {
    "arista_inventory": arista_inventory,
    "arista_bgp_summary": arista_bgp_summary,
    "arista_interfaces": arista_interfaces,
    "arista_lldp_neighbors": arista_lldp_neighbors,
    "arista_routes": arista_routes,
    "arista_health": arista_health,
}


def _self_check() -> None:
    if set(TOOL_FUNCS) != set(EXPECTED_TOOLS):
        missing = set(EXPECTED_TOOLS) - set(TOOL_FUNCS)
        extra = set(TOOL_FUNCS) - set(EXPECTED_TOOLS)
        raise SystemExit(f"tool set mismatch missing={missing} extra={extra}")
    if _verify_tls() is not True and os.environ.get("ARISTA_VERIFY_TLS") in (None, ""):
        raise SystemExit("TLS verify must default on")
    with open(__file__, encoding="utf-8") as fh:
        source = fh.read()
    banned = ("import " + "subprocess", "from " + "subprocess", "os." + "system(")
    if any(token in source for token in banned):
        raise SystemExit("generic command execution is not allowed")
    if "runCmds" not in source:
        raise SystemExit("eAPI runCmds missing")
    if set(TOOL_FUNCS) - set(EXPECTED_TOOLS):
        raise SystemExit("unexpected extra tools")


def build_mcp():
    from fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    mcp = FastMCP(name="arista-ceos")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    for name, func in TOOL_FUNCS.items():
        mcp.tool(name=name)(func)
    return mcp


def main() -> None:
    _self_check()
    if not _inventory():
        print(
            "Arista inventory empty; tools will error until ARISTA_HOSTS_JSON exists",
            file=sys.stderr,
        )
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8084"))
    mcp = build_mcp()
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check()
        print("arista-ceos-mcp self-check ok")
        sys.exit(0)
    main()
