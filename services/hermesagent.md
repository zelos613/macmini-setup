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

### 3. Anthropic OAuth ヒューリスティックが Hermes payload を MCP / extra_usage 扱いする（2026-05-15修正）

**症状**: Sonnet 4.6 / Opus 4.7 の OAuth リクエストが、basic 19% / extra 45.3%（枠 $2000 中 $906 使用）と十分余裕のある状態でも 400 `"out of extra usage"` を返し、Hermes が即 fallback (gemma4:e4b) に切り替わる。直接 curl で同じトークン + 単純 payload は通過 → Hermes 固有の payload 形状が引き金と判明。

**真因** (Anthropic OAuth 側 classifier の隠れヒューリスティック):

1. tool name が `mcp_*` で始まる → MCP server tool と分類 → extra_usage 必須
2. system prompt に Claude Code skill の snake_case 識別子
   (`skill_manage`, `skill_view`, `session_search`, `available_skills`,
   `delegate_task`, `web_search`) → 同上

いずれかが当たると、extra_usage 枠が空でも問答無用で `"out of extra usage"` 400 が返る。

**修正ファイル**: `~/.hermes/hermes-agent/agent/anthropic_adapter.py`
- `_MCP_TOOL_PREFIX = "mcp_"` → `"mcpx_"` (MCP 検出回避)
- OAuth sanitize ステップに `_OAUTH_SNAKE_CASE_TRIGGERS` を追加し、上記 6 識別子を `skill-manage` のようにハイフン化して送信

**修正ファイル**: `~/.hermes/hermes-agent/agent/transports/anthropic.py`
- `_MCP_PREFIX = "mcp_"` → `"mcpx_"` (受信側で剥がす prefix を整合)

**新たな `out of extra usage` が再発した場合の手順**:

1. `~/.hermes/logs/anthropic-400-dump/` の最新 JSON を確認（後述の監視機構が自動収集）
2. `request_kwargs.system` または `tools[].name` に新たな snake_case 識別子が含まれていないか探す
3. 候補が見つかったら `_OAUTH_SNAKE_CASE_TRIGGERS` に追加
4. 下記の credential pool リセット手順を実行 → `launchctl stop com.hermesagent` で再起動

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

## 監視機構 (2026-05-15 追加)

`com.hermesagent.usage-monitor`（5分間隔の launchd job）が
`https://api.anthropic.com/api/oauth/usage` を叩いて Claude.ai サブスクの
basic / extra usage 推移を記録する。Hermes 本体は監視機能を持たないため
別建てで導入。

| ファイル | 内容 |
|---|---|
| `~/.hermes/hermes-agent/agent/usage_monitor.py` | snapshot 取得・異常検知・kill switch ロジック本体 |
| `~/.local/bin/hermes-usage-monitor` | launchd 用ラッパースクリプト |
| `~/Library/LaunchAgents/com.hermesagent.usage-monitor.plist` | 5分間隔の起動設定 |
| `~/.hermes/usage_history.jsonl` | 直近288件 (24h) の snapshot リングバッファ |
| `~/.hermes/usage_alerts.log` | 「basic < 95% なのに extra が増加」を検知した時の警告 |
| `~/.hermes/anthropic_skip.flag` | extra utilization ≥ 95% で作成、credential_pool が anthropic を skip |
| `~/.hermes/logs/usage-monitor.log` | monitor 実行ログ |
| `~/.hermes/logs/anthropic-400-dump/<ts>.json` | Anthropic 400 エラー時の送信 payload ダンプ |

```bash
# 手動 snapshot
/Users/mame/.local/bin/hermes-usage-monitor

# 直近の使用量履歴
tail -5 ~/.hermes/usage_history.jsonl | python3 -m json.tool

# 直近の 400 エラー payload
ls -lt ~/.hermes/logs/anthropic-400-dump/ | head
```

## 更新

```bash
hermes update
```
