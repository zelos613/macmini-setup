#!/usr/bin/env python3
"""
Stage 3-B: WordPress 下書き投稿

write_article.py が生成した下書き Markdown
(actions/drafts/dalamud-*-draft.md) を WordPress REST API に
status=draft で投稿し、編集URLを返す。

実行には ~/macmini-setup/.venv の Python を使う（requests / markdown が必要）:
    ~/macmini-setup/.venv/bin/python3 post_wp.py Echoglossian
    ~/macmini-setup/.venv/bin/python3 post_wp.py actions/drafts/dalamud-Echoglossian-draft.md --dry-run
    ~/macmini-setup/.venv/bin/python3 post_wp.py --list-categories
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import requests
    import markdown as md_lib
except ImportError as e:
    print(f"ERROR: 依存パッケージが入っていない ({e.name})", file=sys.stderr)
    print("  → ~/macmini-setup/.venv/bin/pip install requests markdown", file=sys.stderr)
    print("  または ~/macmini-setup/.venv/bin/python3 post_wp.py ... で実行", file=sys.stderr)
    sys.exit(1)

VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
DRAFTS_DIR = VAULT / "actions" / "drafts"
ENV_PATH = Path.home() / ".toramemoblog.env"


def load_env(path: Path) -> dict[str, str]:
    """KEY=VALUE 形式の env を簡易パース。VALUE の前後の " と ' は剥がす。"""
    if not path.exists():
        print(f"ERROR: 認証情報ファイルが無い: {path}", file=sys.stderr)
        print("  必要なキー: WP_URL / WP_USER / WP_APP_PASSWORD", file=sys.stderr)
        sys.exit(1)

    # ファイル権限チェック（600 でなければ警告）
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        print(f"[warn] {path} の権限が 0o{mode:o} （0o600 推奨）", file=sys.stderr)

    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        # クォート除去（前後対応のもののみ）
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        env[k.strip()] = v

    for required in ("WP_URL", "WP_USER", "WP_APP_PASSWORD"):
        if not env.get(required):
            print(f"ERROR: {path} に {required} が無い", file=sys.stderr)
            sys.exit(1)

    # 末尾スラッシュ除去
    env["WP_URL"] = env["WP_URL"].rstrip("/")
    return env


def resolve_draft(arg: str) -> Path:
    """位置引数を下書きファイルパスに解決。"""
    p = Path(arg)
    if p.exists():
        return p
    # plugin 名として解決を試みる
    cand = DRAFTS_DIR / f"dalamud-{arg}-draft.md"
    if cand.exists():
        return cand
    return p  # 後段で exists() チェックされる


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """先頭の --- YAML --- を簡易パースして (dict, 本文) を返す。

    write_article.py が出す形式に限定（key: value のみ、ネスト無し）。
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 5:]
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip().strip('"').strip("'")
        fm[k.strip()] = v
    return fm, body


def md_to_html(body: str) -> str:
    """Markdown 本文を HTML に変換。"""
    return md_lib.markdown(
        body,
        extensions=["fenced_code", "tables", "sane_lists"],
        output_format="html",
    )


def decide_title(args_title: str | None, fm: dict[str, str], draft_path: Path) -> str:
    """タイトル決定優先順位: --title > suggested_title > plugin > ファイル名推測"""
    if args_title:
        return args_title
    if fm.get("suggested_title"):
        return fm["suggested_title"]
    if fm.get("plugin"):
        return fm["plugin"]
    # "dalamud-Echoglossian-draft.md" → "Echoglossian"
    name = draft_path.stem
    if name.startswith("dalamud-") and name.endswith("-draft"):
        return name[len("dalamud-"):-len("-draft")]
    return name


def parse_tag_ids(s: str | None) -> list[int]:
    if not s:
        return []
    return [int(x) for x in s.split(",") if x.strip()]


def wp_get_all(creds: dict[str, str], path: str, params: dict | None = None) -> list[dict]:
    """ページネーション対応の GET（全件取得）。"""
    out: list[dict] = []
    page = 1
    while True:
        p = {"per_page": 100, "page": page}
        if params:
            p.update(params)
        r = requests.get(
            f"{creds['WP_URL']}/wp-json/wp/v2/{path}",
            auth=(creds["WP_USER"], creds["WP_APP_PASSWORD"]),
            params=p, timeout=30,
        )
        if r.status_code == 400 and page > 1:
            # WP は範囲外ページで 400 を返す
            break
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def cmd_list_categories(creds: dict[str, str]) -> int:
    cats = wp_get_all(creds, "categories", {"orderby": "name", "order": "asc"})
    print(f"# {len(cats)} categories")
    for c in cats:
        print(f"{c['id']:>5}  {c['name']}  (count={c.get('count', 0)})")
    return 0


def cmd_list_tags(creds: dict[str, str]) -> int:
    tags = wp_get_all(creds, "tags", {"orderby": "count", "order": "desc"})
    print(f"# {len(tags)} tags (count desc)")
    for t in tags:
        print(f"{t['id']:>5}  {t['name']}  (count={t.get('count', 0)})")
    return 0


def post_draft(creds: dict[str, str], payload: dict) -> dict:
    r = requests.post(
        f"{creds['WP_URL']}/wp-json/wp/v2/posts",
        auth=(creds["WP_USER"], creds["WP_APP_PASSWORD"]),
        json=payload, timeout=60,
    )
    if r.status_code >= 400:
        print(f"ERROR: WP API {r.status_code}", file=sys.stderr)
        print(r.text[:2000], file=sys.stderr)
        if r.status_code in (401, 403):
            print("  → 認証確認: curl -u $WP_USER:$WP_APP_PASSWORD"
                  f" {creds['WP_URL']}/wp-json/wp/v2/users/me", file=sys.stderr)
        sys.exit(3)
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", nargs="?",
                    help="下書きMD のパス または plugin 名 (--list-* 時は不要)")
    ap.add_argument("--status", default="draft",
                    choices=["draft", "publish", "pending", "private"])
    ap.add_argument("--category-id", type=int, action="append", default=[],
                    help="カテゴリ ID（複数指定可）")
    ap.add_argument("--tag-ids", help="タグ ID をカンマ区切り (例: 1,2,3)")
    ap.add_argument("--title", help="タイトル上書き")
    ap.add_argument("--dry-run", action="store_true",
                    help="HTML を stdout に出力して終了（投稿しない）")
    ap.add_argument("--list-categories", action="store_true")
    ap.add_argument("--list-tags", action="store_true")
    args = ap.parse_args()

    creds = load_env(ENV_PATH)

    if args.list_categories:
        return cmd_list_categories(creds)
    if args.list_tags:
        return cmd_list_tags(creds)

    if not args.draft:
        ap.print_help(sys.stderr)
        print("\nERROR: draft 引数が必要", file=sys.stderr)
        return 1

    # 下書きロード
    draft_path = resolve_draft(args.draft)
    if not draft_path.exists():
        print(f"ERROR: 下書きファイルが無い: {draft_path}", file=sys.stderr)
        print(f"  ヒント: write_article.py で先に生成する", file=sys.stderr)
        return 1

    raw = draft_path.read_text(encoding="utf-8")
    fm, body_md = parse_frontmatter(raw)
    title = decide_title(args.title, fm, draft_path)
    html = md_to_html(body_md)

    print(f"[1/3] 下書きロード: {draft_path.name}", file=sys.stderr)
    print(f"      タイトル: {title}", file=sys.stderr)
    print(f"      本文 MD: {len(body_md):,} chars → HTML: {len(html):,} chars", file=sys.stderr)

    if args.dry_run:
        print(f"[dry-run] 投稿せず HTML を stdout に出力", file=sys.stderr)
        sys.stdout.write(html)
        if not html.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    # ペイロード組み立て
    payload = {
        "title": title,
        "content": html,
        "status": args.status,
        "categories": args.category_id,
        "tags": parse_tag_ids(args.tag_ids),
    }
    # 空配列は WP に送らない（既定カテゴリで処理される）
    if not payload["categories"]:
        del payload["categories"]
    if not payload["tags"]:
        del payload["tags"]

    print(f"[2/3] POST /wp-json/wp/v2/posts (status={args.status})...", file=sys.stderr)
    result = post_draft(creds, payload)

    post_id = result["id"]
    edit_url = f"{creds['WP_URL']}/wp-admin/post.php?post={post_id}&action=edit"
    preview_url = f"{creds['WP_URL']}/?p={post_id}&preview=true"
    print(f"[3/3] 投稿完了: post_id={post_id}", file=sys.stderr)
    print(f"      preview: {preview_url}", file=sys.stderr)
    # stdout には編集URLだけ
    print(edit_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
