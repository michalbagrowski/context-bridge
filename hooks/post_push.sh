#!/bin/bash
# Auto-push context to claude.ai Project after significant git events.
# Configure as a Claude Code PostToolUse hook or git post-commit hook.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Use the repo's venv if available
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

"$PYTHON" -m context_bridge.push --auto 2>>/tmp/context-bridge-hook.log || true
