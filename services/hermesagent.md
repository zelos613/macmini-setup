# hermesagent

zelopersonalの後継。Mac Mini全体の上位管理AIエージェント。

## 構成

- **本体**: `~/.hermes/hermes-agent/` (NousResearch/hermes-agent)
- **設定**: `~/.hermes/config.yaml`
- **環境変数**: `~/.hermes/.env`
- **スキル**: `~/.hermes/skills/`
  - `mac-manage/` — launchctl・ログ・システム監視
  - `smart-route/` — モデル自動切り替え (Ollama ↔ Claude Opus)

## LLM構成

| 用途 | モデル | プロバイダー |
|---|---|---|
| デフォルト | `gemma4:e2b` | Ollama (localhost:11434) |
| 複雑タスク | `claude-opus-4-7` | Anthropic API |
| 圧縮・補助 | `gemma4:e2b` | Ollama (localhost:11434) |

## launchd

| ラベル | 種別 | 対象 |
|---|---|---|
| `com.hermesagent` | KeepAlive（常駐） | `hermes gateway run` |

```bash
# 手動起動
launchctl load ~/Library/LaunchAgents/com.hermesagent.plist

# 再起動
launchctl stop com.hermesagent && launchctl start com.hermesagent

# ログ確認
tail -f ~/.hermes/logs/gateway.log
```

## Discord

- **トークン**: zelopersonalから流用 (`~/.hermes/.env` の `DISCORD_TOKEN`)
- **許可ユーザー**: `161700334173945856`
- **サーバー**: 既存のDiscordサーバー (Guild: 1050376422637711401)
- **ホームチャンネル**: `~/.hermes/.env` の `DISCORD_HOME_CHANNEL` で設定

## zelopersonalからの移行

- `com.zelopersonal-discord` → 停止・無効化済み
- `com.zelopersonal-ingest` → 停止・無効化済み
- `ingest.py` の機能 → hermesスキルとして今後再実装予定

## 更新

```bash
hermes update
```
