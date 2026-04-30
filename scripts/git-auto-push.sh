#!/bin/bash
# Git Auto Push for macmini-setup
# 
# Usage: git-auto-push.sh [message]
# If no message provided, uses git staged changes as summary
# 
# Purpose: After manual edits to CLAUDE.md (or other files), automatically:
#   1. Stage changed files
#   2. Create commit with provided/auto message
#   3. Push to GitHub
#
# Should be called whenever CLAUDE.md is edited in an editor

set -e

REPO_DIR="$HOME/macmini-setup"
cd "$REPO_DIR"

# Detect changed files
CHANGED=$(git status --porcelain | grep -E "^\s?M\s" | awk '{print $2}' | tr '\n' ' ')

if [ -z "$CHANGED" ]; then
  echo "No changes detected. Nothing to commit."
  exit 0
fi

echo "📝 Detected changes: $CHANGED"

# Generate commit message
if [ -z "$1" ]; then
  # Auto-generate from changed files
  if echo "$CHANGED" | grep -q "CLAUDE.md"; then
    MSG="docs: update macmini service configuration and specs"
  elif echo "$CHANGED" | grep -q "services/"; then
    MSG="docs: update service documentation"
  else
    MSG="docs: update macmini-setup documentation"
  fi
else
  MSG="$1"
fi

echo "📌 Commit message: $MSG"

# Stage and commit
git add -A
git commit -m "$MSG"

# Push to GitHub
echo "🚀 Pushing to GitHub..."
git push origin main

echo "✅ Complete. Changes reflected on GitHub."
