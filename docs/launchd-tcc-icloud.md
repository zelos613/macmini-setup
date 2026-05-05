# launchd × iCloud Drive × TCC のハマりどころ

## 結論

launchd で常駐させるスクリプトから iCloud Drive (`~/Library/Mobile Documents/com~apple~CloudDocs/`) を読み書きするには、**実行されるバイナリに「フルディスクアクセス（FDA）」を付与する必要がある**。
ターミナルから手で動かしたときは動くのに、launchd 経由だと動かない場合、ほぼこれが原因。

## 症状

- ターミナルから直接スクリプトを実行 → 正常動作（ファイルが見える、読み書きできる）
- 同じスクリプトを launchd ジョブとして実行 → `os.listdir` / `Path.rglob` が**空配列を返す**
- 例外は投げられない（ENOENT も EACCES も出ない）。**TCC は黙ってフィルタする**ためログにも何も残らない
- launchd の `StandardErrorPath` も空のまま

## なぜ起きるか

macOS の TCC（Transparency, Consent, Control）は iCloud Drive を「保護対象」として扱う。ターミナル系アプリ（Terminal.app / iTerm）は通常 FDA を持っているのでターミナル子プロセスはアクセスできるが、launchd 子プロセスはこの権限を**継承しない**。
さらに iCloud Drive のディレクトリリスティングは「権限が無ければ空に見える」挙動なので、エラーで気づけない。

## 対処：FDA を専用 venv バイナリに絞って付与する

システム Python (`/usr/bin/python3`) に直接 FDA を与えると、全ての python スクリプトが iCloud にアクセスできてしまう。これは権限の与えすぎなので、**サービス専用の venv バイナリを作って、それだけに FDA を付与する**のが推奨。

### 1. venv を作成（**実体バイナリ**を持たせる）

`venv` のデフォルトは symlink モード。symlink だと TCC が解決先（システム Python）を見るので独立した権限管理にならない。`--copies` オプションで実体バイナリを作る必要がある。

```bash
# システム Python (Apple Command Line Tools) は --copies 非対応
# → Homebrew Python を使う
/opt/homebrew/bin/python3 -m venv --copies ~/macmini-setup/.venv

# 確認：symlink ではなく Mach-O 実行ファイルになっているはず
file ~/macmini-setup/.venv/bin/python3
# → Mach-O 64-bit executable arm64
```

### 2. plist の `ProgramArguments` を venv の Python に書き換える

```xml
<key>ProgramArguments</key>
<array>
    <string>/Users/mame/macmini-setup/.venv/bin/python3</string>
    <string>/Users/mame/macmini-setup/scripts/your-script.py</string>
</array>
```

### 3. FDA に専用バイナリを追加

System Settings → プライバシーとセキュリティ → フルディスクアクセス → `+` → Finder で `⌘⇧G` → 以下のパスを貼り付けて選択：

```
/Users/mame/macmini-setup/.venv/bin/python3
```

スイッチがオン（青）になっていることを確認。

### 4. サービスを再起動

```bash
launchctl unload ~/Library/LaunchAgents/com.example.plist
launchctl load   ~/Library/LaunchAgents/com.example.plist
```

## 切り分け方

新規サービスで「ファイルが見えていない」気配がしたら：

```bash
# 1. ターミナルから同じ Python で動かす（普通に動けば TCC が原因濃厚）
~/macmini-setup/.venv/bin/python3 scripts/your-script.py

# 2. launchd 起動中のプロセスが本当に保護対象を見ていないか確認
PID=$(launchctl list | grep your-label | awk '{print $1}')
lsof -p $PID | grep -E "Mobile Documents|CloudDocs"
# 何も出なければ TCC で見えていない
```

## やってはいけないこと

- ❌ シンボリックリンク (`/usr/bin/python3` のような) を FDA に追加 → TCC は解決先で判定するため効かない
- ❌ システム Python に FDA → 他の python スクリプト全てが iCloud にアクセス可能になり権限拡散
- ❌ `--copies` を付けずに作った venv を使う → 中身が symlink なので独立した権限管理にならない

## 関連サービス

- [services/vault-auto-summarize.md](../services/vault-auto-summarize.md) — このパターンで構築されたサービス
