#!/usr/bin/env python3
"""Hourly auto-updater for toradiscordbot."""
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "claude-agent" / "logs" / "actions.md"
NOTIFY = Path.home() / "claude-agent" / "notify.py"

SERVICE = "com.toradiscordbot"
REPO_DIR = Path.home() / "toradiscordbot"
NODE_BIN = "/opt/homebrew/opt/node@22/bin"


def log(tag: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"[{ts}] {tag}: {msg}\n")


def notify(msg: str) -> None:
    subprocess.run([sys.executable, str(NOTIFY), msg], timeout=15)


def git(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=str(REPO_DIR),
        capture_output=True, text=True,
        **kwargs,
    )


def get_uid() -> str:
    return str(os.getuid())


def restart_service() -> bool:
    r = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{get_uid()}/{SERVICE}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        plist = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE}.plist"
        subprocess.run(["launchctl", "unload", str(plist)])
        r2 = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
        return r2.returncode == 0
    return True


def main() -> None:
    # fetch without changing local state
    r = git(["fetch", "origin", "main"])
    if r.returncode != 0:
        log("ERROR", f"git fetch 失敗: {r.stderr.strip()[:200]}")
        return

    # check if remote has new commits
    local = git(["rev-parse", "HEAD"]).stdout.strip()
    remote = git(["rev-parse", "origin/main"]).stdout.strip()

    if local == remote:
        log("CHECK", "toradiscordbot 最新（更新なし）")
        return

    # count new commits and list changed files
    new_commits = git(["log", "--oneline", f"{local}..{remote}"]).stdout.strip()
    changed_files = git(["diff", "--name-only", local, remote]).stdout.strip().splitlines()
    ts_short = datetime.now().strftime("%H:%M")

    log("UPDATE", f"新しいコミットを検出:\n{new_commits}")

    # pull
    r = git(["pull", "--ff-only", "origin", "main"])
    if r.returncode != 0:
        log("ERROR", f"git pull 失敗: {r.stderr.strip()[:200]}")
        notify(f"🚨 toradiscordbot 自動更新失敗（git pull エラー） [{ts_short}]")
        return

    log("UPDATE", "git pull 完了")

    # npm install if package files changed
    pkg_changed = any(
        f in ("package.json", "package-lock.json") for f in changed_files
    )
    if pkg_changed:
        npm = f"{NODE_BIN}/npm"
        r = subprocess.run(
            [npm, "install"],
            cwd=str(REPO_DIR),
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{NODE_BIN}:/opt/homebrew/bin:/usr/bin:/bin"},
        )
        if r.returncode != 0:
            log("ERROR", f"npm install 失敗: {r.stderr.strip()[:200]}")
            notify(f"🚨 toradiscordbot 自動更新失敗（npm install エラー） [{ts_short}]")
            return
        log("UPDATE", "npm install 完了")

    # restart
    ok = restart_service()
    commit_summary = new_commits.split("\n")[0][:80]  # first commit line
    n = len(new_commits.splitlines())

    if ok:
        log("RESTART", f"{SERVICE} 再起動成功（{n}コミット適用）")
        extra = "（npm install 実行）" if pkg_changed else ""
        notify(f"✅ toradiscordbot を自動更新しました [{ts_short}]{extra}\n{commit_summary}" + (f" 他{n-1}件" if n > 1 else ""))
    else:
        log("ERROR", f"{SERVICE} 再起動失敗")
        notify(f"🚨 toradiscordbot 更新後の再起動失敗 [{ts_short}] — 手動確認が必要です")


if __name__ == "__main__":
    main()
