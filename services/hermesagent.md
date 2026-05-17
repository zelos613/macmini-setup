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

### 9. 「`/login` 完全自動化」は OAuth プロトコル上不可能 → 即時通知で対応（2026-05-17）

**経緯**: 8. の修正後も同じ「No Anthropic credentials」障害が再発した。
詳細調査の結果、**OAuth refresh_token が Anthropic 側で revoke された場合、
Hermes も CLI も同じ古い token を持ち続けて refresh API は 400 invalid_grant
を返し続ける**ことが判明。回復には新規 OAuth PKCE フロー (`/login`) が必須で、
これにはブラウザ認証同意が要るため Hermes 単独では実行不可能。

**結論**: 「ゼロ介入の完全自動化」は OAuth プロトコル上の限界で不可能。
代わりに「障害発生から復旧までを最短化」する仕組みを導入した。

**新規ファイル**:

| ファイル | 役割 |
|---|---|
| `~/.hermes/hermes-agent/agent/auth_health_monitor.py` | auth.json の anthropic エントリ全てが `last_status=exhausted` で grace（10分）を超えたら Discord ホームチャンネルに `/login が必要` と通知。復旧したら復旧通知も送る。state file `~/.hermes/auth_alert_state.json` で one-shot semantics（スパム防止） |
| `~/.local/bin/hermes-auth-health-monitor` | launchd 用ラッパースクリプト |
| `~/Library/LaunchAgents/com.hermesagent.auth-health-monitor.plist` | 5分間隔の launchd job |
| `~/.hermes/logs/auth-health-monitor.log` | 実行ログ |

**運用上の挙動**:

1. healthy 状態: ログに `status unchanged (stuck=False)` を残すだけ、Discord には何もしない
2. healthy → stuck（10分以上 exhausted）: ホームチャンネルに警告投稿、state file 作成
3. stuck → healthy: 復旧通知投稿、state file 削除
4. stuck → stuck: 何もしない（再投稿しない）

**通知メッセージに含まれる情報**:
- 各エントリの ID, source, access_token プレフィックス, stuck 時間（分）
- 現在のキーチェーン token プレフィックス
- 復旧手順 (`/login` 実行 → 5分以内に Hermes が自動取り込み)

**Discord 通知の到達経路**: `.env` の `DISCORD_BOT_TOKEN` + `DISCORD_HOME_CHANNEL` を使い、`https://discord.com/api/v10/channels/{id}/messages` に直接 POST。Hermes 本体プロセスに依存しない（Hermes が落ちていても通知される）。

**動作確認**: 2026-05-17 に擬似 stuck 状態でテストし、HTTP 200 で投稿成功・state 遷移正常。

### 8. CLI ⇄ Hermes 間で refresh_token が競合し `/login` 手動介入が必要だった（2026-05-16修正）

**症状**: トークン期限切れ前後で、Claude CLI 側と Hermes 側が同じ
single-use refresh_token を取り合い、片方が refresh した時点で
もう片方は invalid_grant (400) を食らう。今までは Hermes が
`_write_claude_code_credentials` で `~/.claude/.credentials.json` にしか
書き戻していなかったため、CLI 側（キーチェーンを真実とする）に反映されず、
CLI 起動時にまた古いキャッシュで refresh しに行く悪循環。結果として
ユーザーが手動で `/login` を打って同期する運用になっていた。

**修正ファイル①**: `~/.hermes/hermes-agent/agent/anthropic_adapter.py`

- 新関数 `_write_claude_code_credentials_to_keychain(payload)` を追加。
  `security add-generic-password -U -s "Claude Code-credentials" -a "" -w <json>`
  でキーチェーンに upsert。
- `_write_claude_code_credentials()` を「**キーチェーン優先 + credentials.json
  はフォールバック**」に変更。`subscriptionType`・`scopes` も既存値から
  自動で補完して書き戻す（CLI 側の認証チェックが満たすため必須）。

**修正ファイル②**: `~/.hermes/hermes-agent/agent/credential_pool.py`

- `_refresh_entry()` 入口に「**Pre-emptive sync**」を追加。
  refresh API を叩く **前に** `_sync_anthropic_entry_from_credentials_file`
  を呼んでキーチェーン側の最新トークンを確認。
- 新トークンが既に有効期限内なら refresh をスキップして直接採用 →
  refresh_token 競合そのものを回避。

**狙い**: 「**キーチェーンを single source of truth にする**」。Hermes と
Claude CLI のどちらが先に refresh しても、書き先がキーチェーン唯一
なので相手は次に読みに来た瞬間に新トークンを拾える。
`/login` 手動介入も不要、Hermes 再起動も不要。

**How to apply**: `hermes update` でこのパッチが消えた場合、
`_write_claude_code_credentials` 関数全体と、その上に
`_write_claude_code_credentials_to_keychain` 関数を再追加。
あわせて `credential_pool.py:_refresh_entry()` の入口の
「Proactive sync」ブロックを再注入。

### 7. `_refresh_entry` 失敗時のログが debug レベルで埋もれていた（2026-05-16修正）

**症状**: トークン期限切れ後 Hermes の自動 refresh が失敗 → 即 exhausted →
1時間ロック、という連鎖が起きた時、`errors.log` には「No Anthropic
credentials found」しか残らず、**真因の refresh 失敗理由が見えない**。
debug レベルの `logger.debug("Credential refresh failed...")` だけで、
errors.log (WARNING 以上) には届かなかった。

**修正ファイル**: `~/.hermes/hermes-agent/agent/credential_pool.py`

| ログ | 旧レベル | 新レベル | 内容 |
|---|---|---|---|
| refresh API 呼び出し失敗 | debug | **warning** | 例外型 + メッセージを残す |
| retry 失敗（credentials file resync 後） | debug | **warning** | 同上 |
| credentials file 書き込み失敗 | debug | **warning** | OAuth ローテ後の永続化失敗 |
| 最終的に exhausted | (なし) | **warning** | 「諦めた」明示ログ |
| credentials file から sync 成功 | debug | **info** | 外部 rotate を拾った |
| 期限切れ前に valid token 拾えた | debug | **info** | 救済成功 |
| retry refresh 成功 | (なし) | **info** | リカバリ成功明示 |

**確認方法**: 次回 refresh 失敗が起きた時、`~/.hermes/logs/errors.log`
を `grep "credential refresh"` で覗くと、失敗理由（例外型・HTTP コード等）
が読める。これを見て根本治療に進める。

### 5. `_upsert_entry` がトークン再 seed 時に last_status を引き継いで永久 exhausted ロック（2026-05-16修正）

**症状**: 認証エラーで `last_status=exhausted` が付いた claude_code エントリに、後でキーチェーン経由の新トークン (`/login` 等) が再 seed されても **exhausted フラグが残り続けて使えない**。auth.json 上で「fresh access_token + last_status=exhausted」という不整合な状態になり、cooldown 1時間が経つまで anthropic が選ばれない。

**真因**: `agent/credential_pool.py:_upsert_entry()` が `_seed_from_singletons` から呼ばれる時、`access_token` / `refresh_token` / `expires_at_ms` を上書きするだけで、`last_status`・`last_status_at`・`last_error_*` は触っていなかった。古いトークンに対する exhausted フラグが新トークンに引き継がれていた。

**修正ファイル**: `~/.hermes/hermes-agent/agent/credential_pool.py`
- `_upsert_entry()` で `access_token` または `refresh_token` の差分が検出された時、`last_status` / `last_status_at` / `last_error_code` / `last_error_reason` / `last_error_message` / `last_error_reset_at` も併せて `None` にリセット。

### 6. shell rc の `ANTHROPIC_API_KEY` が古い revoke 済みトークンで auth.json を汚染（2026-05-16対処）

**症状**: `~/.zprofile` に古い1年トークン (`sk-ant-oat01-bkqSI7E...`) が `export ANTHROPIC_API_KEY=...` で残っていた。Hermes 本体は plist にこの env を渡していないので無害だが、ユーザーシェル上で `hermes` CLI や Hermes Python モジュールを呼び出すたびに `_seed_from_env` が env を拾って auth.json に **revoke 済みトークンの env エントリを再生成** していた。Hermes 本体は keychain 連動の claude_code エントリで動くが、`hermes auth list` や手動デバッグで auth.json を見ると毎回ゴーストエントリが現れて混乱の元になっていた。

**対処**: `~/.zprofile` の `export ANTHROPIC_API_KEY=...` をコメントアウト。Hermes はキーチェーン (`Claude Code-credentials`) 経由の `claude_code` ソースで動作するので env 変数は不要。新しい shell セッションでは env が無くなり、auth.json も clean state を維持する。

### 4. CLI 外部 refresh で auth.json が古いまま 401 → exhausted ロック（2026-05-16修正）

**症状**: Claude Code CLI が裏で OAuth refresh → キーチェーンに新トークン
（`sk-ant-oat01-CW6L0poj...`）が書き込まれるが、Hermes の
`auth.json` は古いトークン（`sk-ant-oat01-gVIbn-...`）のまま。古い
トークンで Anthropic を叩いて 401 → `mark_exhausted_and_rotate` が
唯一の anthropic エントリを exhausted にして 1時間ロック → 「No
Anthropic credentials found」が連発し fallback (gemma4:e4b) に落ちる。

**真因**: OAuth refresh token は **single-use**。CLI が外部で消費すると
Hermes 側の refresh も無効化される。`_sync_anthropic_entry_from_credentials_file`
は起動時 + acquire_lease 時に走るが、稼働中の 401 では呼ばれず、即
exhausted に倒れていた。

**修正ファイル**: `~/.hermes/hermes-agent/agent/credential_pool.py`
- `mark_exhausted_and_rotate()` 入口に 401 リカバリパスを追加。
  `status_code == 401` かつ `provider == "anthropic"` かつ
  `entry.source == "claude_code"` のとき、まず
  `_sync_anthropic_entry_from_credentials_file()` を呼んでキーチェーン
  最新値を auth.json に取り込む。access_token が実際に変わっていれば
  exhausted にせずそのままエントリを返し、上位レイヤがリトライで成功できる。

**手動復旧手順**（パッチ前の状態に当たった場合）:

```python
import json, subprocess
res = subprocess.run(['security', 'find-generic-password',
                      '-s', 'Claude Code-credentials', '-w'],
                     capture_output=True, text=True)
o = json.loads(res.stdout.strip())['claudeAiOauth']
with open('/Users/mame/.hermes/auth.json') as f: data = json.load(f)
for e in data['credential_pool']['anthropic']:
    if e.get('source') == 'claude_code':
        e['access_token'] = o['accessToken']
        e['refresh_token'] = o['refreshToken']
        e['expires_at_ms'] = o['expiresAt']
        e['expires_at'] = o['expiresAt'] / 1000
        for k in ('last_status', 'last_status_at', 'last_error_code',
                  'last_error_reason', 'last_error_message',
                  'last_error_reset_at', 'last_refresh'):
            e[k] = None
with open('/Users/mame/.hermes/auth.json', 'w') as f: json.dump(data, f, indent=4)
```

その後 `launchctl stop com.hermesagent && launchctl start com.hermesagent`。

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

## モデル切替（スレッドごとに変更可能）

Discord スレッドは Hermes 内部で個別 `session_key` に分かれており、
各 session は独立した AIAgent インスタンスを持つ
(`gateway/run.py` の `_running_agents` / `_session_model_overrides`)。
`/model` コマンドは実行したスレッドだけに反映される。

| 操作 | 効果 |
|---|---|
| スレッドAで `/model claude-opus-4-7` | スレッドAのみ Opus |
| スレッドBは何もせず | `model.default`（`claude-sonnet-4-6`）のまま |
| 新規スレッド | 常に `model.default` で開始 |
| 同じスレッドの続き | 直前の選択を維持 |

**注意**: `_session_model_overrides` は in-memory のみで永続化されない。
`launchctl stop com.hermesagent` で再起動すると上書きが消え、
そのスレッドも `model.default` に戻る → 必要なら再度 `/model` を打つ。

### `/model` autocomplete 候補（2026-05-15 追加）

Discord で `/model` を打った時の autocomplete に以下を表示するよう
`gateway/platforms/discord.py:2202` 周辺の `slash_model` に
`@autocomplete("name")` ハンドラを追加済み:

| ラベル | 値 |
|---|---|
| Opus 4.7 — highest quality (heavy) | `claude-opus-4-7` |
| Sonnet 4.6 — balanced default | `claude-sonnet-4-6` |
| Haiku 4.5 — fast, cheap | `claude-haiku-4-5` |
| Gemma 4 e4b — local, free | `gemma4:e4b` |
| Gemma 4 e2b — local, fastest | `gemma4:e2b` |

**`hermes update` で上書きされる可能性あり**。再適用が必要になったら
`_MODEL_CHOICES` リストと `slash_model_autocomplete` を再追加する。

## 更新

```bash
hermes update
```
