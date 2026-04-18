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
- **使用モデル**: `gemma4:e4b`（zelopersonal経由で呼び出し）

### iCloud Vault
- **パス**: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault`
- zelopersonalがVaultへの読み書きに使用

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
│   └── toradiscordbot.md
└── dotfiles/
    └── .torabot.env.template
```
