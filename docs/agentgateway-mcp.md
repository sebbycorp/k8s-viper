# agentgateway MCP multiplex

One LAN MCP endpoint for every SandboxAgent tool server on Viper.

Same Gateway as OpenAI and Spark (`agentgateway-proxy` NodePort **30100**).
Not a second gateway. Not on [viper.maniak.ai](https://viper.maniak.ai/).

## Client URL

| | |
|--|--|
| URL | `http://172.16.10.135:30100/mcp` |
| Transport | Streamable HTTP |
| Auth | none (LAN only, same as `/spark`) |
| Git | `platform/agentgateway-ai/backend-viper-mcp.yaml` + `httproute-viper-mcp.yaml` |

Anything on the LAN that can hit `:30100` can invoke these tools (Fortigate, F5, Arista, cloud billing, k8s reads). Do not publish this path.

## What is behind it

kagent `RemoteMCPServer` objects already point at these ClusterIP Services. The gateway multiplexes them into one MCP session. With more than one target, tool names are prefixed `target_`.

| Prefix | Service | Talks to |
|--------|---------|----------|
| `fortigate_` | `fortigate-mcp.kagent:8084` | FortiGate 80F `172.16.10.1` |
| `f5-bigip_` | `f5-bigip-mcp.kagent:8084` | BIG-IP `172.16.10.10` |
| `arista-ceos_` | `arista-ceos-mcp.kagent:8084` | cEOS lab eAPI (Containerlab) |
| `aws-budget_` | `aws-budget-mcp.kagent:8084` | AWS us-east-2 billing / capacity |
| `servicenow_` | `servicenow-mcp.kagent:8084` | ServiceNow IT tickets |
| `gcp-budget_` | `gcp-budget-mcp.kagent:8084` | GCP us-east1 billing / capacity |
| `kagent-tools_` | `kagent-tools.kagent:8084` | stock k8s tools (hello-substrate) |

`failureMode: FailOpen` — a down MCP is skipped; the others stay up.

The MCP *servers* are pods in `kagent`. The *targets* (firewall, F5, cEOS, cloud APIs) stay outside the cluster.

## Cursor / Claude / Inspector

Streamable HTTP URL: `http://172.16.10.135:30100/mcp`

```json
{
  "mcpServers": {
    "viper": {
      "url": "http://172.16.10.135:30100/mcp"
    }
  }
}
```

MCP Inspector:

```bash
npx @modelcontextprotocol/inspector@0.21.2
```

Transport **Streamable HTTP**, URL `http://172.16.10.135:30100/mcp`. List tools. You should see prefixed names (`fortigate_…`, `arista-ceos_…`).

## kubectl

```bash
docker exec k3s-viper kubectl -n agentgateway-system get agentgatewaybackend viper-mcp
docker exec k3s-viper kubectl -n agentgateway-system get httproute viper-mcp
docker exec k3s-viper kubectl -n kagent get remotemcpserver
```

## Not this

- Do not add `/mcp` to the public Hugo site.
- Do not bump kagent / Substrate pins to “fix” a missing tool.
- Do not commit Vault values. MCP pods already get creds via ExternalSecret.

See also: [agentgateway-langfuse.md](agentgateway-langfuse.md) (LLM paths), [kagent-substrate.md](kagent-substrate.md).
