#!/bin/bash
#
# weekly-reboot.sh
# 毎週月曜05:00にMac Miniを再起動する
# launchd (com.macmini-setup.weekly-reboot) からroot権限で実行される
#

set -euo pipefail

LOG_FILE="$HOME/macmini-setup/logs/weekly-reboot.log"
BOOT_TIME=$(sysctl -n kern.boottime | awk '{print $4}' | tr -d ',')
NOW=$(date +%s)
UPTIME_DAYS=$(( (NOW - BOOT_TIME) / 86400 ))

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "===== 週次再起動 開始 ===="
log "連続稼働日数: ${UPTIME_DAYS}日"

# Discord通知（Alert Hub経由）
# このスクリプトはroot権限で動くため、discord-alert.pyをrootのまま実行すると
# pending-alerts.jsonl / discord-alert.log がroot所有になり、mameで動く
# flush-alerts等が書き込めなくなる。sudo -H -u mame でmame権限に降格して実行する。
sudo -H -u mame python3 "$HOME/.hermes/scripts/discord-alert.py" \
    --level info \
    --title "週次再起動" \
    --body "Mac Miniを再起動します（連続稼働: ${UPTIME_DAYS}日）" \
    2>/dev/null || true

log "Discord通知: 送信試行完了"

# 通知が届くまで少し待つ
sleep 5

log "再起動実行: /sbin/shutdown -r now"
# 本番では以下の行を有効化
/sbin/shutdown -r now
