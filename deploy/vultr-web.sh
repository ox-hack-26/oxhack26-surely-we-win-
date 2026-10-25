#!/bin/bash
# Serve the ClinicDrift 3D web app on the same Vultr VM as the dashboard, at http://<VM IP>:8080/.
#
# Run as root over SSH after vultr-dashboard.sh (safe to run again; it rebuilds from the latest
# commit). The app is static: it is built once here and served by a small Python web server. Only
# the IDRiD scan images are in the repo, so the app shows a placeholder where a licensed scan would be.
# Logs: journalctl -u clinicdrift-web
set -euo pipefail
BRANCH="${BRANCH:-dev}"
REPO_URL="https://github.com/ox-hack-26/oxhack26-surely-we-win-.git"
HOME_DIR=/opt/clinicdrift
PORT="${PORT:-8080}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 nodejs npm curl

id -u clinicdrift >/dev/null 2>&1 || useradd --system --home-dir "$HOME_DIR" --create-home clinicdrift
if [ -d "$HOME_DIR/repo/.git" ]; then
  git -C "$HOME_DIR/repo" fetch -q origin "$BRANCH"
  git -C "$HOME_DIR/repo" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$HOME_DIR/repo"
fi

# Build the static site (web/dist) from the committed data in web/public/data/.
cd "$HOME_DIR/repo/web"
npm ci --no-audit --no-fund
npm run build
chown -R clinicdrift:clinicdrift "$HOME_DIR"

cat > /etc/systemd/system/clinicdrift-web.service <<EOF
[Unit]
Description=ClinicDrift 3D web app (static files)
After=network-online.target
Wants=network-online.target

[Service]
User=clinicdrift
WorkingDirectory=$HOME_DIR/repo/web/dist
ExecStart=/usr/bin/python3 -m http.server $PORT --bind 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT"/tcp
fi
systemctl daemon-reload
systemctl enable --now clinicdrift-web
systemctl restart clinicdrift-web
echo "ClinicDrift 3D web app: http://$(curl -s -4 ifconfig.me || hostname -I | cut -d' ' -f1):$PORT/"
