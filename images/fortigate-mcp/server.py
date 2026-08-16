#!/usr/bin/env python3
"""FortiOS REST MCP tools (STREAMABLE_HTTP :8084 /mcp).

Thin wrappers around live FortiOS 7.4.11 paths on fw-maniak-hq.
Auth: Authorization Bearer $FORTIGATE_TOKEN. TLS verify off for the lab
self-signed cert (FORTIGATE_VERIFY_TLS=false). Never log or return the token.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

DEFAULT_HOST = "https://172.16.10.1"
MAX_ITEMS = 40
TIMEOUT = 25.0

# Live GET paths probed from Viper (2026-08-15). Do not invent others.
PATHS = {
    "system_status": "/api/v2/monitor/system/status",
    "performance": "/api/v2/monitor/system/performance/status",
    "resource_usage": "/api/v2/monitor/system/resource/usage",
    "cmdb_interface": "/api/v2/cmdb/system/interface",
    "monitor_interface": "/api/v2/monitor/system/interface",
    "cmdb_policy": "/api/v2/cmdb/firewall/policy",
    "monitor_policy": "/api/v2/monitor/firewall/policy",
    "address": "/api/v2/cmdb/firewall/address",
    "addrgrp": "/api/v2/cmdb/firewall/addrgrp",
    "service_custom": "/api/v2/cmdb/firewall.service/custom",
    "service_group": "/api/v2/cmdb/firewall.service/group",
    "router_ipv4": "/api/v2/monitor/router/ipv4",
    "router_static": "/api/v2/cmdb/router/static",
    "vpn_ipsec": "/api/v2/monitor/vpn/ipsec",
    "vpn_ssl": "/api/v2/monitor/vpn/ssl",
    "vpn_p1": "/api/v2/cmdb/vpn.ipsec/phase1-interface",
    "log_state": "/api/v2/monitor/log/device/state",
    "log_forticloud": "/api/v2/monitor/log/forticloud",
    "dhcp": "/api/v2/monitor/system/dhcp",
    "vip": "/api/v2/cmdb/firewall/vip",
    "current_admins": "/api/v2/monitor/system/current-admins",
}

# Probed broken — never call these.
BROKEN_PATHS = (
    "/api/v2/monitor/log/event",
    "/api/v2/monitor/log/threat",
    "/api/v2/cmdb/firewall/service/custom",
)

READ_TOOLS = (
    "fg_system_status",
    "fg_resource_usage",
    "fg_list_interfaces",
    "fg_interface_stats",
    "fg_list_policies",
    "fg_get_policy",
    "fg_policy_stats",
    "fg_list_addresses",
    "fg_list_addrgrp",
    "fg_list_services",
    "fg_list_routes",
    "fg_list_static_routes",
    "fg_vpn_status",
    "fg_dhcp_leases",
    "fg_list_vips",
    "fg_log_state",
    "fg_current_admins",
)

WRITE_TOOLS = (
    "fg_create_address",
    "fg_update_address",
    "fg_set_policy_status",
    "fg_create_policy",
    "fg_update_policy_comment",
)

EXPECTED_TOOLS = READ_TOOLS + WRITE_TOOLS

IFACE_CMDB_FIELDS = ("name", "status", "type", "ip", "vlanid", "role", "mode", "allowaccess")
IFACE_MON_FIELDS = ("name", "alias", "link", "speed", "tx_bytes", "rx_bytes", "tx_packets", "rx_packets")
POLICY_FIELDS = (
    "policyid",
    "name",
    "status",
    "srcintf",
    "dstintf",
    "srcaddr",
    "dstaddr",
    "service",
    "action",
    "schedule",
    "nat",
    "logtraffic",
    "comments",
)
ADDR_FIELDS = ("name", "type", "subnet", "fqdn", "comment", "associated-interface")
ADDRGRP_FIELDS = ("name", "member", "comment")
SVC_FIELDS = ("name", "protocol", "tcp-portrange", "udp-portrange", "comment")
SVCGRP_FIELDS = ("name", "member", "comment")
ROUTE_FIELDS = ("ip_mask", "gateway", "interface", "type", "distance", "metric")
STATIC_FIELDS = ("seq-num", "dst", "gateway", "device", "status", "distance", "comment")
VIP_FIELDS = ("name", "type", "extip", "extintf", "mappedip", "portforward", "extport", "mappedport", "comment")
DHCP_FIELDS = ("ip", "mac", "hostname", "expire_time", "interface", "status")
ADMIN_FIELDS = ("user", "type", "method", "src", "started")


def _host() -> str:
    return os.environ.get("FORTIGATE_HOST", DEFAULT_HOST).rstrip("/")


def _token() -> str:
    return os.environ.get("FORTIGATE_TOKEN", "")


def _verify_tls() -> bool:
    return os.environ.get("FORTIGATE_VERIFY_TLS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _names(value: Any) -> Any:
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict) and "name" in item:
                out.append(item["name"])
            else:
                out.append(item)
        return out
    return value


def _pick(row: Any, fields: tuple[str, ...]) -> Any:
    if not isinstance(row, dict):
        return row
    picked: dict[str, Any] = {}
    for key in fields:
        if key in row:
            picked[key] = _names(row[key])
    return picked


def compact(payload: Any, fields: tuple[str, ...] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"results": payload}
    meta = {
        k: payload[k]
        for k in ("status", "http_status", "serial", "version", "build", "vdom")
        if k in payload
    }
    results = payload.get("results", payload)
    if isinstance(results, list):
        total = len(results)
        items = results[:MAX_ITEMS]
        if fields:
            items = [_pick(row, fields) for row in items]
        out: dict[str, Any] = {**meta, "count": total, "results": items}
        if total > MAX_ITEMS:
            out["truncated"] = True
            out["returned"] = len(items)
        return out
    if isinstance(results, dict) and fields:
        results = _pick(results, fields)
    return {**meta, "results": results}


def dumps(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), default=str)


def _safe_body(response: Any) -> Any:
    try:
        data = response.json()
    except ValueError:
        text = response.text[:400]
        return {"text": text}
    if isinstance(data, dict):
        return {
            k: data[k]
            for k in ("status", "http_status", "error", "error_code", "message", "cli_error")
            if k in data
        } or {"status": data.get("status")}
    return {"body": str(data)[:400]}


def fortios(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if path in BROKEN_PATHS:
        return {"error": True, "message": "refusing broken FortiOS path", "path": path}
    token = _token()
    if not token:
        return {"error": True, "message": "FORTIGATE_TOKEN is not set"}
    import httpx

    url = f"{_host()}{path}"
    query = {"vdom": "root"}
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(verify=_verify_tls(), timeout=TIMEOUT) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=query,
                json=json_body,
            )
    except httpx.HTTPError as exc:
        return {"error": True, "path": path, "message": type(exc).__name__}
    if response.status_code >= 400:
        return {
            "error": True,
            "path": path,
            "http_status": response.status_code,
            "body": _safe_body(response),
        }
    try:
        data = response.json()
    except ValueError:
        return {"error": True, "path": path, "http_status": response.status_code, "message": "non-json"}
    if isinstance(data, dict):
        data.setdefault("http_status", response.status_code)
        return data
    return {"http_status": response.status_code, "results": data}


def named_list(value: str | list[Any]) -> list[dict[str, str]]:
    if isinstance(value, list):
        items = value
    else:
        items = [part.strip() for part in str(value).split(",") if part.strip()]
    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            out.append({"name": str(item["name"])})
        else:
            out.append({"name": str(item)})
    return out


def fg_system_status() -> str:
    """Read FortiGate hostname, version, serial, and optional performance."""
    status = compact(fortios("GET", PATHS["system_status"]))
    perf = fortios("GET", PATHS["performance"])
    if not perf.get("error") and perf.get("http_status") == 200:
        status["performance"] = compact(perf).get("results")
    return dumps(status)


def fg_resource_usage() -> str:
    """Read CPU / memory / session resource usage."""
    return dumps(compact(fortios("GET", PATHS["resource_usage"])))


def fg_list_interfaces() -> str:
    """List CMDB system interfaces (name, status, ip, type)."""
    return dumps(
        compact(
            fortios("GET", PATHS["cmdb_interface"], params={"format": "|".join(IFACE_CMDB_FIELDS)}),
            IFACE_CMDB_FIELDS,
        )
    )


def fg_interface_stats() -> str:
    """Read live interface counters from the monitor API."""
    return dumps(compact(fortios("GET", PATHS["monitor_interface"]), IFACE_MON_FIELDS))


def fg_list_policies() -> str:
    """List firewall policies (compact: id, name, status, zones, action)."""
    return dumps(
        compact(
            fortios("GET", PATHS["cmdb_policy"], params={"format": "|".join(POLICY_FIELDS)}),
            POLICY_FIELDS,
        )
    )


def fg_get_policy(policyid: int | None = None, name: str | None = None) -> str:
    """Get one firewall policy by policyid or name."""
    if policyid is not None:
        return dumps(compact(fortios("GET", f"{PATHS['cmdb_policy']}/{int(policyid)}"), POLICY_FIELDS))
    if name:
        payload = fortios("GET", PATHS["cmdb_policy"], params={"filter": f"name=={name}"})
        return dumps(compact(payload, POLICY_FIELDS))
    return dumps({"error": True, "message": "policyid or name is required"})


def fg_policy_stats() -> str:
    """Read firewall policy hit counters."""
    return dumps(compact(fortios("GET", PATHS["monitor_policy"])))


def fg_list_addresses() -> str:
    """List firewall address objects."""
    return dumps(
        compact(
            fortios("GET", PATHS["address"], params={"format": "|".join(ADDR_FIELDS)}),
            ADDR_FIELDS,
        )
    )


def fg_list_addrgrp() -> str:
    """List firewall address groups."""
    return dumps(
        compact(
            fortios("GET", PATHS["addrgrp"], params={"format": "|".join(ADDRGRP_FIELDS)}),
            ADDRGRP_FIELDS,
        )
    )


def fg_list_services() -> str:
    """List custom services and service groups (dot CMDB paths)."""
    custom = compact(
        fortios("GET", PATHS["service_custom"], params={"format": "|".join(SVC_FIELDS)}),
        SVC_FIELDS,
    )
    groups = compact(
        fortios("GET", PATHS["service_group"], params={"format": "|".join(SVCGRP_FIELDS)}),
        SVCGRP_FIELDS,
    )
    return dumps({"custom": custom, "group": groups})


def fg_list_routes() -> str:
    """List the live IPv4 routing table."""
    return dumps(compact(fortios("GET", PATHS["router_ipv4"]), ROUTE_FIELDS))


def fg_list_static_routes() -> str:
    """List configured static routes."""
    return dumps(
        compact(
            fortios("GET", PATHS["router_static"], params={"format": "|".join(STATIC_FIELDS)}),
            STATIC_FIELDS,
        )
    )


def fg_vpn_status() -> str:
    """Read IPsec monitor, SSL VPN monitor, and phase1-interface objects."""
    return dumps(
        {
            "ipsec": compact(fortios("GET", PATHS["vpn_ipsec"])),
            "ssl": compact(fortios("GET", PATHS["vpn_ssl"])),
            "phase1": compact(fortios("GET", PATHS["vpn_p1"])),
        }
    )


def fg_dhcp_leases() -> str:
    """List DHCP leases (truncated if large)."""
    return dumps(compact(fortios("GET", PATHS["dhcp"]), DHCP_FIELDS))


def fg_list_vips() -> str:
    """List firewall VIPs."""
    return dumps(
        compact(
            fortios("GET", PATHS["vip"], params={"format": "|".join(VIP_FIELDS)}),
            VIP_FIELDS,
        )
    )


def fg_log_state() -> str:
    """Read local log device state and FortiCloud log status."""
    return dumps(
        {
            "device": compact(fortios("GET", PATHS["log_state"])),
            "forticloud": compact(fortios("GET", PATHS["log_forticloud"])),
        }
    )


def fg_current_admins() -> str:
    """List admins currently logged in."""
    return dumps(compact(fortios("GET", PATHS["current_admins"]), ADMIN_FIELDS))


def fg_create_address(name: str, subnet: str, type: str = "ipmask", comment: str = "") -> str:
    """Create a firewall address object. Confirm with the operator first."""
    body: dict[str, Any] = {"name": name, "type": type, "subnet": subnet}
    if comment:
        body["comment"] = comment
    return dumps(compact(fortios("POST", PATHS["address"], json_body=body)))


def fg_update_address(
    name: str,
    subnet: str | None = None,
    type: str | None = None,
    comment: str | None = None,
) -> str:
    """Update an existing firewall address. Confirm with the operator first."""
    body: dict[str, Any] = {}
    if subnet is not None:
        body["subnet"] = subnet
    if type is not None:
        body["type"] = type
    if comment is not None:
        body["comment"] = comment
    if not body:
        return dumps({"error": True, "message": "nothing to update"})
    return dumps(compact(fortios("PUT", f"{PATHS['address']}/{name}", json_body=body)))


def fg_set_policy_status(policyid: int, status: str) -> str:
    """Enable or disable a firewall policy by policyid. Confirm first."""
    wanted = status.strip().lower()
    if wanted not in {"enable", "disable"}:
        return dumps({"error": True, "message": "status must be enable or disable"})
    return dumps(
        compact(
            fortios(
                "PUT",
                f"{PATHS['cmdb_policy']}/{int(policyid)}",
                json_body={"status": wanted},
            )
        )
    )


def fg_create_policy(
    name: str,
    srcintf: str,
    dstintf: str,
    srcaddr: str,
    dstaddr: str,
    service: str,
    action: str,
    comment: str = "",
    schedule: str = "always",
) -> str:
    """Create a firewall policy (no delete). Confirm with the operator first."""
    wanted = action.strip().lower()
    if wanted not in {"accept", "deny"}:
        return dumps({"error": True, "message": "action must be accept or deny"})
    body: dict[str, Any] = {
        "name": name,
        "srcintf": named_list(srcintf),
        "dstintf": named_list(dstintf),
        "srcaddr": named_list(srcaddr),
        "dstaddr": named_list(dstaddr),
        "service": named_list(service),
        "action": wanted,
        "schedule": schedule or "always",
        "status": "enable",
    }
    if comment:
        body["comments"] = comment
    return dumps(compact(fortios("POST", PATHS["cmdb_policy"], json_body=body)))


def fg_update_policy_comment(policyid: int, comment: str) -> str:
    """Set the comments field on a firewall policy. Confirm first."""
    return dumps(
        compact(
            fortios(
                "PUT",
                f"{PATHS['cmdb_policy']}/{int(policyid)}",
                json_body={"comments": comment},
            )
        )
    )


TOOL_FUNCS = {
    "fg_system_status": fg_system_status,
    "fg_resource_usage": fg_resource_usage,
    "fg_list_interfaces": fg_list_interfaces,
    "fg_interface_stats": fg_interface_stats,
    "fg_list_policies": fg_list_policies,
    "fg_get_policy": fg_get_policy,
    "fg_policy_stats": fg_policy_stats,
    "fg_list_addresses": fg_list_addresses,
    "fg_list_addrgrp": fg_list_addrgrp,
    "fg_list_services": fg_list_services,
    "fg_list_routes": fg_list_routes,
    "fg_list_static_routes": fg_list_static_routes,
    "fg_vpn_status": fg_vpn_status,
    "fg_dhcp_leases": fg_dhcp_leases,
    "fg_list_vips": fg_list_vips,
    "fg_log_state": fg_log_state,
    "fg_current_admins": fg_current_admins,
    "fg_create_address": fg_create_address,
    "fg_update_address": fg_update_address,
    "fg_set_policy_status": fg_set_policy_status,
    "fg_create_policy": fg_create_policy,
    "fg_update_policy_comment": fg_update_policy_comment,
}


def _self_check() -> None:
    paths = set(PATHS.values())
    for broken in BROKEN_PATHS:
        if broken in paths:
            raise SystemExit(f"broken path registered: {broken}")
    if any("firewall/service/custom" in p for p in paths):
        raise SystemExit("slash service path is registered")
    if PATHS["service_custom"] != "/api/v2/cmdb/firewall.service/custom":
        raise SystemExit("service custom must use the FortiOS dot path")
    if _host() == "" or "token" in _host().lower():
        raise SystemExit("invalid default host")
    if set(TOOL_FUNCS) != set(EXPECTED_TOOLS):
        missing = set(EXPECTED_TOOLS) - set(TOOL_FUNCS)
        extra = set(TOOL_FUNCS) - set(EXPECTED_TOOLS)
        raise SystemExit(f"tool set mismatch missing={missing} extra={extra}")
    source = open(__file__, encoding="utf-8").read()
    for needle in ("Authorization: Bearer ", "FORTIGATE_TOKEN="):
        if needle in source and needle == "FORTIGATE_TOKEN=":
            # env lookup is fine; a literal assignment is not
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith("FORTIGATE_TOKEN=") or "FORTIGATE_TOKEN = \"" in stripped:
                    raise SystemExit("literal token assignment in source")


def build_mcp():
    from fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    mcp = FastMCP(name="fortigate")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    for name, func in TOOL_FUNCS.items():
        mcp.tool(name=name)(func)
    return mcp


def main() -> None:
    _self_check()
    if not _token():
        print("FORTIGATE_TOKEN is not set; tools will return an error until the Secret exists", file=sys.stderr)
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8084"))
    mcp = build_mcp()
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check()
        print("fortigate-mcp self-check ok")
        sys.exit(0)
    main()
