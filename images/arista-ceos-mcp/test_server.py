#!/usr/bin/env python3
"""Unit tests for arista-ceos-mcp (mocked eAPI, no live devices)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import server


LAB_HOSTS = {
    "spine1": "https://192.0.2.11",
    "leaf1": "https://192.0.2.12",
    "leaf2": "http://192.0.2.13",
}

SHOW_VERSION = {
    "hostname": "spine1",
    "modelName": "cEOSLab",
    "version": "4.32.0F",
    "uptime": 3600.5,
    "serialNumber": "N/A",
    "architecture": "x86_64",
    "systemMacAddress": "00:11:22:33:44:55",
}

SHOW_BGP = {
    "vrfs": {
        "default": {
            "routerId": "10.0.0.1",
            "asn": "65000",
            "peers": {
                "10.0.1.1": {
                    "peerState": "Established",
                    "prefixAccepted": 2,
                    "asn": "65101",
                    "upDownTime": 120,
                },
                "10.0.1.2": {
                    "peerState": "Idle",
                    "prefixAccepted": 0,
                    "asn": "65102",
                },
            },
        }
    }
}

SHOW_INTERFACES = {
    "interfaces": {
        "Ethernet1": {
            "description": "to leaf1",
            "interfaceStatus": "connected",
            "lineProtocolStatus": "up",
            "interfaceAddress": [{"primaryIp": {"address": "10.0.1.0", "maskLen": 31}}],
        },
        "Management0": {
            "description": "mgmt",
            "interfaceStatus": "connected",
            "lineProtocolStatus": "up",
            "interfaceAddress": [{"primaryIp": {"address": "192.0.2.11", "maskLen": 24}}],
        },
    }
}

SHOW_LLDP = {
    "lldpNeighbors": [
        {"port": "Ethernet1", "neighborDevice": "leaf1", "neighborPort": "Ethernet1"},
        {"port": "Ethernet2", "neighborDevice": "leaf2", "neighborPort": "Ethernet1"},
    ]
}

SHOW_ROUTES = {
    "vrfs": {
        "default": {
            "routes": {
                "10.0.1.0/31": {
                    "routeType": "connected",
                    "vias": [{"interface": "Ethernet1"}],
                },
                "10.1.1.0/24": {
                    "routeType": "eBGP",
                    "vias": [{"nexthopAddr": "10.0.1.1", "interface": "Ethernet1"}],
                },
            }
        }
    }
}


class EnvTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "ARISTA_HOSTS_JSON",
                "ARISTA_HOSTS",
                "ARISTA_USERNAME",
                "ARISTA_PASSWORD",
                "ARISTA_ALLOWED_NODES",
                "ARISTA_VERIFY_TLS",
                "ARISTA_TIMEOUT",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)
        os.environ["ARISTA_HOSTS_JSON"] = json.dumps(LAB_HOSTS)
        os.environ["ARISTA_USERNAME"] = "admin"
        os.environ["ARISTA_PASSWORD"] = "super-secret-lab-pass"
        os.environ["ARISTA_ALLOWED_NODES"] = "spine1,leaf1,leaf2"

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AllowlistTests(EnvTestCase):
    def test_inventory_is_allowlisted_lab_nodes(self) -> None:
        names = set(server._inventory())
        self.assertEqual(names, {"spine1", "leaf1", "leaf2"})

    def test_reject_unknown_node(self) -> None:
        res = server._resolve_node("spine99")
        self.assertFalse(res["ok"])
        self.assertIn("allowlist", res["error"])

    def test_reject_url_as_node(self) -> None:
        res = server._resolve_node("https://evil.example")
        self.assertFalse(res["ok"])
        self.assertIn("not a URL", res["error"])

    def test_reject_host_header_style(self) -> None:
        res = server._resolve_node("evil.example/command-api")
        self.assertFalse(res["ok"])

    def test_extra_host_in_json_is_ignored(self) -> None:
        extra = dict(LAB_HOSTS)
        extra["attacker"] = "https://203.0.113.9"
        os.environ["ARISTA_HOSTS_JSON"] = json.dumps(extra)
        self.assertNotIn("attacker", server._inventory())
        res = server._resolve_node("attacker")
        self.assertFalse(res["ok"])

    def test_hosts_alias_env(self) -> None:
        os.environ.pop("ARISTA_HOSTS_JSON")
        os.environ["ARISTA_HOSTS"] = "spine1=https://192.0.2.11,leaf1=https://192.0.2.12,leaf2=http://192.0.2.13"
        self.assertEqual(set(server._inventory()), {"spine1", "leaf1", "leaf2"})

    def test_nested_hosts_object(self) -> None:
        os.environ["ARISTA_HOSTS_JSON"] = json.dumps(
            {"username": "admin", "hosts": LAB_HOSTS}
        )
        self.assertEqual(set(server._inventory()), {"spine1", "leaf1", "leaf2"})
        self.assertNotIn("username", server._inventory())


class CommandGuardTests(EnvTestCase):
    def test_allow_show_version(self) -> None:
        self.assertEqual(server._assert_show_only("show version"), "show version")

    def test_reject_configure(self) -> None:
        with self.assertRaises(ValueError):
            server._assert_show_only("configure terminal")

    def test_reject_enable(self) -> None:
        with self.assertRaises(ValueError):
            server._assert_show_only("enable")

    def test_reject_semicolon(self) -> None:
        with self.assertRaises(ValueError):
            server._assert_show_only("show version; configure terminal")

    def test_eapi_rejects_config_before_http(self) -> None:
        spec = server._inventory()["spine1"]
        res = server._eapi(spec, ["configure terminal"])
        self.assertFalse(res["ok"])
        self.assertIn("show", res["error"])


class RedactionTests(EnvTestCase):
    def test_redact_replaces_password(self) -> None:
        text = server._redact("login failed for super-secret-lab-pass")
        self.assertNotIn("super-secret-lab-pass", text)
        self.assertIn("***", text)

    def test_http_error_does_not_leak_password(self) -> None:
        spec = server._inventory()["spine1"]

        class Boom(Exception):
            def __str__(self) -> str:
                return "POST https://admin:super-secret-lab-pass@192.0.2.11/command-api failed"

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                raise Boom()

        import sys
        import types

        fake = types.ModuleType("httpx")
        fake.Client = FakeClient
        with patch.dict(sys.modules, {"httpx": fake}):
            res = server._eapi(spec, ["show version"])
        self.assertFalse(res["ok"])
        blob = json.dumps(res)
        self.assertNotIn("super-secret-lab-pass", blob)
        self.assertNotIn("admin:super-secret", blob)

    def test_err_helper_redacts(self) -> None:
        res = server._err("bad password=super-secret-lab-pass")
        self.assertNotIn("super-secret-lab-pass", res["error"])


class TlsAndTimeoutTests(EnvTestCase):
    def test_verify_defaults_on(self) -> None:
        os.environ.pop("ARISTA_VERIFY_TLS", None)
        self.assertTrue(server._verify_tls())

    def test_verify_false_only_when_explicit(self) -> None:
        os.environ["ARISTA_VERIFY_TLS"] = "false"
        self.assertFalse(server._verify_tls())
        os.environ["ARISTA_VERIFY_TLS"] = "true"
        self.assertTrue(server._verify_tls())

    def test_timeout_default(self) -> None:
        self.assertEqual(server._timeout(), 25.0)


class PrefixTests(EnvTestCase):
    def test_valid_cidr(self) -> None:
        res = server._validate_prefix("10.1.1.0/24")
        self.assertTrue(res["ok"])

    def test_reject_command_injection(self) -> None:
        res = server._validate_prefix("10.0.0.0/24; configure")
        self.assertFalse(res["ok"])

    def test_reject_oversize_mask(self) -> None:
        res = server._validate_prefix("10.0.0.0/99")
        self.assertFalse(res["ok"])


class ToolTests(EnvTestCase):
    def _ok(self, spec, commands, mapping):
        results = []
        for cmd in commands:
            if cmd not in mapping:
                raise AssertionError(f"unexpected command {cmd}")
            results.append(mapping[cmd])
        return {"ok": True, "node": spec["name"], "url": spec["url"], "result": results}

    def test_inventory(self) -> None:
        def fake(spec, commands):
            return self._ok(spec, commands, {"show version": {**SHOW_VERSION, "hostname": spec["name"]}})

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_inventory()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        names = {row["node"] for row in res["nodes"]}
        self.assertEqual(names, {"spine1", "leaf1", "leaf2"})
        self.assertEqual(res["nodes"][0]["model"], "cEOSLab")

    def test_bgp_one_and_all(self) -> None:
        def fake(spec, commands):
            return self._ok(spec, commands, {"show ip bgp summary": SHOW_BGP})

        with patch.object(server, "_eapi", side_effect=fake):
            one = server.arista_bgp_summary("spine1")
            all_nodes = server.arista_bgp_summary()
        self.assertTrue(one["ok"])
        self.assertEqual(one["count"], 1)
        self.assertEqual(one["nodes"][0]["asn"], "65000")
        self.assertEqual(len(one["nodes"][0]["peers"]), 2)
        self.assertEqual(all_nodes["count"], 3)

    def test_interfaces_requires_node(self) -> None:
        res = server.arista_interfaces("")
        self.assertFalse(res["ok"])

    def test_interfaces_one_node(self) -> None:
        def fake(spec, commands):
            self.assertEqual(spec["name"], "leaf1")
            return self._ok(spec, commands, {"show interfaces": SHOW_INTERFACES})

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_interfaces("leaf1")
        self.assertTrue(res["ok"])
        self.assertEqual(res["node"], "leaf1")
        names = {row["name"] for row in res["interfaces"]}
        self.assertIn("Ethernet1", names)

    def test_lldp_all(self) -> None:
        def fake(spec, commands):
            return self._ok(spec, commands, {"show lldp neighbors": SHOW_LLDP})

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_lldp_neighbors()
        self.assertTrue(res["ok"])
        self.assertEqual(res["nodes"][0]["count"], 2)
        self.assertEqual(res["nodes"][0]["neighbors"][0]["neighbor"], "leaf1")

    def test_routes_prefix_filter(self) -> None:
        seen = []

        def fake(spec, commands):
            seen.append(commands)
            return self._ok(spec, commands, {"show ip route 10.1.1.0/24": SHOW_ROUTES})

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_routes("spine1", prefix="10.1.1.0/24")
        self.assertTrue(res["ok"])
        self.assertEqual(seen, [["show ip route 10.1.1.0/24"]])
        prefixes = [row["prefix"] for row in res["routes"]]
        self.assertEqual(prefixes, ["10.1.1.0/24"])

    def test_routes_rejects_bad_prefix_without_eapi(self) -> None:
        with patch.object(server, "_eapi") as mocked:
            res = server.arista_routes("spine1", prefix="10.0.0.0/24; reboot")
            mocked.assert_not_called()
        self.assertFalse(res["ok"])

    def test_health(self) -> None:
        def fake(spec, commands):
            self.assertEqual(
                commands, ["show version", "show ip bgp summary", "show interfaces"]
            )
            return {
                "ok": True,
                "node": spec["name"],
                "result": [SHOW_VERSION, SHOW_BGP, SHOW_INTERFACES],
            }

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_health()
        self.assertTrue(res["ok"])
        row = res["nodes"][0]
        self.assertEqual(row["bgp_established"], 1)
        self.assertEqual(row["bgp_peers"], 2)
        self.assertGreaterEqual(row["interfaces_up"], 1)

    def test_tool_error_is_per_node(self) -> None:
        def fake(spec, commands):
            if spec["name"] == "leaf2":
                return {"ok": False, "error": "request failed: ConnectError", "node": "leaf2"}
            return self._ok(spec, commands, {"show version": SHOW_VERSION})

        with patch.object(server, "_eapi", side_effect=fake):
            res = server.arista_inventory()
        self.assertTrue(res["ok"])
        by_name = {row["node"]: row for row in res["nodes"]}
        self.assertTrue(by_name["spine1"]["ok"])
        self.assertFalse(by_name["leaf2"]["ok"])
        self.assertIn("ConnectError", by_name["leaf2"]["error"])


class SelfCheckTests(EnvTestCase):
    def test_self_check(self) -> None:
        os.environ.pop("ARISTA_VERIFY_TLS", None)
        server._self_check()
        self.assertEqual(set(server.TOOL_FUNCS), set(server.EXPECTED_TOOLS))


if __name__ == "__main__":
    unittest.main()
