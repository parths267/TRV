#!/bin/bash
# Host firewall and SSH lock-down. Safe to run more than once.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

mkdir -p /etc/systemd/system/stoxs8-web.service.d
cat >/etc/systemd/system/stoxs8-web.service.d/bind.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/npm start -- --hostname 127.0.0.1 --port 3000
EOF

cat >/etc/ssh/sshd_config.d/99-stoxs8.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
DebianBanner no
ClientAliveInterval 300
ClientAliveCountMax 2
AllowUsers deploy LENOVO ubuntu
EOF
sshd -t
systemctl reload ssh

systemctl daemon-reload
systemctl restart stoxs8-web

ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from 35.235.240.0/20 to any port 22 proto tcp
ufw --force enable
# Drop an older rule that left SSH open to the internet.
ufw delete allow 22/tcp >/dev/null 2>&1 || true
ufw delete allow 22/tcp >/dev/null 2>&1 || true

apt-get update -qq
apt-get install -y -qq fail2ban
cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
port = 22
backend = systemd
maxretry = 4
findtime = 10m
bantime = 1h
ignoreip = 127.0.0.1/8 ::1 35.235.240.0/20
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

# Clear a finished deploy timer so the next release can schedule a new one.
systemctl stop stoxs8-after-close.timer stoxs8-after-close.service 2>/dev/null || true
systemctl reset-failed stoxs8-after-close.timer stoxs8-after-close.service 2>/dev/null || true
rm -f /run/systemd/transient/stoxs8-after-close.timer /run/systemd/transient/stoxs8-after-close.service
systemctl daemon-reload

echo '---LISTEN---'
ss -tlnp | grep -E ':3000|:8000|:22 |:80 |:443 ' || true
echo '---UFW---'
ufw status verbose
echo '---HOSTKEY---'
cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
