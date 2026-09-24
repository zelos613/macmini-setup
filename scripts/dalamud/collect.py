#!/usr/bin/env python3
"""
Stage 2: プラグイン素材収集

指定したリポジトリの README、最新リリース、コミット履歴、メタ情報を
収集して素材ファイル(Markdown)を出力する。

使い方:
    python3 collect.py owner/repo
    python3 collect.py lokinmodar/Echoglossian
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
OUTPUT_DIR = VAULT / "raw-sources" / "articles"


def gh_api(path: str) -> Any:
    try:
        r = subprocess.run(
            ["gh", "api", path],
            capture_output=True, text=True, check=True, timeout=60,
        )
        out = r.stdout.strip()
        return json.loads(out) if out else None
    except subprocess.CalledProcessError as e:
        print(f"[gh api error] {path}: {e.stderr[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[parse error] {path}: {e}", file=sys.stderr)
        return None


def fetch_readme(full_name: str) -> str:
    data = gh_api(f"repos/{full_name}/readme")
    if not data or "content" not in data:
        return "(READMEなし)"
    try:
        decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return decoded
    except Exception as e:
        return f"(README decode失敗: {e})"


def fetch_releases(full_name: str, limit: int = 5) -> list[dict]:
    data = gh_api(f"repos/{full_name}/releases?per_page={limit}")
    return data if isinstance(data, list) else []


def fetch_recent_commits(full_name: str, days: int = 30) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = gh_api(f"repos/{full_name}/commits?since={since}&per_page=50")
    return data if isinstance(data, list) else []


def fetch_repo_meta(full_name: str) -> dict | None:
    return gh_api(f"repos/{full_name}")


def detect_custom_repo_url(readme: str) -> list[str]:
    """READMEからカスタムリポジトリURL(repo.json)を抽出する。"""
    import re
    urls = re.findall(r"https?://[^\s\)\"<>]+repo\.json", readme)
    # 重複除去
    seen: list[str] = []
    for u in urls:
        if u not in seen:
            seen.append(u)
    return seen


def find_related_articles(plugin_name: str) -> list[Path]:
    """既存の記事サンプルから関連しそうなものを探す。"""
    articles_dir = VAULT / "raw-sources" / "articles"
    if not articles_dir.exists():
        return []
    related: list[Path] = []
    keyword = plugin_name.lower()
    for p in articles_dir.glob("*.txt"):
        # ファイル名や中身に同名があれば
        if keyword in p.name.lower():
            related.append(p)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if keyword in text.lower():
                related.append(p)
        except Exception:
            pass
    return related


def to_markdown(
    full_name: str,
    meta: dict,
    readme: str,
    releases: list[dict],
    commits: list[dict],
    custom_repo: list[str],
    related: list[Path],
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    name = full_name.split("/")[-1]

    lines = [
        f"# 素材: {name}",
        "",
        f"収集日: {today}",
        f"リポジトリ: <{meta.get('html_url')}>",
        "",
        "## メタ情報",
        f"- フルネーム: `{full_name}`",
        f"- スター: {meta.get('stargazers_count', 0)}",
        f"- 説明 (en): {meta.get('description') or '(なし)'}",
        f"- 言語: {meta.get('language')}",
        f"- ライセンス: {(meta.get('license') or {}).get('spdx_id', '不明')}",
        f"- 作成: {meta.get('created_at')}",
        f"- 最終push: {meta.get('pushed_at')}",
        f"- トピック: {', '.join(meta.get('topics', [])) or '(なし)'}",
        f"- ホームページ: {meta.get('homepage') or '(なし)'}",
        "",
        "## カスタムリポジトリURL候補",
    ]
    if custom_repo:
        for url in custom_repo:
            lines.append(f"- `{url}`")
    else:
        lines.append("- (READMEから自動検出できず。手動確認が必要かも)")
    lines += ["", "## 最新リリース（最大5件）"]
    if releases:
        for r in releases:
            tag = r.get("tag_name", "?")
            pub = (r.get("published_at") or "")[:10]
            body = (r.get("body") or "").strip()
            # bodyは300字までに切る
            short = body[:300] + ("..." if len(body) > 300 else "")
            lines += [
                f"### {tag} ({pub})",
                short or "(リリースノートなし)",
                "",
            ]
    else:
        lines.append("(リリースなし)")
        lines.append("")

    lines.append("## 直近30日のコミット (最大20件)")
    if commits:
        for c in commits[:20]:
            msg = c.get("commit", {}).get("message", "").split("\n")[0][:120]
            date = (c.get("commit", {}).get("author", {}).get("date") or "")[:10]
            lines.append(f"- `{date}` {msg}")
    else:
        lines.append("- (コミットなし)")
    lines.append("")

    lines.append("## 関連する既存記事 (重複チェック用)")
    if related:
        for p in related:
            lines.append(f"- `{p.name}`")
    else:
        lines.append("- (関連記事なし → 新規ネタとしてOK)")
    lines.append("")

    lines += [
        "## README全文",
        "",
        "```markdown",
        readme,
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="owner/repo")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    full_name = args.repo
    print(f"[1/4] メタ情報取得: {full_name}", file=sys.stderr)
    meta = fetch_repo_meta(full_name)
    if not meta:
        print(f"ERROR: リポジトリが取得できない: {full_name}", file=sys.stderr)
        return 1

    print("[2/4] README取得", file=sys.stderr)
    readme = fetch_readme(full_name)

    print("[3/4] リリース・コミット取得", file=sys.stderr)
    releases = fetch_releases(full_name)
    commits = fetch_recent_commits(full_name, days=args.days)

    print("[4/4] 整形・保存", file=sys.stderr)
    custom_repo = detect_custom_repo_url(readme)
    related = find_related_articles(meta["name"])
    md = to_markdown(full_name, meta, readme, releases, commits, custom_repo, related)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = full_name.replace("/", "_")
    out_path = OUTPUT_DIR / f"dalamud-{safe_name}-source.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"      → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
