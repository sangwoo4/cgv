#!/bin/bash
set -euxo pipefail
exec > /var/log/cgv-alarm-init.log 2>&1

dnf install -y git
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

git clone https://github.com/sangwoo4/cgv /opt/cgv-alarm
cd /opt/cgv-alarm

cat > .env <<ENV
TELEGRAM_BOT_TOKEN=${telegram_bot_token}
TELEGRAM_CHAT_ID=${telegram_chat_id}
DISCORD_WEBHOOK_URL=${discord_webhook_url}
ENV
chmod 600 .env

/usr/local/bin/uv sync --frozen

cat > /etc/systemd/system/cgv-alarm.service <<UNIT
[Unit]
Description=CGV cancellation/open alarm
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/cgv-alarm
ExecStart=/usr/local/bin/uv run cgv-alarm loop --interval ${poll_interval}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now cgv-alarm
