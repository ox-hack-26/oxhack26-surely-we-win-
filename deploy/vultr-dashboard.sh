#!/bin/bash
# Run the ClinicDrift dashboard on a fresh Ubuntu 24.04 Vultr VM, at http://<VM IP>/.
#
# Either paste this whole file into "Cloud-Init User-Data" when deploying the VM, or run it as root
# over SSH (safe to run again; it updates to the latest commit). Then, to read Tiger Data, put the
# connection string in the VM's environment file (never in the repo) and restart:
#
#   sudo nano /etc/clinicdrift.env        # TIGER_DATABASE_URL=postgres://...  and  CLINICDRIFT_DATA_MODE=tiger
#   sudo systemctl restart clinicdrift-dashboard
#
# Until then it serves the sample-data/ files, labelled as offline mode. Logs: journalctl -u clinicdrift-dashboard
set -euo pipefail
BRANCH="${BRANCH:-dev}"
REPO_URL="https://github.com/ox-hack-26/oxhack26-surely-we-win-.git"
HOME_DIR=/opt/clinicdrift

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3-venv

id -u clinicdrift >/dev/null 2>&1 || useradd --system --home-dir "$HOME_DIR" --create-home clinicdrift
if [ -d "$HOME_DIR/repo/.git" ]; then
  git -C "$HOME_DIR/repo" fetch -q origin "$BRANCH"
  git -C "$HOME_DIR/repo" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$HOME_DIR/repo"
fi
python3 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install -q --upgrade pip
"$HOME_DIR/venv/bin/pip" install -q -r "$HOME_DIR/repo/dashboard/requirements.txt"
chown -R clinicdrift:clinicdrift "$HOME_DIR"

# Settings the service reads. Root-only, and not in git: the Tiger URL holds a password.
if [ ! -f /etc/clinicdrift.env ]; then
  cat > /etc/clinicdrift.env <<'EOF'
# ClinicDrift dashboard settings (not in git). After editing: systemctl restart clinicdrift-dashboard
# files = sample-data/ (offline); tiger = Tiger Data, which needs TIGER_DATABASE_URL.
CLINICDRIFT_DATA_MODE=files
TIGER_DATABASE_URL=
EOF
  chmod 600 /etc/clinicdrift.env
fi

cat > /etc/systemd/system/clinicdrift-dashboard.service <<EOF
[Unit]
Description=ClinicDrift dashboard (Streamlit)
After=network-online.target
Wants=network-online.target

[Service]
User=clinicdrift
WorkingDirectory=$HOME_DIR/repo/dashboard
EnvironmentFile=/etc/clinicdrift.env
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=$HOME_DIR/venv/bin/python -m streamlit run app.py --server.port 80 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
Restart=always

[Install]
WantedBy=multi-user.target
EOF

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp
fi
systemctl daemon-reload
systemctl enable --now clinicdrift-dashboard
systemctl restart clinicdrift-dashboard
echo "ClinicDrift dashboard: http://$(curl -s -4 ifconfig.me || hostname -I | cut -d' ' -f1)/"
