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
| デフォルト | `claude-sonnet-4-6` | Anthropic (OAuth) |
| フォールバック | `gemma4:e4b` | Ollama (localhost:11434) |
| 圧縮・補助 | `claude-sonnet-4-6` | Anthropic (OAuth) |

## 認証（OAuth setup-token）

Anthropic API は **従量課金APIキー不要**。`claude setup-token` で発行した1年有効のOAuth setup-tokenで動作。

```bash
# トークン設定（claude setup-token で取得した sk-ant-oat01-... をセット）
hermes-set-longtoken <token>

# Hermesに再起動で反映
launchctl stop com.hermesagent && launchctl start com.hermesagent
```

**設定内容（`~/.hermes/.env`）**
```
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
ANTHROPIC_API_KEY=sk-ant-oat01-...   ← 同じトークン（credential poolが参照）
CLAUDE_CODE_OAUTH_TOKEN_EXPIRES_AT=<ms epoch>  ← 1年後
```

**suppressed_sources（`~/.hermes/auth.json`）**
```json
"suppressed_sources": {"anthropic": ["claude_code"]}
```
キーチェーンの短命トークンがpool上書きしないよう抑制。

## 既知バグ・修正履歴

### 1. context-1m beta × OAuth Bearer 非互換（2026-05-13修正）

**症状**: wiki-notifier cron jobがAnthropicに `context-1m-2025-08-07` betaヘッダーを付けて呼び出すと、API が 400 "This authentication style is incompatible with the long context beta header." を返す。両エントリが exhausted → 1時間全Anthropicリクエストブロック。

**修正ファイル**: `~/.hermes/hermes-agent/agent/anthropic_adapter.py`
- `build_anthropic_client()` の OAuth ブランチで `drop_context_1m_beta=True` を強制

**修正ファイル**: `~/.hermes/hermes-agent/agent/error_classifier.py`
- `oauth_long_context_beta_forbidden` パターンに `"incompatible"` を追加（`"not yet available"` のみだった）

### 2. X-Api-Key / Bearer 二重送信による 401（2026-05-14修正）

**症状**: `ANTHROPIC_API_KEY` に OAuth トークンをセットすると、Anthropic SDK のコンストラクタが `os.environ["ANTHROPIC_API_KEY"]` を自動読み込みして `self.api_key` にセット。`auth_token`（Bearer）と `api_key`（X-Api-Key）が **同時送信** され、Anthropic が 401 `"invalid x-api-key"` を返してcredential poolが再びexhausted。

**修正ファイル**: `~/.hermes/hermes-agent/agent/anthropic_adapter.py`
```python
# OAuth ブランチでクライアント生成後に api_key を None にリセット
client = _anthropic_sdk.Anthropic(**kwargs)
client.api_key = None  # X-Api-Key を抑制、Authorization: Bearer のみ送信
return client
```

**テスト**: `tests/agent/test_anthropic_adapter.py::TestOAuthClientAuthHeaders`
- `ANTHROPIC_API_KEY` が env にある状態でも X-Api-Key が送信されないことを実 SDK で検証

## credential pool exhausted 時のリセット手順

```python
import json
with open('/Users/mame/.hermes/auth.json') as f: data = json.load(f)
for e in data['credential_pool']['anthropic']:
    e.update({'last_status': None, 'last_status_at': None, 'last_error_code': None,
              'last_error_reason': None, 'last_error_message': None, 'last_error_reset_at': None})
with open('/Users/mame/.hermes/auth.json', 'w') as f: json.dump(data, f, indent=4)
```

その後 `launchctl stop com.hermesagent && launchctl start com.hermesagent` で再起動。

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
tail -f ~/.hermes/logs/errors.log
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
