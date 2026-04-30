#!/usr/bin/env python3
"""
File watcher for macmini-setup CLAUDE.md
Monitors changes and automatically pushes to GitHub

Usage:
  python3 watch-and-push.py

Runs as background process. Detects CLAUDE.md saves and auto-commits.
"""

import os
import subprocess
import time
from pathlib import Path
from datetime import datetime

REPO_DIR = Path.home() / "macmini-setup"
WATCH_FILE = REPO_DIR / "CLAUDE.md"
LOG_FILE = REPO_DIR / "logs" / "git-watch.log"

# Create logs directory
LOG_FILE.parent.mkdir(exist_ok=True)

def log(msg):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")

def git_push(message="docs: update macmini service configuration"):
    """Commit and push changes"""
    try:
        os.chdir(REPO_DIR)
        
        # Check if there are changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True
        )
        
        if not result.stdout.strip():
            return False
        
        # Stage changes
        subprocess.run(["git", "add", "-A"], check=True)
        
        # Commit
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            capture_output=True
        )
        
        # Push
        subprocess.run(
            ["git", "push", "origin", "main"],
            check=True,
            capture_output=True
        )
        
        log(f"✅ Pushed: {message}")
        return True
        
    except subprocess.CalledProcessError as e:
        log(f"❌ Git error: {e}")
        return False

def watch_file():
    """Watch CLAUDE.md for changes"""
    last_mtime = 0
    
    log("🔍 Starting file watcher for CLAUDE.md")
    
    while True:
        try:
            if not WATCH_FILE.exists():
                log(f"⚠️  {WATCH_FILE} not found")
                time.sleep(5)
                continue
            
            current_mtime = WATCH_FILE.stat().st_mtime
            
            # File was modified
            if current_mtime > last_mtime and last_mtime > 0:
                log("📝 Detected CLAUDE.md change, waiting for save to complete...")
                time.sleep(2)  # Wait for file to be fully written
                
                # Double-check file hasn't changed again (still being written)
                time.sleep(0.5)
                new_mtime = WATCH_FILE.stat().st_mtime
                
                if new_mtime == current_mtime:
                    # File save is complete
                    git_push()
                else:
                    log("⏳ File still being written, skipping this time")
            
            last_mtime = current_mtime
            time.sleep(2)  # Check every 2 seconds
            
        except KeyboardInterrupt:
            log("⛔ Watcher stopped")
            break
        except Exception as e:
            log(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    watch_file()
