# k8s-viper handbook (Hugo)

Static site published to GitHub Pages: the **Agents** showcase
(`/agents/`), **MCP servers** (`/mcp-servers/`), and the lab handbook (`/handbook/`).

## Develop

```bash
# install Hugo extended if needed: https://gohugo.io/installation/
cd site
hugo server -D
# open http://localhost:1313/k8s-viper/
```

## Build

```bash
cd site
hugo --minify
# output: site/public/
```

## Content

| Path | Role |
|------|------|
| `hugo.toml` | Site config / baseURL / default Node IP |
| `data/cluster.yaml` | Tables: UIs, apps, ports, Vault paths, versions… |
| `data/agents.yaml` | SandboxAgent showcase inventory (path names + live facts only) |
| `layouts/` | Templates (Agents page + handbook sections) |
| `layouts/agents/` | `/agents/` showcase (list/section) |
| `layouts/mcp-servers/` | `/mcp-servers/` multiplex catalog |
| `static/mcp-servers/` | Live kubectl shots of viper-mcp CRs |
| `static/agents/` | Real Chromium shots copied from the demos repo — no generated art |
| `assets/css/main.css` | Styles |
| `assets/js/app.js` | Node IP rewriting + TOC |
| `content/_index.md` | Home page entry (handbook) |
| `content/agents/_index.md` | Agents showcase section |

Edit `data/cluster.yaml` for handbook inventory, `data/agents.yaml`
for the SandboxAgent showcase, then rebuild.

Public send-links:
[https://viper.maniak.ai/agents/](https://viper.maniak.ai/agents/) and
[https://viper.maniak.ai/mcp-servers/](https://viper.maniak.ai/mcp-servers/).
kagent UI `:30500` stays LAN-only. `/mcp` is LAN-only too.

Shots under `static/agents/` are live Chromium captures from
[kagent-agent-substrate-demos](https://github.com/sebbycorp/kagent-agent-substrate-demos).
Do not add generated, reconstructed, or AI-drawn images. hello-substrate,
fortigate, f5-bigip, and arista-ceos have no live shot — leave those
cards without a photo.

Canonical markdown runbooks live under `../docs/` (not only this site):

- `platform-ui-access.md` — all ports
- `vault-eso-setup.md` — Vault + secret inventory
- `agentgateway-langfuse.md` — AI gateway + Langfuse
- `kagent-substrate.md` — OSS kagent + Agent Substrate
- `fortigate-agent.md` — home FortiGate SandboxAgent + FortiOS MCP
- `f5-bigip-agent.md` — F5 BIG-IP VIP monitor
- `arista-ceos-agent.md` — read-only Arista cEOS Containerlab agent
- `mcp-servers/README.md` — multiplex MCP front door on :30100/mcp
- `why-traefik.md` — Traefik vs kgateway
- `headlamp.md` — dashboard tokens

Custom domain: `https://viper.maniak.ai/` (GitHub Pages + Let's Encrypt).
