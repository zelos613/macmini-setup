#!/usr/bin/env python3
"""
vault-index-update.py
ToraVault のマスターインデックス (index.md) を自動更新するスクリプト。
毎日6:00 に Hermesクロンジョブから実行される。

index.md を各フォルダの実際のファイル一覧で再構築する。
"""

import os
import re
from datetime import datetime
from pathlib import Path

VAULT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
))
INDEX_FILE = VAULT / "index.md"


def list_md_files(directory: Path, max_items: int = 20) -> list[tuple[str, str]]:
    """
    指定ディレクトリ内の .md ファイルを更新日降順で返す。
    戻り値: [(obsidian_link, title), ...]
    """
    results = []
    if not directory.exists():
        return results

    files = sorted(
        directory.rglob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    for f in files[:max_items]:
        # Obsidian 内部リンク用の相対パス（拡張子なし）
        rel = f.relative_to(VAULT).with_suffix("")
        link = str(rel).replace(os.sep, "/")

        # ファイル1行目からタイトルを抽出（# で始まる行 or ファイル名）
        try:
            first_line = f.read_text(encoding="utf-8").splitlines()[0]
            title = re.sub(r"^#+\s*", "", first_line).strip() or f.stem
        except Exception:
            title = f.stem

        results.append((link, title))
    return results


def count_files(directory: Path, pattern: str = "*.md") -> int:
    if not directory.exists():
        return 0
    return len(list(directory.rglob(pattern)))


def build_index() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # --- raw-sources ---
    raw_dir = VAULT / "raw-sources"
    raw_count = count_files(raw_dir)
    raw_recent = list_md_files(raw_dir, max_items=10)

    raw_lines = [f"- [[{link}|{title}]]" for link, title in raw_recent]
    if not raw_lines:
        raw_lines = ["- （ファイルなし）"]

    # --- wiki サブフォルダ ---
    wiki_sections = {}
    for sub in ["summaries", "concepts", "entities"]:
        sub_dir = VAULT / "wiki" / sub
        items = list_md_files(sub_dir, max_items=10)
        wiki_sections[sub] = items

    # --- discord-logs ---
    dl_daily_count = count_files(VAULT / "discord-logs" / "daily")
    dl_weekly_count = count_files(VAULT / "discord-logs" / "weekly")
    dl_recent = list_md_files(VAULT / "discord-logs" / "daily", max_items=5)

    # --- hermes-logs ---
    hl_recent = list_md_files(VAULT / "hermes-logs", max_items=5)

    # --- actions ---
    action_items = list_md_files(VAULT / "actions", max_items=10)

    # ------- 組み立て -------
    lines = []
    lines.append("# ToraVault マスターインデックス")
    lines.append(f"\n> 最終更新: {now}  （vault-index-update.py 自動生成）\n")

    # Raw Sources
    lines.append("## 📥 Raw Sources")
    lines.append(f"合計 {raw_count} ファイル / 直近10件:\n")
    lines.extend(raw_lines)

    # Wiki
    lines.append("\n## 📚 Wiki")

    sub_labels = {
        "summaries": "要約 (summaries)",
        "concepts":  "概念・用語 (concepts)",
        "entities":  "人物・ツール・コンテンツ (entities)",
    }
    for sub, label in sub_labels.items():
        items = wiki_sections[sub]
        cnt = count_files(VAULT / "wiki" / sub)
        lines.append(f"\n### {label}（{cnt} 件）")
        if items:
            for link, title in items:
                lines.append(f"- [[{link}|{title}]]")
        else:
            lines.append("- （ファイルなし）")

    # Discord Logs
    lines.append("\n## 💬 Discord Logs")
    lines.append(f"日次: {dl_daily_count} 日分 / 週次: {dl_weekly_count} 週分\n")
    lines.append("直近5日:")
    if dl_recent:
        for link, title in dl_recent:
            lines.append(f"- [[{link}|{title}]]")
    else:
        lines.append("- （ファイルなし）")

    # Hermes Logs
    lines.append("\n## 🤖 Hermes Logs")
    lines.append("直近5件:")
    if hl_recent:
        for link, title in hl_recent:
            lines.append(f"- [[{link}|{title}]]")
    else:
        lines.append("- （ファイルなし）")

    # Actions
    lines.append("\n## ✅ Actions")
    if action_items:
        for link, title in action_items:
            lines.append(f"- [[{link}|{title}]]")
    else:
        lines.append("- （ファイルなし）")

    # Footer
    lines.append("\n---")
    lines.append("_このファイルは毎日6:00に自動更新されます。手動編集は上書きされます。_")

    return "\n".join(lines) + "\n"


def main():
    content = build_index()
    INDEX_FILE.write_text(content, encoding="utf-8")
    print(f"=== vault-index-update ===")
    print(f"index.md 更新完了: {INDEX_FILE}")
    print(content[:800])
    print("=== END ===")


if __name__ == "__main__":
    main()
