#!/usr/bin/env python3
"""
vault-auto-summarize.py
ToraVault の raw-sources/ を監視し、新規ファイルを検知したら
Claude Sonnet (Anthropic API) で要約を生成して wiki/summaries/ に保存する。
Anthropic が応答しない場合は Ollama (gemma4:e2b) にフォールバック。
"""

import os
import sys
import json
import time
import subprocess
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# ─── 設定 ────────────────────────────────────────────────────────────────────
VAULT_PATH = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/ToraVault"
RAW_SOURCES = VAULT_PATH / "raw-sources"
SUMMARIES   = VAULT_PATH / "wiki/summaries"
CONCEPTS    = VAULT_PATH / "wiki/concepts"

PROCESSED_FILE = Path.home() / ".hermes/vault-processed-files.json"
LOG_PATH       = Path.home() / "macmini-setup/logs/vault-summarize.log"

POLL_INTERVAL   = 3       # seconds
RETRY_INTERVAL  = 60      # seconds (Anthropic/Ollama 未起動時)
ICLOUD_WAIT_MAX = 30      # seconds (iCloud ダウンロード待ち最大)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-sonnet-4-6"
OLLAMA_API_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL      = "gemma4:e2b"

DISCORD_HOME_CHANNEL = "1499328996234625074"

SUMMARY_PROMPT = """\
あなたはObsidianのwikiページを生成するAIです。
以下の素材を読んで、wiki/summaries/に追加するObsidianノートを日本語で生成してください。

出力形式（Markdownのみ、余計なコメント不要）:
# [適切なタイトル]

## 概要
（2〜4文で内容の要点を述べる）

## 主要ポイント
- （箇条書きで3〜7つ）

## 関連概念
- （このメモと関連する概念・用語のリスト。なければ「なし」）

## Source
- ファイル: {filename}
- 生成日時: {datetime}

---

## 素材

{content}
"""

# ─── ロガー設定 ──────────────────────────────────────────────────────────────
def setup_logger():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("vault-summarize")
    if logger.handlers:
        return logger  # 二重登録防止
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    # FileHandler はデフォルトでバッファリングするため、emit ごとに flush するよう wrap
    _orig_emit = fh.emit
    def _flushing_emit(record):
        _orig_emit(record)
        fh.flush()
    fh.emit = _flushing_emit
    logger.addHandler(fh)
    # launchd 実行時は stdout をログファイルにリダイレクト済みのため StreamHandler は不要
    if sys.stdout.isatty():
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger

log = setup_logger()

# ─── 処理済みリスト管理 ──────────────────────────────────────────────────────
def load_processed() -> set:
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("processed", []))
        except Exception as e:
            log.warning(f"処理済みリスト読み込みエラー: {e}")
    return set()

def save_processed(processed: set):
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump({"processed": sorted(processed)}, f, ensure_ascii=False, indent=2)

# ─── iCloud ダウンロード対応 ─────────────────────────────────────────────────
def ensure_icloud_downloaded(path: Path) -> bool:
    """
    .icloud のプレースホルダーなら brctl download でダウンロードを要求し
    実体が現れるまで待機する。タイムアウトしたら False を返す。
    """
    icloud_placeholder = path.parent / f".{path.name}.icloud"
    if icloud_placeholder.exists() and not path.exists():
        log.info(f"iCloud ダウンロード待ち: {path.name}")
        try:
            subprocess.run(["brctl", "download", str(path)], check=False)
        except FileNotFoundError:
            pass  # brctl がない環境はスキップ
        for _ in range(ICLOUD_WAIT_MAX):
            time.sleep(1)
            if path.exists():
                return True
        log.warning(f"iCloud ダウンロードタイムアウト: {path.name}")
        return False
    return path.exists()

# ─── ファイル列挙 ────────────────────────────────────────────────────────────
def scan_raw_sources() -> List[Path]:
    """raw-sources/ 配下のテキストファイルを再帰的に列挙する（.icloud 除外）"""
    result = []
    for p in RAW_SOURCES.rglob("*"):
        # .icloud プレースホルダーは .名前.icloud 形式
        if p.suffix == ".icloud":
            continue
        if p.is_file() and p.suffix in (".md", ".txt", ".html", ".json", ".yaml", ".yml"):
            result.append(p)
    return result

# ─── LLM 呼び出し ────────────────────────────────────────────────────────────
def get_anthropic_key() -> str:
    """環境変数 → .env ファイルの順で ANTHROPIC_API_KEY を取得"""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""

def call_anthropic(prompt: str) -> Optional[str]:
    """Claude Sonnet API 呼び出し。エラー時は None を返す"""
    import urllib.request, urllib.error

    api_key = get_anthropic_key()
    if not api_key:
        log.warning("ANTHROPIC_API_KEY が見つかりません")
        return None

    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        log.warning(f"Anthropic HTTP エラー {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        log.warning(f"Anthropic 呼び出しエラー: {e}")
        return None

def call_ollama(prompt: str) -> Optional[str]:
    """Ollama gemma4:e2b 呼び出し。エラー時は None を返す"""
    import urllib.request, urllib.error

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
    except Exception as e:
        log.warning(f"Ollama 呼び出しエラー: {e}")
        return None

def generate_summary(filename: str, content: str) -> Optional[str]:
    """Claude Sonnet 優先、失敗時は Ollama にフォールバック"""
    prompt = SUMMARY_PROMPT.format(
        filename=filename,
        datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        content=content[:8000],  # 長すぎるファイルは先頭8000字
    )

    log.info(f"Claude Sonnet で要約生成中: {filename}")
    result = call_anthropic(prompt)
    if result:
        log.info("Claude Sonnet 要約生成成功")
        return result

    log.info(f"Ollama にフォールバック: {filename}")
    result = call_ollama(prompt)
    if result:
        log.info("Ollama 要約生成成功")
        return result

    log.warning(f"要約生成失敗 (両方エラー): {filename}")
    return None

# ─── Discord 通知 ────────────────────────────────────────────────────────────
def notify_discord(page_name: str, rel_path: str):
    """Discord API 直接呼び出しで home チャンネルに通知"""
    import urllib.request, urllib.error

    # BotトークンをDISCORD_BOT_TOKENから取得
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not bot_token:
        env_file = Path.home() / ".hermes/.env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DISCORD_BOT_TOKEN="):
                        bot_token = line.split("=", 1)[1].strip()
                        break

    if not bot_token:
        log.warning("DISCORD_BOT_TOKEN が見つかりません。通知をスキップ")
        return

    message = f"📄 新規wikiページを生成しました: **{page_name}**\n→ `wiki/summaries/{rel_path}`"
    payload = json.dumps({"content": message}).encode("utf-8")
    url = f"https://discord.com/api/v10/channels/{DISCORD_HOME_CHANNEL}/messages"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "ToraVaultAutoSummarize (https://github.com/zelos/macmini-setup, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                log.info(f"Discord 通知送信: {page_name}")
            else:
                log.warning(f"Discord 通知 HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        log.warning(f"Discord 通知 HTTP エラー {e.code}: {e.read().decode()[:100]}")
    except Exception as e:
        log.warning(f"Discord 通知エラー: {e}")

# ─── ファイル処理 ────────────────────────────────────────────────────────────
def process_file(raw_path: Path) -> bool:
    """
    1ファイルを処理して wiki/summaries/ に保存する。
    成功したら True、リトライが必要なら False を返す。
    """
    if not ensure_icloud_downloaded(raw_path):
        log.warning(f"スキップ（iCloud未ダウンロード）: {raw_path.name}")
        return False

    try:
        content = raw_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.error(f"ファイル読み込みエラー: {raw_path.name} - {e}")
        return True  # 読み込み不可は処理済み扱いにして無限ループを防ぐ

    if not content.strip():
        log.info(f"空ファイルのためスキップ: {raw_path.name}")
        return True

    summary = generate_summary(raw_path.name, content)
    if summary is None:
        return False  # リトライキューに残す

    # 出力パスを raw-sources からの相対パスを維持
    try:
        rel = raw_path.relative_to(RAW_SOURCES)
    except ValueError:
        rel = Path(raw_path.name)

    # summaries/ 配下に同じサブディレクトリ構造を作る
    out_path = SUMMARIES / rel.with_suffix(".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 既に同名ファイルがある場合はタイムスタンプ付きで保存
    if out_path.exists():
        stem = out_path.stem
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = out_path.with_name(f"{stem}-{ts}.md")

    out_path.write_text(summary, encoding="utf-8")
    log.info(f"要約保存: {out_path.relative_to(VAULT_PATH)}")

    # Discord 通知
    notify_discord(out_path.stem, str(out_path.relative_to(SUMMARIES)))

    return True

# ─── メインループ ────────────────────────────────────────────────────────────
def main():
    log.info("=== vault-auto-summarize 起動 ===")
    log.info(f"監視対象: {RAW_SOURCES}")
    log.info(f"出力先  : {SUMMARIES}")

    SUMMARIES.mkdir(parents=True, exist_ok=True)
    CONCEPTS.mkdir(parents=True, exist_ok=True)

    processed = load_processed()
    retry_queue: List[Path] = []
    last_retry_time = 0.0
    last_heartbeat = 0.0
    HEARTBEAT_INTERVAL = 60  # seconds

    while True:
        try:
            # 通常スキャン
            current_files = scan_raw_sources()
            new_files = [p for p in current_files if str(p) not in processed]

            now_hb = time.time()
            if (now_hb - last_heartbeat) >= HEARTBEAT_INTERVAL:
                last_heartbeat = now_hb
                log.info(f"heartbeat: scan={len(current_files)} processed={len(processed)} new={len(new_files)} retry_queue={len(retry_queue)}")

            for raw_path in new_files:
                log.info(f"新規ファイル検出: {raw_path.relative_to(RAW_SOURCES)}")
                success = process_file(raw_path)
                if success:
                    processed.add(str(raw_path))
                    save_processed(processed)
                else:
                    if raw_path not in retry_queue:
                        retry_queue.append(raw_path)
                        log.info(f"リトライキューに追加: {raw_path.name}")

            # リトライキュー処理（RETRY_INTERVAL ごと）
            now = time.time()
            if retry_queue and (now - last_retry_time) >= RETRY_INTERVAL:
                last_retry_time = now
                still_retry = []
                for raw_path in retry_queue:
                    log.info(f"リトライ: {raw_path.name}")
                    success = process_file(raw_path)
                    if success:
                        processed.add(str(raw_path))
                        save_processed(processed)
                    else:
                        still_retry.append(raw_path)
                retry_queue = still_retry

        except Exception as e:
            log.error(f"メインループ例外: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
