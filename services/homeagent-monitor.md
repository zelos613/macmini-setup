# homeagent-monitor

Discord Bot の死活監視・自動修復エージェント。

## 場所

`~/claude-agent/`

```
claude-agent/
├── monitor.py     # メインの監視スクリプト
├── notify.py      # 通知処理
├── auto-update.py # （zelopersonal/toradiscordbot 向け自動更新）
└── logs/
    ├── monitor.log
    ├── monitor.err
    └── actions.md  # 修復アクションの記録
```

## 監視対象サービス

| launchd ラベル | 内容 |
|---|---|
| `com.zelopersonal-discord` | 個人用AIアシスタントBot |
| `com.toradiscordbot` | とらめも交流所コミュニティBot |

## launchd

- **ラベル**: `com.homeagent-monitor`
- **実行間隔**: 15分ごと（`StartInterval: 900`）
- **plist**: `~/Library/LaunchAgents/com.homeagent-monitor.plist`

## ログ

- 通常ログ: `~/claude-agent/logs/monitor.log`
- エラー: `~/claude-agent/logs/monitor.err`
- 修復アクション記録: `~/claude-agent/logs/actions.md`
