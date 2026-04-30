# Git Auto-Push System for macmini-setup

## 概要

Mac Mini の仕様書（CLAUDE.md）を手動で編集すると、自動で GitHub に push される仕組み。

- **単一のソースオブトゥルース**: `~/macmini-setup/CLAUDE.md`
- **自動ウォッチ**: ファイル変更を検出 → コミット → push
- **バックグラウンド実行**: launchd で常駐

## 使用方法

### 方法 1: テキストエディタで直接編集（推奨）

```bash
# 好きなエディタで編集
vim ~/macmini-setup/CLAUDE.md
# または
nano ~/macmini-setup/CLAUDE.md
```

保存すると自動で GitHub に push されます。

### 方法 2: 手動で push

```bash
# git-auto-push.sh を実行
~/macmini-setup/scripts/git-auto-push.sh "任意のメッセージ"

# メッセージなしで実行（自動生成）
~/macmini-setup/scripts/git-auto-push.sh
```

## ファイル構成

```
macmini-setup/
├── CLAUDE.md                    # ← 仕様書（自動更新対象）
├── scripts/
│   ├── git-auto-push.sh         # 手動 push スクリプト
│   └── watch-and-push.py        # ウォッチャー本体
├── logs/
│   ├── git-watch.log            # ウォッチャーログ
│   ├── git-watcher.out          # stdout
│   └── git-watcher.err          # stderr
└── ~/Library/LaunchAgents/
    └── com.macmini-setup.git-watcher.plist  # launchd 設定
```

## ウォッチャーの状態確認

```bash
# 実行中か確認
launchctl list | grep git-watcher

# ログを確認
tail -f ~/macmini-setup/logs/git-watch.log
```

## トラブルシューティング

### ウォッチャーが起動していない

```bash
# 再起動
launchctl unload ~/Library/LaunchAgents/com.macmini-setup.git-watcher.plist
launchctl load ~/Library/LaunchAgents/com.macmini-setup.git-watcher.plist
```

### push に失敗する

```bash
# SSH キーが設定されているか確認
ssh -T git@github.com

# 手動で push してみる
cd ~/macmini-setup
git push origin main
```

### ログの確認

```bash
# ウォッチャーログ
tail -f ~/macmini-setup/logs/git-watch.log

# launchd ログ
log stream --level debug --predicate 'eventMessage contains "git-watcher"'
```

## 自動化の詳細

1. **ファイル監視**: watch-and-push.py が 2 秒ごとに CLAUDE.md を確認
2. **変更検出**: mtime が増加したら save 完了と判定（2.5 秒待機）
3. **git 操作**: `git add -A` → `git commit` → `git push origin main`
4. **バックグラウンド**: launchd で常に実行

## 注意事項

- **GitHub に push できるか確認**: SSH キーまたは HTTPS token が必要
- **ネットワーク接続**: インターネット接続がないと push に失敗（ローカルコミットは成功）
- **競合**: 複数プロセスが同時に push しないよう注意

## 今後の拡張

- [ ] Slack 通知（push 成功 / 失敗）
- [ ] Git Diff を Slack に送信
- [ ] services/*.md も監視対象に追加
