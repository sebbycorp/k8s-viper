# Lab computer-use desktop for Viper.
# Intended tags:
#   viper-desktop:dev                         (local / ctr images import)
#   ghcr.io/sebbycorp/viper-desktop:dev       (published name; not required to deploy)
#
# Xvfb + x11vnc + openbox run as uid 1000 without privileged:true.
# Chromium uses --no-sandbox because the container is already the isolation
# boundary (no user-ns sandbox in this lab image). Do not set privileged: true.
# If a later gVisor Actor needs extra caps, add them then — not now.
#
# X11 does not need SYS_ADMIN here. /tmp and /dev/shm must be writable
# (Deployment mounts emptyDirs).
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    SCREEN_GEOMETRY=1280x800x24 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        fonts-dejavu-core \
        fonts-liberation \
        novnc \
        openbox \
        procps \
        python3 \
        python3-websockify \
        scrot \
        websockify \
        x11-utils \
        x11vnc \
        xdotool \
        xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash desktop \
    && mkdir -p /opt/computer-use /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix

COPY --chown=desktop:desktop api.py /opt/computer-use/api.py
COPY --chown=desktop:desktop entrypoint.sh /opt/computer-use/entrypoint.sh
COPY --chown=desktop:desktop novnc-index.html /usr/share/novnc/index.html

RUN chmod 0755 /opt/computer-use/entrypoint.sh /opt/computer-use/api.py

USER desktop
WORKDIR /home/desktop

EXPOSE 6080 18790

ENTRYPOINT ["/opt/computer-use/entrypoint.sh"]
