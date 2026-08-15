# viper-desktop (computer-use lab image)

Xvfb + openbox + Chromium + noVNC + a tiny computer-use HTTP API.

Intended tags:

- local / node import: `viper-desktop:dev`
- published name: `ghcr.io/sebbycorp/viper-desktop:dev`

The Deployment uses `viper-desktop:dev` with `imagePullPolicy: IfNotPresent` so a
node-imported image works. Import the image **before** the pod can start.

```bash
# on Viper
docker build -t viper-desktop:dev images/desktop-computer-use
docker save viper-desktop:dev | docker exec -i k3s-viper ctr images import -
```

Optional publish (not required for the lab path):

```bash
docker tag viper-desktop:dev ghcr.io/sebbycorp/viper-desktop:dev
```

VNC is lab-open (`x11vnc -nopw`). No password is stored in git or the image.
x11vnc listens on localhost only; expose noVNC `:6080` and the API `:18790`.

Run as uid 1000. Do not set `privileged: true`. Chromium uses `--no-sandbox`
(container is the isolation boundary).
