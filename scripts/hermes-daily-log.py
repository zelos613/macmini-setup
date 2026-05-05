#!/usr/bin/env python3
"""
Hermes 日次ログ作成スクリプト
毎日 ToraVault/hermes-logs/ に当日のログファイルを生成する
"""

import os
import subprocess
from datetime import date, datetime

VAULT = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
)
LOG_DIR = os.path.join(VAULT, "hermes-logs")

def get_service_status(label: str) -> str:
    """launchctl でサービス状態を確認"""
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return "✅ 稼働中"
        else:
            return "❌ 停止中"
    except Exception:
        return "⚠️ 確認不可"

def get_disk_usage() -> str:
    """ディスク使用量を取得"""
    try:
        result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            return f"使用: {parts[2]} / {parts[1]} ({parts[4]})"
    except Exception:
        pass
    return "取得不可"

def get_bot_log_tail() -> str:
    """toradiscordbot の最近のログを取得"""
    log_path = os.path.expanduser("~/toradiscordbot/bot.log")
    try:
        result = subprocess.run(
            ["tail", "-5", log_path],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        return "\n".join(f"  {l}" for l in lines if l.strip())
    except Exception:
        return "  (ログ取得不可)"

def create_daily_log():
    os.makedirs(LOG_DIR, exist_ok=True)

    today = date.today()
    filename = f"{today}.md"
    filepath = os.path.join(LOG_DIR, filename)

    # 既にファイルが存在する場合はスキップ（上書きしない）
    if os.path.exists(filepath):
        print(f"既存のログファイルをスキップ: {filepath}")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    torabot_status = get_service_status("com.toradiscordbot")
    hermes_status = get_service_status("com.hermesagent")
    disk = get_disk_usage()
    bot_log = get_bot_log_tail()

    content = f"""# Hermes 日次記録 — {today}

> 自動生成: {now}

## 今日のトピック

（この日に会話した内容・作業した内容が記録されます）

## 実施したこと

（Hermesが実行したタスクが記録されます）

## メモ・発見

（重要な気づきや発見が記録されます）

---

## システム状態 ({now} 時点)

| サービス | 状態 |
|---|---|
| com.toradiscordbot | {torabot_status} |
| com.hermesagent | {hermes_status} |

**ディスク使用量:** {disk}

**toradiscordbot 直近ログ:**
{bot_log}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"日次ログを作成しました: {filepath}")

if __name__ == "__main__":
    create_daily_log()
