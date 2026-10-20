#!/bin/bash
# Copy the staged release onto the live tree and restart Stoxs8.
# The database, Upstox token, and .env stay on the server.
set -euo pipefail
LIVE=/opt/stoxs8
STAGE=/opt/stoxs8-staging
exec 9>/var/lock/stoxs8-apply
flock -n 9 || { echo "Another Stoxs8 deploy is already running."; exit 1; }

test -f "$STAGE/apps/api/requirements.txt"
rsync -a --delete \
  --exclude .env \
  --exclude data \
  --exclude apps/api/.venv \
  --exclude apps/web/.next/cache \
  "$STAGE/" "$LIVE/"
chown -R stoxs8:stoxs8 "$LIVE"
chmod 600 "$LIVE/.env"
sudo -u stoxs8 "$LIVE/apps/api/.venv/bin/pip" install -q -r "$LIVE/apps/api/requirements.txt"
sudo -u stoxs8 "$LIVE/apps/api/.venv/bin/pip" install -q -e "$LIVE"
systemctl restart stoxs8-api stoxs8-web stoxs8-autotrader
sleep 4
curl -fsS http://127.0.0.1:8000/api/v1/health
echo
echo "Stoxs8 is live."
