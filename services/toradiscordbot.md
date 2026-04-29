# ToraDiscordBot

「とらめも交流所」Discord サーバーの永続ロガー＆日次・週次サマリーBot（Node.js）。

## 構成

- `bot.js` — Discord bot 本体（メッセージ蓄積・スコアリング・サマリー投稿）
- `auto-update.py` — GitHub から最新版を自動取得するスクリプト

## 主な機能

- Discord メッセージを SQLite に永続保存
- スコアリング: `(reaction×2 + reply×1.5 + thread×3) × 時間減衰係数(24h以内: 1.2)`
- 日次・週次サマリーを Claude API で生成し Discord + ToraVault に投稿

## launchd

| ラベル | 種別 | 対象 |
|---|---|---|
| `com.toradiscordbot` | KeepAlive（常駐） | `bot.js` |
| `com.toradiscordbot-autoupdate` | 定時（自動更新） | `auto-update.py` |

```bash
# 再起動
launchctl stop com.toradiscordbot && launchctl start com.toradiscordbot

# ログ確認
tail -f ~/toradiscordbot/bot.log
```

## 環境変数

`~/.toradiscordbot.env` を参照。

## ランタイム

Node.js v22 LTS（`/opt/homebrew/opt/node@22/bin/node`）、`better-sqlite3` 使用
