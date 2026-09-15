#!/bin/bash
# t4g.nano(512MB)는 스왑 없이 dnf가 OOM으로 죽는다 — 스왑 먼저, 코드는 git 없이 tarball로.
set -euxo pipefail
exec > /var/log/cgv-alarm-init.log 2>&1

fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

mkdir -p /opt/cgv-alarm
curl -Ls https://github.com/sangwoo4/cgv/tarball/main | tar xz -C /opt/cgv-alarm --strip-components=1
cd /opt/cgv-alarm

cat > .env <<ENV
TELEGRAM_BOT_TOKEN=${telegram_bot_token}
TELEGRAM_CHAT_ID=${telegram_chat_id}
DISCORD_WEBHOOK_URL=${discord_webhook_url}
ENV
chmod 600 .env

/usr/local/bin/uv sync --frozen --no-dev

cat > /etc/systemd/system/cgv-alarm.service <<UNIT
[Unit]
Description=CGV cancellation/open alarm
After=network-online.target
Wants=network-online.target

[Service]
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/cgv-alarm
ExecStart=/usr/local/bin/uv run --frozen cgv-alarm loop --interval ${poll_interval}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now cgv-alarm
