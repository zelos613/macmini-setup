#!/usr/bin/env python3
"""
Stage 3-A: 記事下書き生成

collect.py が生成した素材ファイル (raw-sources/articles/dalamud-*-source.md) を
入力に、Claude Opus を `claude -p` (Pro OAuth) で呼び出し、
ブログ下書き原稿 (actions/drafts/dalamud-*-draft.md) を生成する。

使い方:
    python3 write_article.py raw-sources/articles/dalamud-lokinmodar_Echoglossian-source.md
    python3 write_article.py lokinmodar/Echoglossian
    python3 write_article.py lokinmodar/Echoglossian --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
ARTICLES_DIR = VAULT / "raw-sources" / "articles"
DRAFTS_DIR = VAULT / "actions" / "drafts"
PHILOSOPHY_PATH = VAULT / "wiki" / "concepts" / "FF14ツール哲学.md"

DEFAULT_SAMPLES = ["haseltweaks", "vnavmesh", "craftimizer"]
DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_TIMEOUT = 900  # 15分

# サンプル記事のボイラープレート（免責・Discord案内）を切り捨てるための目印。
# 最初に現れた行までを捨てて、それ以降を few-shot として使う。
BODY_START_MARKERS = ("もくじ", "概要", "このプラグインについて", "導入方法")

PHILOSOPHY_FALLBACK = """\
- ツール使用者はマイノリティであり、日陰ものの自覚を持つ
- 「他人に迷惑をかけない」が大前提。バレないように使う覚悟も含む
- PvPでの使用、課金外見Modの共有はNG
- スクエニ規約への不満を外に出さない（自己責任の二択）
- ツールは「補助」であって「代替」ではない
"""


def resolve_source_path(arg: str) -> Path:
    """位置引数を素材ファイルのパスに解決する。

    - "owner/repo" 形式なら ARTICLES_DIR/dalamud-owner_repo-source.md
    - それ以外はそのままパスとして扱う（相対/絶対両対応）
    """
    if "/" in arg and not arg.endswith(".md") and not Path(arg).exists():
        safe = arg.replace("/", "_")
        return ARTICLES_DIR / f"dalamud-{safe}-source.md"
    p = Path(arg)
    if not p.is_absolute():
        # スクリプト実行ディレクトリ基準で探し、なければ ARTICLES_DIR も試す
        cand = Path.cwd() / p
        if cand.exists():
            return cand
        cand2 = ARTICLES_DIR / p.name
        if cand2.exists():
            return cand2
    return p


def load_source(path: Path) -> dict:
    """素材ファイルを読み込み、メタ情報と全文を返す。"""
    text = path.read_text(encoding="utf-8")

    # フルネーム抽出（例: `- フルネーム: \`lokinmodar/Echoglossian\``）
    m = re.search(r"フルネーム:\s*`([^`]+)`", text)
    full_name = m.group(1) if m else "unknown/unknown"
    plugin_name = full_name.split("/")[-1]

    # リポジトリURL抽出
    m = re.search(r"リポジトリ:\s*<([^>]+)>", text)
    repo_url = m.group(1) if m else f"https://github.com/{full_name}"

    # カスタムリポジトリURL（あれば最初の1つ）
    m = re.search(r"## カスタムリポジトリURL候補\n((?:- .+\n)+)", text)
    custom_repo_block = m.group(1) if m else ""
    custom_repos = re.findall(r"`([^`]+repo\.json)`", custom_repo_block)

    return {
        "path": path,
        "text": text,
        "full_name": full_name,
        "plugin_name": plugin_name,
        "repo_url": repo_url,
        "custom_repos": custom_repos,
    }


def strip_boilerplate(sample_text: str) -> str:
    """サンプル記事の先頭ボイラープレートを除去する。

    記事先頭の URL/タイトル/日付/区切り線/免責/Discord案内/更新履歴は
    ブログのテンプレートで挿入される共通部分なので、本文学習用には不要。
    """
    lines = sample_text.splitlines()
    # 最初の本文マーカー出現行で切る
    cut = 0
    for i, line in enumerate(lines):
        if any(line.strip().startswith(m) or line.strip() == m for m in BODY_START_MARKERS):
            cut = i
            break
    return "\n".join(lines[cut:]).strip() + "\n"


def select_samples(names: list[str]) -> list[tuple[str, str]]:
    """サンプル名リスト → (ファイル名, ボイラープレート除去済み本文) のリスト。"""
    out: list[tuple[str, str]] = []
    missing: list[str] = []
    for name in names:
        p = ARTICLES_DIR / f"{name}.txt"
        if not p.exists():
            missing.append(name)
            continue
        text = p.read_text(encoding="utf-8")
        out.append((p.name, strip_boilerplate(text)))
    if missing:
        print(f"[warn] サンプル記事が見つからない: {', '.join(missing)}", file=sys.stderr)
    return out


def load_philosophy() -> str:
    """FF14ツール哲学.md を読む。無ければフォールバック。"""
    if PHILOSOPHY_PATH.exists():
        return PHILOSOPHY_PATH.read_text(encoding="utf-8")
    return PHILOSOPHY_FALLBACK


def build_prompt(source: dict, samples: list[tuple[str, str]], philosophy: str,
                 extra_instruction: str | None = None) -> str:
    """Claude に渡す一発生成プロンプトを組み立てる。"""
    has_custom_repo = bool(source["custom_repos"])
    install_hint = (
        "素材にカスタムリポジトリURLがあるので、"
        "「Dalamud設定 → 試験的機能タブ → URL入力 → ＋ → 保存マーク → 『すべてのプラグイン』で検索 → インストール」のテンプレで書く。"
        if has_custom_repo
        else "素材にカスタムリポジトリURLが無い（公式Dalamudプラグインリポジトリ掲載と推測される）ので、"
        "「Dalamudの『すべてのプラグイン』タブで検索 → インストール」のシンプルな手順で書く。カスタムリポジトリ追加手順は書かない。"
    )

    sample_blocks = []
    for fname, body in samples:
        sample_blocks.append(f"--- 文体サンプル: {fname} ---\n{body}\n--- ここまで ---\n")
    samples_section = "\n".join(sample_blocks)

    return f"""\
あなたは「とらまめ」というFF14ブロガー。Dalamudプラグインの紹介記事を日本語で書く。
以下の制約とガイドを厳守して、素材ファイルから記事本文(Markdown)を1本生成する。

# 出力ルール（最優先）

- 出力は **Markdown 本文のみ**。前置き・後置きの説明文・「了解しました」等は一切書かない。
- 1行目を **`<!-- TITLE: 〜 -->`** にする（タイトル案。本文には含めない扱い）。
- 2行目以降が本文。**H1 (`#`) は使わない**。本文は H2 (`##`) から開始。
- コードブロックは ``` で囲む。
- 公式リポジトリURL `{source['repo_url']}` を本文中に1回入れる（導入方法か末尾あたり）。
- 各機能・設定の節末に **`<!-- SCREENSHOT: 〇〇画面 -->`** を1つ挿入する。〇〇は具体的な画面名（例: 設定画面 / インストール画面 / 翻訳オーバーレイ）。
- 素材ファイルに存在しないURL・機能・コマンドは **絶対に捏造しない**。

# 文体ガイド

- 口語・短文・箇条書き多め。だらだら長文化しない。
- プラグイン名は英語表記のまま。
- 「〜という感じ」「〜ですね」「〜してくれます」など柔らかい結び。
- 「ｗ」はたまに使う程度。多用しない。
- スクエニ批判・規約への不満は書かない。
- 「導入を推奨するものではない、自己責任」スタンスを節々に滲ませる。
- 派手な煽り・誇張・最上級表現（最強・神プラグイン等）は避ける。

# FF14ツール哲学（書き手の価値観・記事には直接書かないが文体に滲ませる）

{philosophy.strip()}

# 構成テンプレート

1. **概要** — このプラグインは何か / 誰向けか（1〜2段落）
2. **導入方法** — {install_hint}
3. **主な機能・特徴** — 機能ごとに小見出し（`### 〇〇`）。各節末にスクショプレースホルダ。
4. **使い方の流れ** — 起動から実用までの一連の操作
5. **使ってみた想定シーン** — 「〜なときに便利」調で1〜3例
6. **あとがき** — 1〜3文。力みすぎず軽く締める

# 文体サンプル（3本。先頭のテンプレヘッダは除去済み）

{samples_section}

# 素材ファイル（このプラグインについての全情報源）

{source['text']}

# 生成指示

上記の素材ファイルだけを情報源にして、「文体サンプル」の書き口を踏襲した
記事本文(Markdown)を生成してください。1行目は `<!-- TITLE: 〜 -->`、2行目以降が本文です。
{('''
# 今回の追加指示（最優先・上の構成テンプレートを上書きしてよい）

''' + extra_instruction.strip() + '\n') if extra_instruction else ''}"""


def call_claude(prompt: str, model: str, timeout: int) -> str:
    """`claude -p` を Pro OAuth で呼ぶ。ANTHROPIC_API_KEY は外す。"""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "text",
        "--no-session-persistence",
    ]
    try:
        r = subprocess.run(
            cmd, input=prompt, env=env,
            capture_output=True, text=True, check=True, timeout=timeout,
        )
        return r.stdout
    except FileNotFoundError:
        print("ERROR: `claude` バイナリが見つからない。Claude Code がインストールされているか確認。", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: claude 呼び出しが {timeout}s で timeout", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: claude が失敗 (exit {e.returncode})", file=sys.stderr)
        print("--- stderr ---", file=sys.stderr)
        print(e.stderr[:2000], file=sys.stderr)
        if "login" in (e.stderr or "").lower() or "auth" in (e.stderr or "").lower():
            print("→ `claude /login` で再認証が必要かもしれません。", file=sys.stderr)
        sys.exit(3)


def postprocess(raw: str) -> tuple[str, str | None, list[str]]:
    """LLM出力を整形し、(本文, タイトル案, 警告リスト) を返す。"""
    warnings: list[str] = []
    text = raw.strip()

    # 先頭のコードフェンス剥がし対策（```markdown ... ``` で囲まれてくる事故）
    if text.startswith("```"):
        # 最初の改行までを捨て、末尾の ``` も除去
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    # タイトル抽出
    title = None
    m = re.match(r"<!--\s*TITLE:\s*(.+?)\s*-->\s*\n", text)
    if m:
        title = m.group(1).strip()
        text = text[m.end():]
    else:
        warnings.append("TITLE コメントが見つからなかった")

    # スクショプレースホルダ数チェック
    n_screenshots = len(re.findall(r"<!--\s*SCREENSHOT:", text))
    if n_screenshots == 0:
        warnings.append("SCREENSHOT プレースホルダが1つも入っていない")
    elif n_screenshots < 2:
        warnings.append(f"SCREENSHOT プレースホルダが {n_screenshots} 個しかない（推奨: 3以上）")

    # H2 個数チェック
    n_h2 = len(re.findall(r"^## ", text, re.MULTILINE))
    if n_h2 < 3:
        warnings.append(f"H2 (`##`) の節が {n_h2} 個しかない（構成スカスカの可能性）")

    # H1 混入チェック
    if re.search(r"^# ", text, re.MULTILINE):
        warnings.append("H1 (`# `) が混入している（ルール違反）")

    return text.strip() + "\n", title, warnings


def build_frontmatter(source: dict, title: str | None, model: str) -> str:
    """YAML front matter を組み立てる。"""
    now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    # +0900 → +09:00 整形
    now = re.sub(r"(\+\d{2})(\d{2})$", r"\1:\2", now)
    title_line = f'suggested_title: "{title}"' if title else "suggested_title: null"
    return f"""\
---
plugin: {source['plugin_name']}
repo_url: {source['repo_url']}
source_file: {source['path'].name}
generated_at: {now}
model: {model}
{title_line}
---

"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="素材mdのパス、または owner/repo")
    ap.add_argument("--samples", default=",".join(DEFAULT_SAMPLES),
                    help=f"文体サンプル名 (カンマ区切り、.txt 拡張子なし)。デフォルト: {','.join(DEFAULT_SAMPLES)}")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Claude モデル (alias可)。デフォルト: {DEFAULT_MODEL}")
    ap.add_argument("--output", default=None, help="出力先パス（省略時は actions/drafts/ に自動命名）")
    ap.add_argument("--dry-run", action="store_true", help="プロンプトを stdout に出力して終了（claude 呼ばない）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"claude 呼び出し timeout 秒 (default: {DEFAULT_TIMEOUT})")
    ap.add_argument("--extra-instruction", default=None,
                    help="プロンプト末尾に追加注入する指示テキスト（@<path> で指定するとファイルから読み込む）")
    args = ap.parse_args()

    # --extra-instruction が @<path> 形式ならファイルから読む
    extra = args.extra_instruction
    if extra and extra.startswith("@"):
        ext_path = Path(extra[1:]).expanduser()
        if not ext_path.exists():
            print(f"ERROR: --extra-instruction のファイルが無い: {ext_path}", file=sys.stderr)
            return 1
        extra = ext_path.read_text(encoding="utf-8")

    # 1. 素材ロード
    src_path = resolve_source_path(args.source)
    if not src_path.exists():
        print(f"ERROR: 素材ファイルが見つからない: {src_path}", file=sys.stderr)
        print(f"  ヒント: 先に `python3 collect.py {args.source}` を実行する", file=sys.stderr)
        return 1
    source = load_source(src_path)
    print(f"[1/4] 素材ロード: {source['full_name']} ({src_path.name})", file=sys.stderr)

    # 2. サンプル＆哲学
    sample_names = [s.strip() for s in args.samples.split(",") if s.strip()]
    samples = select_samples(sample_names)
    if not samples:
        print("ERROR: サンプル記事が1つも見つからない", file=sys.stderr)
        return 1
    print(f"[2/4] サンプル選定: {len(samples)} 本", file=sys.stderr)
    philosophy = load_philosophy()

    # 3. プロンプト組み立て
    prompt = build_prompt(source, samples, philosophy, extra)
    print(f"[3/4] プロンプト構築 ({len(prompt):,} chars{', +extra' if extra else ''})", file=sys.stderr)

    if args.dry_run:
        sys.stdout.write(prompt)
        return 0

    # 4. Claude 呼び出し
    print(f"[4/4] Claude 呼び出し (model={args.model}, timeout={args.timeout}s)...", file=sys.stderr)
    raw = call_claude(prompt, args.model, args.timeout)

    # 5. 後処理
    body, title, warnings = postprocess(raw)
    for w in warnings:
        print(f"[warn] {w}", file=sys.stderr)

    # 6. 出力
    if args.output:
        out_path = Path(args.output)
    else:
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DRAFTS_DIR / f"dalamud-{source['plugin_name']}-draft.md"

    front = build_frontmatter(source, title, args.model)
    out_path.write_text(front + body, encoding="utf-8")
    print(f"      → {out_path}", file=sys.stderr)
    if title:
        print(f"      タイトル案: {title}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
