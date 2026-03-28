#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_PATH="${1:-$ROOT_DIR/.brew/gitig.rb}"

if [[ ! -f "$FORMULA_PATH" ]]; then
    echo "error: formula not found: $FORMULA_PATH" >&2
    echo "hint: run scripts/release-homebrew.sh first" >&2
    exit 1
fi

brew uninstall --force gitig >/dev/null 2>&1 || true
brew install --build-from-source "$FORMULA_PATH"
gitig help
