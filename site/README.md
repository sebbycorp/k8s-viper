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
| `hugo.toml` | Site config / baseURL |
| `data/cluster.yaml` | Tables: UIs, apps, ports, versions… |
| `layouts/` | Templates (design) |
| `assets/css/main.css` | Styles |
| `assets/js/app.js` | Node IP rewriting + TOC |
| `content/_index.md` | Home page entry |

Edit `data/cluster.yaml` for inventory changes, then rebuild.
