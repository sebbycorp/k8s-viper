# k8s-viper handbook (Hugo)

Static environment handbook published to GitHub Pages.

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
| `layouts/` | Templates (design + handbook sections) |
| `assets/css/main.css` | Styles |
| `assets/js/app.js` | Node IP rewriting + TOC |
| `content/_index.md` | Home page entry |

Edit `data/cluster.yaml` for inventory changes, then rebuild.

Canonical markdown runbooks live under `../docs/` (not only this site):

- `platform-ui-access.md` — all ports
- `vault-eso-setup.md` — Vault + secret inventory
- `agentgateway-langfuse.md` — AI gateway + Langfuse
- `kagent-substrate.md` — OSS kagent + Agent Substrate
- `fortigate-agent.md` — home FortiGate SandboxAgent + FortiOS MCP
- `why-traefik.md` — Traefik vs kgateway
- `headlamp.md` — dashboard tokens
