# zelopersonal

個人用AIアシスタントBot（旧: torabot）。

## 構成

- `discord_bot.py` — Discord bot
- `ingest.py` — データ取り込み（定時実行）

## LLM連携

1. **Ollama**（優先）: `http://localhost:11434` / モデル: `gemma4:e4b`
2. **Grok API**（フォールバック）

## launchd

| ラベル | 種別 | 対象 |
|---|---|---|
| `com.zelopersonal-discord` | KeepAlive（常駐） | `discord_bot.py` |
| `com.zelopersonal-ingest` | 定時（6/12/18/0時） | `ingest.py` |

```bash
# 手動でロード/アンロード
launchctl load ~/Library/LaunchAgents/com.zelopersonal-discord.plist
launchctl unload ~/Library/LaunchAgents/com.zelopersonal-discord.plist
```

## 環境変数

`~/.torabot.env` を参照。テンプレートは [`../dotfiles/.torabot.env.template`](../dotfiles/.torabot.env.template)。
