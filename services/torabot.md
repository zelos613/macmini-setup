# ToraBot

Telegram + Discord 向けパーソナルAIアシスタント。

## 構成

- `bot.py` — Telegram bot（python-telegram-bot使用）
- `discord_bot.py` — Discord bot
- `ingest.py` — データ取り込み

## LLM連携

1. **Ollama**（優先）: `http://localhost:11434` / モデル: `gemma4:e4b`
2. **Grok API**（フォールバック）

## 起動・ログ

```bash
# 起動（バックグラウンド）
python bot.py >> bot.log 2>> bot.err &
python discord_bot.py >> discord_bot.log 2>> discord_bot.err &
python ingest.py >> ingest.log 2>> ingest.err &
```

## 環境変数

`~/.torabot.env` を参照。テンプレートは `dotfiles/.torabot.env.template`。
