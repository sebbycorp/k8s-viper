#!/bin/bash
# Start Xvfb, window manager, VNC/noVNC, computer-use API, optional Chromium.
# Lab-open: x11vnc runs with -nopw (no VNC password in the image or in git).
# VNC listens on 127.0.0.1 only; the Service exposes noVNC :6080 and the API :18790.
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
GEOMETRY="${SCREEN_GEOMETRY:-1280x800x24}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
API_PORT="${API_PORT:-18790}"
VNC_PORT="${VNC_PORT:-5900}"
START_BROWSER="${START_BROWSER:-1}"

mkdir -p /tmp/.X11-unix /tmp/desktop
chmod 1777 /tmp/.X11-unix || true

echo "starting Xvfb ${DISPLAY} ${GEOMETRY}"
Xvfb "${DISPLAY}" -screen 0 "${GEOMETRY}" -ac +extension RANDR +extension GLX \
  -nolisten tcp >/tmp/desktop/xvfb.log 2>&1 &

for _ in $(seq 1 50); do
  if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
  echo "Xvfb failed to start" >&2
  cat /tmp/desktop/xvfb.log >&2 || true
  exit 1
fi

echo "starting openbox"
openbox >/tmp/desktop/openbox.log 2>&1 &

echo "starting x11vnc (lab-open, localhost only, no password)"
# -nopw: no VNC password. Do not bake a password into the image or git.
# -localhost: VNC is not on the pod IP; websockify is the only front door.
x11vnc -display "${DISPLAY}" -forever -shared -nopw -localhost \
  -rfbport "${VNC_PORT}" -o /tmp/desktop/x11vnc.log >/tmp/desktop/x11vnc.stdout 2>&1 &

WEBSOCKIFY_BIN=""
for candidate in websockify /usr/bin/websockify /usr/bin/websockify3; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    WEBSOCKIFY_BIN="${candidate}"
    break
  fi
done
if [[ -z "${WEBSOCKIFY_BIN}" ]]; then
  echo "websockify not found" >&2
  exit 1
fi

NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
echo "starting noVNC/websockify on :${NOVNC_PORT} (web=${NOVNC_WEB})"
"${WEBSOCKIFY_BIN}" --web "${NOVNC_WEB}" --heartbeat 30 \
  "0.0.0.0:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" \
  >/tmp/desktop/websockify.log 2>&1 &

echo "starting computer-use API on :${API_PORT}"
python3 /opt/computer-use/api.py --port "${API_PORT}" \
  >/tmp/desktop/api.log 2>&1 &

if [[ "${START_BROWSER}" == "1" ]]; then
  CHROMIUM_BIN=""
  for candidate in chromium chromium-browser google-chrome; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      CHROMIUM_BIN="${candidate}"
      break
    fi
  done
  if [[ -n "${CHROMIUM_BIN}" ]]; then
    echo "starting ${CHROMIUM_BIN} (about:blank, --no-sandbox)"
    # --no-sandbox: Chromium's user-ns sandbox is not available as uid 1000
    # in this container. Isolation is the pod, not Chromium's SUID sandbox.
    # --disable-dev-shm-usage: k8s /dev/shm is small unless emptyDir is mounted.
    "${CHROMIUM_BIN}" \
      --no-sandbox \
      --disable-dev-shm-usage \
      --disable-gpu \
      --disable-software-rasterizer \
      --no-first-run \
      --no-default-browser-check \
      --disable-translate \
      --disable-infobars \
      --start-maximized \
      about:blank \
      >/tmp/desktop/chromium.log 2>&1 &
  else
    echo "chromium not found; desktop will stay at the window manager" >&2
  fi
fi

echo "desktop ready: noVNC :${NOVNC_PORT}  computer-use :${API_PORT}  DISPLAY=${DISPLAY}"

# If any supervisor child exits, fail the container so Kubernetes restarts it.
wait -n
echo "a desktop process exited; shutting down" >&2
exit 1
