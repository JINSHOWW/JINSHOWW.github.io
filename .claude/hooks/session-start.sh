#!/bin/bash
# Cloud/mobile sessions start in a fresh container: install graphify and rebuild the graph.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v graphify >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then uv tool install graphifyy >/dev/null 2>&1
  else pip install --user graphifyy >/dev/null 2>&1; fi
fi
command -v graphify >/dev/null 2>&1 || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" && graphify update . >/dev/null 2>&1
exit 0
