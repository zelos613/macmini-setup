#!/usr/bin/env python3
"""
Claude Code セッション保存スクリプト（Stop hook 用）

Claude Code の Stop hook から呼ばれ、現セッションの JSONL transcript を
読みやすい Markdown に変換して ToraVault/raw-sources/claude-sessions/ に
保存する。既存の vault-auto-summarize がそれを拾って要約を生成する。

設計方針:
  - 冪等: 毎ターン JSONL を真実の源として全文再生成（途中クラッシュ復旧不要）
  - 5ユーザーターン未満はスキップ（ノイズ隔離）
  - user プロンプト全文 + assistant の text ブロックのみ保存
  - thinking / tool_use / tool_result の内容はスキップ（件数だけ要約）
  - 「やり残し」検出を意識して assistant の最終応答は全文保存
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

VAULT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
OUT_DIR = VAULT / "raw-sources" / "claude-sessions"
MIN_USER_TURNS = 5  # これ未満のセッションは保存しない


def read_hook_input():
    """Stop hook の stdin JSON から transcript_path / session_id を取得。
    手動実行用に環境変数フォールバックも用意。"""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}
    tp = data.get("transcript_path") or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    sid = data.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    return tp, sid


def load_events(path):
    out = []
    with open(path, errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def is_pure_user_text(ev):
    """tool_result でも system reminder でもない、ユーザー入力の text。"""
    if ev.get("type") != "user":
        return False
    msg = ev.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        has_tool_result = any(x.get("type") == "tool_result" for x in c if isinstance(x, dict))
        has_text = any(
            isinstance(x, dict) and x.get("type") == "text" and (x.get("text") or "").strip()
            for x in c
        )
        return has_text and not has_tool_result
    return False


def extract_user_text(ev):
    c = (ev.get("message") or {}).get("content")
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        return "\n".join(
            (x.get("text") or "").strip()
            for x in c
            if isinstance(x, dict) and x.get("type") == "text"
        ).strip()
    return ""


def extract_assistant(ev):
    """assistant の text ブロック全文 + tool 呼び出し件数。"""
    c = (ev.get("message") or {}).get("content") or []
    texts = []
    tool_names = []
    for x in c:
        if not isinstance(x, dict):
            continue
        if x.get("type") == "text":
            t = (x.get("text") or "").strip()
            if t:
                texts.append(t)
        elif x.get("type") == "tool_use":
            tool_names.append(x.get("name") or "?")
    text = "\n\n".join(texts).strip()
    tool_summary = ""
    if tool_names:
        cnt = Counter(tool_names)
        parts = ", ".join(f"{n}×{c}" for n, c in cnt.most_common())
        tool_summary = f"🔧 [{len(tool_names)} tool calls: {parts}]"
    return text, tool_summary


def fmt_ts(ev):
    ts = ev.get("timestamp")
    if not ts:
        return ""
    try:
        # transcript には ISO 8601 UTC で記録される
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%H:%M")
    except Exception:
        return ""


def build_markdown(events, session_id):
    # ユーザーターンを起点に区切り、各ターン内の assistant 応答をまとめる
    turns = []  # list of {user_text, ts, assistant_blocks: [(text, tool_summary), ...]}
    cur = None
    for ev in events:
        if is_pure_user_text(ev):
            if cur is not None:
                turns.append(cur)
            cur = {
                "user_text": extract_user_text(ev),
                "ts": fmt_ts(ev),
                "assistant_blocks": [],
            }
        elif ev.get("type") == "assistant" and cur is not None:
            txt, tools = extract_assistant(ev)
            if txt or tools:
                cur["assistant_blocks"].append((txt, tools))
    if cur is not None:
        turns.append(cur)

    if len(turns) < MIN_USER_TURNS:
        return None, len(turns)

    first_ts = next((t["ts"] for t in turns if t["ts"]), "")
    date_str = datetime.now().strftime("%Y-%m-%d")
    short_id = (session_id or "unknown")[:8]
    header_time = first_ts or datetime.now().strftime("%H:%M")
    lines = [
        f"# Claude Code Session {date_str} {header_time} (id: {short_id})",
        "",
        f"_保存時刻: {datetime.now():%Y-%m-%d %H:%M:%S} / ユーザーターン数: {len(turns)}_",
        "",
    ]
    for i, t in enumerate(turns, 1):
        ts_label = f" ({t['ts']})" if t["ts"] else ""
        lines.append(f"## ターン {i}{ts_label}")
        lines.append("")
        lines.append("**user**:")
        lines.append("")
        lines.append(t["user_text"])
        lines.append("")
        for j, (txt, tools) in enumerate(t["assistant_blocks"], 1):
            tag = "**assistant**:" if j == 1 else "**assistant (続き)**:"
            lines.append(tag)
            lines.append("")
            if txt:
                lines.append(txt)
                lines.append("")
            if tools:
                lines.append(tools)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n", len(turns)


def write_atomically(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def main():
    transcript_path, session_id = read_hook_input()
    if not transcript_path or not os.path.exists(transcript_path):
        # hook 起動条件が満たされないだけ。静かに終了（Claude Code を妨げない）
        return 0
    try:
        events = load_events(transcript_path)
        md, turn_count = build_markdown(events, session_id or "")
        if md is None:
            return 0  # ターン数未満
        date_str = datetime.now().strftime("%Y-%m-%d")
        month_dir = datetime.now().strftime("%Y-%m")
        short_id = (session_id or "unknown")[:8]
        out = OUT_DIR / month_dir / f"claude-{date_str}-{short_id}.md"
        write_atomically(out, md)
    except Exception as exc:
        # hook 失敗は Claude Code を止めない。stderr に出すだけ
        print(f"save-claude-session: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
