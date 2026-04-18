# macmini-setup

Mac mini（mame）上で動いているサービス・構成の全体管理リポジトリ。

## マシン概要

- **ホスト名**: macmini (mame)
- **OS**: macOS
- **用途**: 自宅サーバー / AI処理 / Bot運用

## 動いているサービス

### ToraBot (`~/torabot/`)
Discord 向けのパーソナルAIアシスタントBot。

| ファイル | 役割 |
|---|---|
| `discord_bot.py` | Discordボット本体 |
| `ingest.py` | データ取り込み処理 |

- **設定ファイル**: `~/.torabot.env`
- **ログ**: `~/torabot/*.log` / `*.err`
- **GitHubリポジトリ**: [torabot](https://github.com/zelos613/torabot)（予定）

### Ollama（ローカルLLM）
- **URL**: `http://localhost:11434`
- **使用モデル**: `gemma4:e4b`（ToraBot経由で呼び出し）

### iCloud Vault
- **パス**: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault`
- ToraBotがVaultへの読み書きに使用

## 外部API連携

| サービス | 用途 |
|---|---|
| Discord API | ToraBotのDiscord通信 |
| Grok API (xAI) | LLM補助（Ollama非対応時など） |

## 環境変数

`~/.torabot.env` で管理（シークレットは含めないこと）。
テンプレート → [`dotfiles/.torabot.env.template`](dotfiles/.torabot.env.template)

## ディレクトリ構成

```
macmini-setup/
├── CLAUDE.md          # このファイル：全体概要
├── services/          # 各サービスの詳細メモ
│   └── torabot.md
└── dotfiles/
    └── .torabot.env.template
```
