#!/usr/bin/env python3
"""
vault-health-check.py
ToraVault wiki の健全性チェックスクリプト

検出項目:
  - 内部リンク切れ ([[ページ名]] 形式)
  - raw-sources に対応する wiki ページが存在しない素材
  - 最終更新日が 90 日以上前のページ（古い可能性あり）
  - どこからもリンクされていない孤立ノート
"""

import os
import re
import sys
import json
import datetime
from pathlib import Path
from collections import defaultdict

# ── 設定 ────────────────────────────────────────────────
VAULT_ROOT = Path(os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
))
WIKI_DIRS = [
    VAULT_ROOT / "wiki" / "summaries",
    VAULT_ROOT / "wiki" / "concepts",
    VAULT_ROOT / "wiki" / "entities",
]
RAW_SOURCES_DIR = VAULT_ROOT / "raw-sources"
REPORT_PATH = VAULT_ROOT / "actions" / "vault-health-report.md"
STALE_DAYS = 90

# ── ユーティリティ ─────────────────────────────────────

def safe_run(fn, label):
    """エラーを握りつぶさず results に記録しながら継続実行"""
    try:
        return fn(), None
    except Exception as e:
        return None, f"[{label}] {type(e).__name__}: {e}"


def collect_wiki_files():
    """全 wiki .md ファイルのパスリストを返す"""
    files = []
    for d in WIKI_DIRS:
        if d.exists():
            files.extend(d.rglob("*.md"))
    return files


def stem_to_path_map(wiki_files):
    """ファイル名（拡張子なし）→ Path の辞書。大文字小文字を正規化"""
    m = {}
    for p in wiki_files:
        m[p.stem.lower()] = p
    return m


def extract_internal_links(text):
    """[[ページ名]] または [[ページ名|エイリアス]] を抽出"""
    pattern = r'\[\[([^\]|#]+)(?:[|#][^\]]*)?]]'
    return re.findall(pattern, text)


def file_mtime(path):
    """ファイルの最終更新日時 (datetime)"""
    return datetime.datetime.fromtimestamp(path.stat().st_mtime)


# ── チェック処理 ───────────────────────────────────────

def check_broken_links(wiki_files, stem_map):
    """内部リンク切れを検出"""
    broken = []  # (source_path, link_target)
    for path in wiki_files:
        try:
            text = path.read_text(encoding="utf-8")
            links = extract_internal_links(text)
            for link in links:
                # エイリアスやアンカーを除去したページ名
                page_name = link.split("#")[0].split("|")[0].strip()
                if page_name.lower() not in stem_map:
                    broken.append((path, page_name))
        except Exception as e:
            broken.append((path, f"[読み込みエラー: {e}]"))
    return broken


def check_stale_pages(wiki_files):
    """STALE_DAYS 日以上更新されていないページを検出"""
    threshold = datetime.datetime.now() - datetime.timedelta(days=STALE_DAYS)
    stale = []
    for path in wiki_files:
        try:
            mtime = file_mtime(path)
            if mtime < threshold:
                days_old = (datetime.datetime.now() - mtime).days
                stale.append((path, mtime, days_old))
        except Exception as e:
            stale.append((path, None, f"[エラー: {e}]"))
    return sorted(stale, key=lambda x: x[2] if isinstance(x[2], int) else 0, reverse=True)


def check_orphan_notes(wiki_files, stem_map):
    """どの wiki ページからもリンクされていない孤立ノートを検出"""
    # 全リンクターゲットを収集
    referenced = set()
    for path in wiki_files:
        try:
            text = path.read_text(encoding="utf-8")
            links = extract_internal_links(text)
            for link in links:
                page_name = link.split("#")[0].split("|")[0].strip().lower()
                referenced.add(page_name)
        except Exception:
            pass

    orphans = []
    for path in wiki_files:
        if path.stem.lower() not in referenced:
            orphans.append(path)
    return orphans


def check_raw_sources_coverage(wiki_files, stem_map):
    """raw-sources の各ファイルに対応する wiki/summaries が存在するか確認"""
    uncovered = []
    if not RAW_SOURCES_DIR.exists():
        return uncovered
    for raw in RAW_SOURCES_DIR.rglob("*.md"):
        stem = raw.stem.lower()
        # summaries/ 以下にファイル名が含まれているかチェック
        summaries_dir = VAULT_ROOT / "wiki" / "summaries"
        matched = any(
            p.stem.lower() == stem or stem in p.stem.lower() or p.stem.lower() in stem
            for p in summaries_dir.rglob("*.md")
        ) if summaries_dir.exists() else False
        if not matched:
            uncovered.append(raw)
    return uncovered


# ── レポート生成 ────────────────────────────────────────

def relative(path):
    """Vault ルートからの相対パスを返す"""
    try:
        return str(path.relative_to(VAULT_ROOT))
    except ValueError:
        return str(path)


def build_report(broken, stale, orphans, uncovered, errors, elapsed):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []

    lines.append(f"# ToraVault ヘルスチェックレポート")
    lines.append(f"")
    lines.append(f"生成日時: {now}  ")
    lines.append(f"処理時間: {elapsed:.2f} 秒")
    lines.append(f"")

    # サマリー
    lines.append(f"## サマリー")
    lines.append(f"")
    lines.append(f"| 項目 | 件数 |")
    lines.append(f"|------|------|")
    lines.append(f"| リンク切れ | {len(broken)} |")
    lines.append(f"| 古いページ（{STALE_DAYS}日以上） | {len(stale)} |")
    lines.append(f"| 孤立ノート | {len(orphans)} |")
    lines.append(f"| raw-sources カバレッジ不足 | {len(uncovered)} |")
    lines.append(f"| エラー | {len(errors)} |")
    lines.append(f"")

    # リンク切れ
    lines.append(f"## リンク切れ ({len(broken)} 件)")
    lines.append(f"")
    if broken:
        for src, target in broken:
            lines.append(f"- `{relative(src)}` → `[[{target}]]` が存在しない")
    else:
        lines.append(f"✅ リンク切れなし")
    lines.append(f"")

    # 古いページ
    lines.append(f"## 古い可能性があるページ ({len(stale)} 件, {STALE_DAYS}日以上未更新)")
    lines.append(f"")
    if stale:
        for path, mtime, days in stale:
            if isinstance(days, int):
                mtime_str = mtime.strftime("%Y-%m-%d") if mtime else "不明"
                lines.append(f"- `{relative(path)}` — 最終更新: {mtime_str} ({days}日前)")
            else:
                lines.append(f"- `{relative(path)}` — {days}")
    else:
        lines.append(f"✅ 古いページなし")
    lines.append(f"")

    # 孤立ノート
    lines.append(f"## 孤立ノート ({len(orphans)} 件)")
    lines.append(f"")
    if orphans:
        for path in orphans:
            lines.append(f"- `{relative(path)}`")
    else:
        lines.append(f"✅ 孤立ノートなし")
    lines.append(f"")

    # raw-sources カバレッジ
    lines.append(f"## raw-sources カバレッジ不足 ({len(uncovered)} 件)")
    lines.append(f"")
    if uncovered:
        lines.append(f"> wiki/summaries に対応するページが見つからない raw-sources ファイル")
        lines.append(f"")
        for path in uncovered:
            lines.append(f"- `{relative(path)}`")
    else:
        lines.append(f"✅ 全 raw-sources にサマリーあり")
    lines.append(f"")

    # エラー
    if errors:
        lines.append(f"## 処理中エラー ({len(errors)} 件)")
        lines.append(f"")
        for e in errors:
            lines.append(f"- {e}")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"*このレポートは vault-health-check.py により自動生成されました*")

    return "\n".join(lines)


def build_discord_summary(broken, stale, orphans, uncovered, errors):
    """Discord 通知用の短いサマリー"""
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    total_issues = len(broken) + len(stale) + len(orphans) + len(uncovered)

    if total_issues == 0 and not errors:
        status = "✅ 問題なし"
    elif total_issues <= 5:
        status = "🟡 軽微な問題あり"
    else:
        status = "🔴 要確認"

    lines = [
        f"## ToraVault ヘルスチェック {status}",
        f"実行日時: {now}",
        f"",
        f"| 項目 | 件数 |",
        f"|------|------|",
        f"| リンク切れ | {len(broken)} |",
        f"| 古いページ({STALE_DAYS}日以上) | {len(stale)} |",
        f"| 孤立ノート | {len(orphans)} |",
        f"| summaryカバレッジ不足 | {len(uncovered)} |",
    ]
    if errors:
        lines.append(f"| エラー | {len(errors)} |")

    if broken:
        lines.append(f"")
        lines.append(f"**リンク切れ（最大3件）:**")
        for src, target in broken[:3]:
            lines.append(f"- `{src.name}` → `[[{target}]]`")

    lines.append(f"")
    lines.append(f"詳細: `ToraVault/actions/vault-health-report.md`")

    return "\n".join(lines)


# ── メイン ─────────────────────────────────────────────

def main():
    start = datetime.datetime.now()
    errors = []

    print("ToraVault ヘルスチェック開始...")

    # wiki ファイル収集
    wiki_files, err = safe_run(collect_wiki_files, "wiki_files")
    if err:
        errors.append(err)
        wiki_files = []
    print(f"  wiki ファイル数: {len(wiki_files)}")

    stem_map = stem_to_path_map(wiki_files) if wiki_files else {}

    # 各チェック実行
    broken, err = safe_run(lambda: check_broken_links(wiki_files, stem_map), "broken_links")
    if err: errors.append(err); broken = []

    stale, err = safe_run(lambda: check_stale_pages(wiki_files), "stale_pages")
    if err: errors.append(err); stale = []

    orphans, err = safe_run(lambda: check_orphan_notes(wiki_files, stem_map), "orphan_notes")
    if err: errors.append(err); orphans = []

    uncovered, err = safe_run(lambda: check_raw_sources_coverage(wiki_files, stem_map), "raw_coverage")
    if err: errors.append(err); uncovered = []

    elapsed = (datetime.datetime.now() - start).total_seconds()

    # レポート生成・書き込み
    report = build_report(broken, stale, orphans, uncovered, errors, elapsed)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"  レポート書き込み完了: {REPORT_PATH}")

    # Discord サマリーを stdout に出力（cronjob の deliver で使用）
    summary = build_discord_summary(broken, stale, orphans, uncovered, errors)
    print("\n" + "=" * 40)
    print(summary)
    print("=" * 40)

    # cronjob の最終出力として summary を返す
    # (Hermes cronjob は stdout の最後の出力を deliver する)
    sys.stdout.flush()
    return summary


if __name__ == "__main__":
    main()
