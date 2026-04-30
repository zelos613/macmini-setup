#!/usr/bin/env python3
"""
CLAUDE.md Auto-Updater for macmini-setup

Automatically updates CLAUDE.md when:
1. New MCP server is registered (hermes mcp add)
2. New launchd service is loaded (launchctl load)
3. New skill is created (skill_manage action=create)
4. New LLM model is added (Ollama/llama.cpp)

Usage:
  python3 auto-update-specs.py [action] [details]

Actions:
  mcp-add <name> <description>
  service-add <label> <description> <path>
  skill-create <name> <title> <category>
  model-add <type> <model-name> <model-path>

Example:
  python3 auto-update-specs.py mcp-add context-mode "FTS5 search & sandbox output"
  python3 auto-update-specs.py service-add com.hermesagent "Personal AI assistant" ~/.hermes
  python3 auto-update-specs.py skill-create my-skill "My Skill Title" development
"""

import sys
import re
from pathlib import Path
from datetime import datetime

REPO_DIR = Path.home() / "macmini-setup"
CLAUDE_MD = REPO_DIR / "CLAUDE.md"
LOG_FILE = REPO_DIR / "logs" / "auto-update.log"

LOG_FILE.parent.mkdir(exist_ok=True)


def log(msg):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")


def read_claude():
    """Read CLAUDE.md"""
    if not CLAUDE_MD.exists():
        log(f"❌ {CLAUDE_MD} not found")
        return None
    return CLAUDE_MD.read_text(encoding="utf-8")


def write_claude(content):
    """Write CLAUDE.md"""
    CLAUDE_MD.write_text(content, encoding="utf-8")
    log(f"✅ Updated {CLAUDE_MD}")


def add_mcp_server(name, description):
    """Add MCP server section"""
    content = read_claude()
    if not content:
        return False

    if "#### MCP サーバー" in content:
        # Already has MCP section, append to it
        mcp_entry = f"- **{name}**: {description}\n  - Auto-registered via hermes mcp add"
        content = content.replace(
            "#### MCP サーバー",
            f"#### MCP サーバー\n{mcp_entry}",
        )
    else:
        # No MCP section yet, add before iCloud Vault
        mcp_section = f"#### MCP サーバー\n- **{name}**: {description}\n  - Auto-registered via hermes mcp add\n"
        content = content.replace(
            "### iCloud Vault",
            mcp_section + "\n### iCloud Vault",
        )

    write_claude(content)
    return True


def add_launchd_service(label, description, path):
    """Add launchd service section"""
    content = read_claude()
    if not content:
        return False

    service_section = f"\n### {label.split('.')[-1].replace('-', ' ').title()}（{description}）\n- **場所**: `{path}`\n- **launchd**: `{label}`（常駐）\n- **役割**: {description}"

    # Insert before iCloud Vault or existing services section
    if "### iCloud Vault" in content:
        content = content.replace(
            "### iCloud Vault",
            service_section + "\n\n### iCloud Vault",
        )
    else:
        # Insert before external API section
        if "## 外部API連携" in content:
            content = content.replace(
                "## 外部API連携",
                service_section + "\n\n## 外部API連携",
            )

    write_claude(content)
    return True


def add_skill(name, title, category):
    """Add skill creation record"""
    content = read_claude()
    if not content:
        return False

    # Add to a "スキル" section if exists, or create it
    skill_section = f"\n- `{name}` ({category}): {title}"

    if "## スキル" not in content:
        # Create skills section before footer
        content = content.replace(
            "\n## ディレクトリ構成",
            f"\n## スキル\n\n{skill_section}\n\n## ディレクトリ構成",
        )
    else:
        # Append to existing skills section
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line == "## スキル":
                # Insert after section header
                lines.insert(i + 1, skill_section)
                content = "\n".join(lines)
                break

    write_claude(content)
    return True


def add_model(model_type, model_name, model_path):
    """Add LLM model"""
    content = read_claude()
    if not content:
        return False

    model_entry = f"\n- **{model_name}**: `{model_path}`"

    if model_type.lower() == "ollama":
        if "### Ollama（ローカルLLM）" in content:
            # Find the line after Ollama section
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "### Ollama（ローカルLLM）" in line:
                    # Insert after the existing model list
                    for j in range(i + 1, len(lines)):
                        if lines[j].startswith("### ") or lines[j].startswith("##"):
                            lines.insert(j, f"  - **{model_name}**: `{model_path}`")
                            content = "\n".join(lines)
                            break
                    break

    elif model_type.lower() in ["llama.cpp", "llama-cpp"]:
        if "### llama.cpp（ローカルLLM）" in content:
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "### llama.cpp（ローカルLLM）" in line:
                    for j in range(i + 1, len(lines)):
                        if (lines[j].startswith("### ") or
                            lines[j].startswith("##") or
                            lines[j].startswith("- **launchd")):
                            lines.insert(
                                j, f"- **{model_name}**: `{model_path}`\n"
                            )
                            content = "\n".join(lines)
                            break
                    break

    write_claude(content)
    return True


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]

    try:
        if action == "mcp-add" and len(sys.argv) >= 4:
            name = sys.argv[2]
            description = " ".join(sys.argv[3:])
            log(f"Adding MCP server: {name}")
            add_mcp_server(name, description)

        elif action == "service-add" and len(sys.argv) >= 5:
            label = sys.argv[2]
            description = sys.argv[3]
            path = sys.argv[4]
            log(f"Adding launchd service: {label}")
            add_launchd_service(label, description, path)

        elif action == "skill-create" and len(sys.argv) >= 5:
            name = sys.argv[2]
            title = sys.argv[3]
            category = sys.argv[4]
            log(f"Adding skill: {name}")
            add_skill(name, title, category)

        elif action == "model-add" and len(sys.argv) >= 5:
            model_type = sys.argv[2]
            model_name = sys.argv[3]
            model_path = " ".join(sys.argv[4:])
            log(f"Adding model: {model_name} ({model_type})")
            add_model(model_type, model_name, model_path)

        else:
            print(f"Unknown action: {action}")
            print(__doc__)
            sys.exit(1)

    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
