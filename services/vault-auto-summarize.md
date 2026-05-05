# vault-auto-summarize

ToraVault の `raw-sources/` を監視し、新規ファイルを検知したら Claude Sonnet で要約を生成して `wiki/summaries/` に保存、Discord に通知する常駐サービス。Anthropic API がエラー時は Ollama (gemma4:e2b) にフォールバック。

## 構成

| 項目 | パス |
|---|---|
| スクリプト | `~/macmini-setup/scripts/vault-auto-summarize.py` |
| Python ランタイム | `~/macmini-setup/.venv/bin/python3`（Homebrew Python 3.14、`--copies` で実体バイナリ） |
| plist | `~/Library/LaunchAgents/com.toravault.auto-summarize.plist` |
| 環境変数 | `~/.hermes/.env`（`ANTHROPIC_API_KEY`, `DISCORD_BOT_TOKEN`） |
| 処理済みリスト | `~/.hermes/vault-processed-files.json` |
| ログ | `~/macmini-setup/logs/vault-summarize.log` / `.err` |
| 監視対象 | `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/` |
| 出力先 | `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/wiki/summaries/` |
| Discord 通知先 | チャンネル ID `1499328996234625074` |

## 主な動作

- 3 秒ごとに `raw-sources/` を再帰スキャン（`.md`, `.txt`, `.html`, `.json`, `.yaml`, `.yml`）
- `.icloud` プレースホルダーは `brctl download` で実体取得を試行（最大 30 秒待機）
- Claude Sonnet で要約生成 → 失敗時は Ollama にフォールバック
- 出力 Markdown は `raw-sources/` からの相対パス構造を維持
- 既存ファイルがあればタイムスタンプ付きで保存
- 60 秒ごとに heartbeat ログ（`scan/processed/new/retry_queue` のカウント）

## launchd

| ラベル | 種別 | 対象 |
|---|---|---|
| `com.toravault.auto-summarize` | KeepAlive（常駐） | `vault-auto-summarize.py` |

```bash
# 再起動
launchctl unload ~/Library/LaunchAgents/com.toravault.auto-summarize.plist
launchctl load   ~/Library/LaunchAgents/com.toravault.auto-summarize.plist

# ログ確認
tail -f ~/macmini-setup/logs/vault-summarize.log

# 処理済みリスト確認
python3 -c "import json; d=json.load(open('$HOME/.hermes/vault-processed-files.json')); print(len(d['processed']))"
```

## トラブルシューティング

### heartbeat に `scan=0` が出続ける

iCloud Drive への TCC アクセス権が無い。**専用 venv バイナリ (`~/macmini-setup/.venv/bin/python3`) に「フルディスクアクセス」を付与**する必要がある。詳しくは [docs/launchd-tcc-icloud.md](../docs/launchd-tcc-icloud.md)。

### Discord 通知が `HTTP エラー 403: error code: 1010`

Cloudflare WAF が Python urllib のデフォルト User-Agent をブロックしている。スクリプトの `notify_discord` で `User-Agent: ToraVaultAutoSummarize ...` ヘッダを送るようにしている。同種 Bot を作るときも `User-Agent` を明示すること。

### 起動ログだけ出てその後ログが止まる

`logging.FileHandler` のバッファリングが原因の可能性。`emit` ごとに `flush()` するよう wrap している。バッファ問題を疑うときは launchd を一度落として直接実行で再現を取る：

```bash
launchctl unload ~/Library/LaunchAgents/com.toravault.auto-summarize.plist
PYTHONUNBUFFERED=1 ~/macmini-setup/.venv/bin/python3 ~/macmini-setup/scripts/vault-auto-summarize.py
```

### テストファイルで強制的に動作確認

```bash
TS=$(date +%Y%m%d-%H%M%S)
TESTFILE=~/Library/Mobile\ Documents/com~apple~CloudDocs/ToraVault/raw-sources/test-${TS}.md
echo "# テスト" > "$TESTFILE"
# 数秒待って summaries/ に同名ファイルが出来ていれば OK
```

## 環境変数

`~/.hermes/.env` を参照（zelopersonal / hermesagent と共有）：

- `ANTHROPIC_API_KEY` — Claude Sonnet 呼び出し用
- `DISCORD_BOT_TOKEN` — Discord 通知用（zelopersonal の Bot トークン流用）
