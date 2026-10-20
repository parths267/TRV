#!/bin/bash
# Run as root. Applies the staged release now, or at 15:31 IST on a weekday session.
set -euo pipefail
install -m 755 /opt/stoxs8-staging/scripts/stoxs8-apply.sh /usr/local/bin/stoxs8-apply
install -m 755 /opt/stoxs8-staging/scripts/stoxs8-deploy.sh /usr/local/bin/stoxs8-deploy

dow=$(TZ=Asia/Kolkata date +%u)
hm=$((10#$(TZ=Asia/Kolkata date +%H%M)))
if [ "$dow" -le 5 ] && [ "$hm" -ge 915 ] && [ "$hm" -le 1530 ]; then
  now=$(date +%s)
  target=$(TZ=Asia/Kolkata date -d "today 15:31" +%s)
  delay=$((target - now))
  [ "$delay" -lt 1 ] && delay=1
  systemctl stop stoxs8-after-close.service 2>/dev/null || true
  systemctl reset-failed stoxs8-after-close.service 2>/dev/null || true
  systemd-run --unit=stoxs8-after-close --on-active="${delay}s" /usr/local/bin/stoxs8-apply
  echo "Market session is open. The release is staged and will go live at 15:31 IST."
else
  /usr/local/bin/stoxs8-apply
fi
