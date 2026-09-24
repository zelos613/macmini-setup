#!/usr/bin/env python3
"""
Dalamud プラグイン活発度ファインダー

GitHub上の Dalamud 関連リポジトリを検索し、直近30日の活動量で
スコアリングして「盛り上がっているプラグイン」を抽出する。

使い方:
    python3 finder.py              # 標準: 30日, top 30
    python3 finder.py --days 14    # 直近14日に変更
    python3 finder.py --top 50     # 上位50件
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
OUTPUT_DIR = VAULT / "raw-sources"
EXCLUDE_FILE = Path(__file__).parent / "exclude.txt"


def load_exclude_rules() -> tuple[set[str], set[str], list[str]]:
    """除外リストを読み込む → (full_names, owners, keywords)。"""
    full: set[str] = set()
    owners: set[str] = set()
    keywords: list[str] = []
    if not EXCLUDE_FILE.exists():
        return full, owners, keywords
    for line in EXCLUDE_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("keyword:"):
            keywords.append(s[len("keyword:"):].strip().lower())
        elif s.endswith("/"):
            owners.add(s[:-1].lower())
        elif "/" in s:
            full.add(s.lower())
    return full, owners, keywords


def is_excluded(repo: dict, full: set[str], owners: set[str], keywords: list[str]) -> str | None:
    """除外なら理由を返す、対象なら None。"""
    fn = repo["full_name"].lower()
    if fn in full:
        return f"full_name match: {fn}"
    owner = fn.split("/")[0]
    if owner in owners:
        return f"owner match: {owner}"
    desc = (repo.get("description") or "").lower()
    name = repo["name"].lower()
    for kw in keywords:
        if kw in desc or kw in name:
            return f"keyword match: {kw}"
    return None


def gh_api(path: str, paginate: bool = False) -> Any:
    """gh CLI 経由で GitHub API を叩く。"""
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd.append(path)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        out = r.stdout.strip()
        if not out:
            return None
        # --paginate は複数JSON配列を連結するので個別パース
        if paginate and out.startswith("["):
            # 配列の連結を1つの配列に
            items: list[Any] = []
            depth = 0
            buf = ""
            for ch in out:
                buf += ch
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        items.extend(json.loads(buf))
                        buf = ""
            return items
        return json.loads(out)
    except subprocess.CalledProcessError as e:
        print(f"[gh api error] {path}: {e.stderr[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[parse error] {path}: {e}", file=sys.stderr)
        return None


@dataclass
class RepoStats:
    name: str
    full_name: str
    url: str
    description: str
    stars: int
    pushed_at: str
    commits_30d: int = 0
    merged_prs_30d: int = 0
    open_prs: int = 0
    new_issues_30d: int = 0
    releases_30d: int = 0
    score: float = 0.0
    last_commit_msg: str = ""

    def compute_score(self) -> None:
        self.score = (
            self.commits_30d * 1.0
            + self.merged_prs_30d * 2.0
            + self.open_prs * 1.5
            + self.new_issues_30d * 0.5
            + self.releases_30d * 5.0
            + self.stars * 0.1
        )


def search_dalamud_repos(top: int = 80) -> list[dict]:
    """dalamud関連リポジトリを直近pushed順で取得。"""
    # 複数クエリで網羅性を上げる
    queries = [
        "dalamud+language:C%23",
        "dalamud+plugin",
        "topic:dalamud-plugin",
        "topic:ffxiv-dalamud",
    ]
    seen: dict[str, dict] = {}
    for q in queries:
        # 1ページ100件まで、sortedはpushed
        data = gh_api(f"search/repositories?q={q}&sort=updated&order=desc&per_page=100")
        if not data or "items" not in data:
            continue
        for item in data["items"]:
            fn = item["full_name"]
            if fn not in seen:
                seen[fn] = item
    # スター順で軽くソートして上位top件に絞る
    repos = sorted(seen.values(), key=lambda x: x.get("stargazers_count", 0), reverse=True)
    return repos[:top]


def collect_activity(repo: dict, since: datetime) -> RepoStats:
    fn = repo["full_name"]
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    stats = RepoStats(
        name=repo["name"],
        full_name=fn,
        url=repo["html_url"],
        description=(repo.get("description") or "").strip(),
        stars=repo.get("stargazers_count", 0),
        pushed_at=repo.get("pushed_at", ""),
    )

    # コミット数
    commits = gh_api(f"repos/{fn}/commits?since={since_iso}&per_page=100", paginate=True)
    if isinstance(commits, list):
        stats.commits_30d = len(commits)
        if commits:
            msg = commits[0].get("commit", {}).get("message", "")
            stats.last_commit_msg = msg.split("\n")[0][:120]

    # PR (コアAPI: search/issuesは30req/分制限が厳しいので避ける)
    # closed PR一覧から直近30日のマージ済みを数える
    closed_prs = gh_api(
        f"repos/{fn}/pulls?state=closed&sort=updated&direction=desc&per_page=100"
    )
    if isinstance(closed_prs, list):
        merged_cnt = 0
        for pr in closed_prs:
            merged_at = pr.get("merged_at")
            if merged_at and merged_at >= since_iso:
                merged_cnt += 1
            elif merged_at and merged_at < since_iso:
                break  # 更新順なので以降は古い
        stats.merged_prs_30d = merged_cnt

    open_prs_list = gh_api(f"repos/{fn}/pulls?state=open&per_page=100")
    if isinstance(open_prs_list, list):
        stats.open_prs = len(open_prs_list)

    # 新規Issue (PRも含まれるので除外)
    issues = gh_api(
        f"repos/{fn}/issues?state=all&since={since_iso}&per_page=100&sort=created&direction=desc"
    )
    if isinstance(issues, list):
        cnt = 0
        for it in issues:
            if it.get("pull_request"):
                continue
            created = it.get("created_at", "")
            if created >= since_iso:
                cnt += 1
        stats.new_issues_30d = cnt

    # リリース
    releases = gh_api(f"repos/{fn}/releases?per_page=30")
    if isinstance(releases, list):
        cnt = 0
        for r in releases:
            pub = r.get("published_at") or ""
            if pub and pub >= since_iso:
                cnt += 1
        stats.releases_30d = cnt

    stats.compute_score()
    return stats


def to_markdown(stats_list: list[RepoStats], days: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Dalamud活発プラグイン候補 ({today})",
        "",
        f"直近{days}日の活動量でスコアリング。上位ほどブログネタ候補。",
        "",
        "スコア = コミット×1 + マージPR×2 + オープンPR×1.5 + 新規Issue×0.5 + リリース×5 + スター×0.1",
        "",
        "---",
        "",
    ]
    for i, s in enumerate(stats_list, 1):
        lines += [
            f"## {i}. [{s.full_name}]({s.url})  — スコア {s.score:.1f}",
            "",
            f"- ⭐ {s.stars} / 最終push: `{s.pushed_at}`",
            f"- 説明: {s.description or '(なし)'}",
            f"- 直近{days}日: コミット {s.commits_30d} / マージPR {s.merged_prs_30d} / "
            f"オープンPR {s.open_prs} / 新規Issue {s.new_issues_30d} / リリース {s.releases_30d}",
        ]
        if s.last_commit_msg:
            lines.append(f"- 最新コミット: {s.last_commit_msg}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--top", type=int, default=30, help="出力する上位件数")
    ap.add_argument("--scan", type=int, default=80, help="活動量を調べる候補数")
    ap.add_argument("--min-score", type=float, default=3.0)
    ap.add_argument("--json-out", type=Path, help="JSON出力先(任意)")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"[1/3] dalamud関連リポジトリを検索 (上位{args.scan}件)...", file=sys.stderr)
    repos = search_dalamud_repos(top=args.scan)
    print(f"      → {len(repos)} 件取得", file=sys.stderr)

    # 除外フィルタ
    full, owners, keywords = load_exclude_rules()
    filtered: list[dict] = []
    excluded_count = 0
    for r in repos:
        reason = is_excluded(r, full, owners, keywords)
        if reason:
            excluded_count += 1
            print(f"      除外: {r['full_name']} ({reason})", file=sys.stderr)
        else:
            filtered.append(r)
    print(f"      → {len(filtered)} 件 ({excluded_count}件除外)", file=sys.stderr)
    repos = filtered

    print(f"[2/3] 各リポジトリの活動量を収集 (since {since.date()})...", file=sys.stderr)
    stats_list: list[RepoStats] = []
    for i, repo in enumerate(repos, 1):
        if i % 10 == 0:
            print(f"      ... {i}/{len(repos)}", file=sys.stderr)
        s = collect_activity(repo, since)
        if s.score >= args.min_score:
            stats_list.append(s)

    stats_list.sort(key=lambda x: x.score, reverse=True)
    stats_list = stats_list[: args.top]

    print(f"[3/3] {len(stats_list)} 件を保存", file=sys.stderr)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / f"dalamud-active-{datetime.now().strftime('%Y-%m-%d')}.md"
    md_path.write_text(to_markdown(stats_list, args.days), encoding="utf-8")
    print(f"      → {md_path}")

    if args.json_out:
        args.json_out.write_text(
            json.dumps([asdict(s) for s in stats_list], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"      → {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
