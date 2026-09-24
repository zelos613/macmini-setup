# Dalamudプラグイン記事自動生成パイプライン - 引き継ぎ

作成日: 2026-05-18 (Hermes Agent から Claude Code CLI へ)

## このプロジェクトの目的

GitHub上で活発に更新されているDalamudプラグインを自動で発見し、
ブログ記事の下書きまでをWordPress (https://toramemoblog.com) に
自動投稿する。ゲーム内スクリーンショットだけ人間が後から差し込む。

**読者像**: FF14プレイヤー（ツール活用に興味がある層）
**ブログの文体サンプル**: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/articles/*.txt` (265本)

---

## 役割分担（重要）

このプロジェクトは2つのエージェントで分担する:

### Claude Code CLI (このセッション) の担当
- **実装・コーディング全般**
- Stage 2/3/4 のスクリプト作成
- 記事生成ロジックの調整（文体模倣、プロンプト設計）
- テスト実行・デバッグ
- 単発の `finder.py` 手動実行や `collect.py` の対話的呼び出し

### Hermes Agent の担当
- **cron実行・スケジュール運用**
- 週1の `finder.py` 自動実行（毎週月曜朝9時など）
- 結果の Discord 通知（home channel: torabot-memo）
- 月末の `monthly_roundup.py` 自動実行
- 障害検知・ログ監視

**理由**: Hermes Agent はすでに常駐(launchd)で動いており、cronjob機能と Discord 連携を内蔵している。Claude Code CLI は単発セッション型で常駐運用に向かない。

### cron化はClaude Code CLIではやらない
- launchd plist の作成は不要
- 代わりに Hermes Agent 側で `mcpx_cronjob` を使って登録する
- 引き継ぎ完了時に「Hermes Agent側で以下のcronを登録してください」というメモを残せばOK

---

## 全体設計（3ステージ）

```
[Stage 1: 発見]      [Stage 2: 素材収集]       [Stage 3: 執筆+投稿]
finder.py    →    collect.py    →    write_article.py + post_wp.py
GitHub探索        README/PR/コミット集約    Claude Opus生成 → WP下書き

[月次まとめ]
monthly_roundup.py — 月末に「今月の注目プラグイン○選」を生成
```

---

## 既存ファイル（実装済み）

### Stage 1: finder.py ✅ 完成
- 場所: `~/macmini-setup/scripts/dalamud/finder.py`
- 機能:
  - `gh api` 経由でDalamud関連リポジトリを検索（GITHUB_TOKEN不要、gh CLIで認証済み）
  - 直近30日の活動量でスコアリング: コミット×1 + マージPR×2 + オープンPR×1.5 + 新規Issue×0.5 + リリース×5 + スター×0.1
  - 除外リスト (`exclude.txt`) でフレームワーク本体・中国語専用リポを排除
  - 出力先: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/dalamud-active-YYYY-MM-DD.md`
- 実行例:
  ```bash
  cd ~/macmini-setup/scripts/dalamud
  python3 finder.py --scan 40 --top 20 --days 30
  ```

### Stage 1 関連: exclude.txt ✅
- 場所: `~/macmini-setup/scripts/dalamud/exclude.txt`
- 形式:
  - `owner/repo` 完全一致除外
  - `owner/` でowner全リポジトリ除外
  - `keyword:XXX` で description/name にキーワード含むものを除外

### Stage 2: collect.py ✅ 完成
- 場所: `~/macmini-setup/scripts/dalamud/collect.py`
- 機能: 指定したリポジトリの README, 最新リリース5件, 直近30日コミット, メタ情報を素材ファイル化
- 出力先: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/articles/dalamud-<owner>_<repo>-source.md`
- 実行例:
  ```bash
  python3 collect.py lokinmodar/Echoglossian
  ```
- テスト済み: Echoglossianで193行の素材生成成功

---

## 残作業（これからやること）

### Stage 3-A: write_article.py 未着手

**目的**: 素材ファイルから Claude Opus で記事Markdown原稿を生成

**仕様**:
- 入力: `dalamud-<owner>_<repo>-source.md` のパス
- 文体サンプル: `raw-sources/articles/` から3〜5本を自動選定して few-shot として渡す
  - 候補: `haseltweaks.txt`, `xiv-bossmod.txt`, `xivdeck.txt`, `penumbra.txt`, `vnavmesh.txt`, `craftimizer.txt`, `wrathcombo.txt`, `rotation-solver-reborn.txt`
  - 選定ロジック: ランダム3本 or 「単独プラグイン紹介系」を固定3本
- 出力構成:
  1. 導入（なぜ紹介するか）
  2. プラグインの概要
  3. 主な機能・特徴
  4. インストール方法（カスタムリポジトリURL等）
  5. 使い方の流れ
  6. **`<!-- SCREENSHOT: 〇〇画面 -->`** プレースホルダーを章末に挿入
  7. 使ってみた感想・想定シーン
  8. まとめ
- LLM: Claude Opus (Claude Code CLI上なのでネイティブで使える)
- 出力先: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/actions/drafts/dalamud-<plugin>-draft.md`

**重要な制約（FF14ツール哲学）**:
- ツール使用者は「日陰もの」という自覚を持った文体に
- 「他人に迷惑をかけない」が大前提
- PvPでの使用、課金外見Mod共有はNG
- スクエニ規約への不満を外に出さない
- 詳細: `HERMES.md` の「FF14ツール哲学」セクション参照

### Stage 3-B: post_wp.py 未着手

**目的**: 生成されたMarkdownをWordPressに下書き投稿

**仕様**:
- WordPress REST API: `POST https://toramemoblog.com/wp-json/wp/v2/posts`
- Basic認証: `WP_USER` + `WP_APP_PASSWORD`（`~/.toramemoblog.env`）
- `status=draft` で投稿
- カテゴリ・タグの自動付与（既存カテゴリAPI: `/wp-json/wp/v2/categories`）
- 投稿成功時、下書きURL `https://toramemoblog.com/wp-admin/post.php?post=<id>&action=edit` を出力
- Markdown → HTML変換: `markdown` (pip) で十分

**認証確認済み**:
```bash
curl -s -u "wordtoramame:xSqf 5tPT MbMo UEnk n3Dp nCUP" \
  https://toramemoblog.com/wp-json/wp/v2/users/me
# → {"name":"とらまめ", "id":1} で認証OK
```

### Stage 4: monthly_roundup.py 未着手
- 月末トリガーで、その月にdraftに入れたプラグイン記事の一覧 + 未紹介で活発だったプラグインを集計
- 「今月の注目Dalamudプラグイン○選」として別途下書き生成

### Hermes Agent 側へ引き渡す項目（Claude Code CLI ではやらない）

実装完了後、以下を Hermes Agent に依頼してcron登録してもらう:

1. **週1の finder.py 実行**
   - スケジュール: 毎週月曜 朝9時 (`0 9 * * 1`)
   - コマンド: `cd ~/macmini-setup/scripts/dalamud && python3 finder.py --scan 40 --top 20 --days 30`
   - 結果ファイル: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/dalamud-active-YYYY-MM-DD.md`
   - 通知先: Discord home channel (torabot-memo)
   - 通知内容: 上位5件のサマリ + ファイルパス

2. **月末の monthly_roundup.py 実行**
   - スケジュール: 毎月末日 朝10時
   - WordPress下書き投稿後、Discordに下書きURL通知

3. **障害監視**
   - finder.py が失敗したら Discord に通知
   - gh APIレート制限エラーを検知したら次回リトライ

---

## 環境情報

### WordPress認証
- 場所: `~/.toramemoblog.env` (chmod 600)
- 内容:
  ```
  WP_URL=https://toramemoblog.com
  WP_LOGIN_URL=https://toramemoblog.com/libetora
  WP_USER=wordtoramame
  WP_APP_PASSWORD="xSqf 5tPT MbMo UEnk n3Dp nCUP"
  ```

### GitHub認証
- `gh` CLI が `zelos613` アカウントで認証済み（keyring保存）
- スコープ: gist, read:org, repo, workflow
- 別途 `GITHUB_TOKEN` 環境変数は不要

### ToraVault
- パス: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/`
- iCloud同期
- `raw-sources/articles/*.txt` に過去記事サンプル265本
- `actions/drafts/` は今回新設予定（自動生成原稿の格納先）

### LLM
- **このプロジェクトは Claude Code CLI 上で Claude Opus を使う**
- Hermes Agent 側の Ollama/Qwen/Grok は使わない方針
- ローカルでHermes経由を試した場合のメモ: ANTHROPIC_API_KEY が `~/.hermes/.env` に未設定だった

---

## テスト時の選定プラグイン

zelo が選んだテスト対象: **`lokinmodar/Echoglossian`** (FFXIV Dialogue text translator)
- スコア 167.6（直近30日: コミット103 / マージPR5 / オープンPR2 / 新規Issue40 / リリース4）
- 素材ファイル生成済み: `~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault/raw-sources/articles/dalamud-lokinmodar_Echoglossian-source.md`

このプラグインで Stage 3 (write_article.py + post_wp.py) を通しでテストすればOK。

---

## オーナーの方針（重要）

- 設計を先に提示してから実装を進める（設計レビュー必須）
- 設計には変更ファイル一覧・依存関係・依存がない場合の挙動を含める
- 記事サンプル選定は自動でOK（プラグイン紹介系はだいたい同じ形式）
- Stage 1は週1自動化
- 1プラグイン = 1記事、月1でまとめ記事

---

## 過去のやりとりの要約

1. ユーザーから「GitHub更新が盛んなDalamudプラグイン発見方法」を相談
2. 設計提案 → 「解説記事生成までやりたい」と追加要件
3. WordPress下書き自動投稿、文体は既存ブログ模倣、Claude Opus使用で合意
4. Application Password発行（既に上記envに保存）
5. Stage 1 (finder.py) 実装・テスト成功
6. PR/Issueも見たいとの要望 → コアAPIに切り替えてレート制限回避
7. 除外リスト (exclude.txt) 追加
8. Stage 2 (collect.py) 実装・Echoglossianでテスト成功
9. Stage 3に進む前にHermes Agentから Claude Code CLI へ引き継ぐことに

---

## 次のセッションでの第一声テンプレ

```
このディレクトリ ~/macmini-setup/scripts/dalamud/ で
HANDOFF.md を読んで、Stage 3-A (write_article.py) の設計から提案して。
オーナー(zelo)は設計レビュー後に実装に入る方針。
テスト対象は素材ファイル既出の Echoglossian で。
```
