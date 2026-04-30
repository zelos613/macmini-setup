#!/bin/bash
# Hermes Wrapper for Auto-Updating CLAUDE.md
#
# Intercepts important hermes commands and auto-updates Mac Mini specs:
# - hermes mcp add → auto-update-specs.py mcp-add
# - hermes skill create → auto-update-specs.py skill-create (future)
#
# Usage: Source this in ~/.bash_profile or ~/.zshrc
#   source ~/macmini-setup/scripts/hermes-wrapper.sh

SPEC_UPDATER="$HOME/macmini-setup/scripts/auto-update-specs.py"

# Backup original hermes function (if any)
_original_hermes() {
  command hermes "$@"
}

hermes() {
  # Intercept 'hermes mcp add'
  if [[ "$1" == "mcp" && "$2" == "add" ]]; then
    _hermes_mcp_add "$@"
  else
    # Pass through to original hermes
    _original_hermes "$@"
  fi
}

_hermes_mcp_add() {
  # Extract MCP name from: hermes mcp add context-mode --command context-mode
  local mcp_name="$3"
  
  # Run original hermes mcp add
  _original_hermes "$@"
  local hermes_exit=$?
  
  if [ $hermes_exit -eq 0 ]; then
    # Generate description from MCP name
    local description="MCP server: $mcp_name"
    
    # Auto-update specs
    echo "📝 Auto-updating Mac Mini specs..."
    python3 "$SPEC_UPDATER" mcp-add "$mcp_name" "$description"
  fi
  
  return $hermes_exit
}

# Export function for subshells
export -f hermes _hermes_mcp_add _original_hermes
