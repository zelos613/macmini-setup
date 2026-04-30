# macmini-setup

Mac mini（mame）上で動いているサービス・構成の全体管理リポジトリ。

## マシン概要

- **ホスト名**: macmini (mame)
- **OS**: macOS
- **用途**: 自宅サーバー / AI処理 / Bot運用

## 動いているサービス

### zelopersonal (`~/zelopersonal/`)
個人用AIアシスタントBot。Ollama / Grok API と連携。

| ファイル | 役割 |
|---|---|
| `discord_bot.py` | Discordボット本体 |
| `ingest.py` | データ取り込み処理（6/12/18/0時定時実行） |

- **launchd**: `com.zelopersonal-discord`（常駐）/ `com.zelopersonal-ingest`（定時）
- **設定ファイル**: `~/.torabot.env`
- **ログ**: `~/zelopersonal/*.log` / `*.err`

### toradiscordbot (`~/toradiscordbot/`)
Discordサーバー向けの多機能Bot（Node.js）。スケジューラ・スコアラー・サマライザー等。

- **launchd**: `com.toradiscordbot`（常駐）
- **設定ファイル**: `~/.toradiscordbot.env`
- **ログ**: `~/toradiscordbot/bot.log` / `bot.err`

### Ollama（ローカルLLM）
- **URL**: `http://localhost:11434`
- **launchd**: `homebrew.mxcl.ollama`（brew services 管理）
- **使用モデル**: `gemma4:e4b`（高精度）/ `gemma4:e2b`（高速）— zelopersonal 経由で呼び出し

### llama.cpp（ローカルLLM）
- **URL**: `http://localhost:8081`
- **モデル**: `~/.local/share/llama-models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf`
- **launchd**: 未登録（手動起動）
- **起動コマンド**: `llama-server --model ~/.local/share/llama-models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf --port 8081 --ctx-size 16384 --n-gpu-layers 0 --mmap --flash-attn on --threads 8`

### homeagent-monitor（ヘルスチェック）
- **場所**: `~/claude-agent/`
- **launchd**: `com.homeagent-monitor`（15分ごとに実行）
- **役割**: `com.zelopersonal-discord` / `com.toradiscordbot` の死活監視・自動修復
- **ログ**: `~/claude-agent/logs/monitor.log` / `actions.md`

### hermesagent（個人AI秘書）
- **場所**: `~/.hermes/`
- **launchd**: `com.hermesagent`（常駐 gateway）
- **役割**: パーソナルAIアシスタント。ターミナル・ブラウザ・ファイル操作等を統合制御
- **設定**: `~/.hermes/config.yaml`
- **スキル**: `~/.hermes/skills/` に永続化
- **LLM連携**: Ollama (gemma4:e2b/e4b), Claude API, 他

#### MCP サーバー
- **context-mode**: FTS5 検索・サンドボックス出力（98% トークン削減）
  - 11 ツール有効: `ctx_execute`, `ctx_batch_execute`, `ctx_search`, `ctx_fetch_and_index` 等
  - 登録コマンド: `hermes mcp add context-mode --command context-mode`

### iCloud Vault
- **パス**: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault`
- zelopersonal / hermesagent が Vault への読み書きに使用

## 外部API連携

| サービス | 用途 |
|---|---|
| Discord API | zelopersonal / toradiscordbot |
| Grok API (xAI) | LLM補助（Ollama非対応時など）|

## 環境変数

- `~/.torabot.env` — zelopersonal用（テンプレート: [`dotfiles/.torabot.env.template`](dotfiles/.torabot.env.template)）
- `~/.toradiscordbot.env` — toradiscordbot用

## ディレクトリ構成

```
macmini-setup/
├── CLAUDE.md          # このファイル：全体概要
├── services/          # 各サービスの詳細メモ
│   ├── zelopersonal.md
│   ├── toradiscordbot.md
│   ├── homeagent-monitor.md
│   └── auto-update.py / com.toradiscordbot-autoupdate.plist
└── dotfiles/
    └── .torabot.env.template
```
