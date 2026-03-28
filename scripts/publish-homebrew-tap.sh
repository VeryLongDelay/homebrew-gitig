#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<USAGE
Usage:
  $(basename "$0") <tap-dir>

Example:
  $(basename "$0") ../homebrew-tap
USAGE
}

if [[ "${1:-}" == "" ]] || [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAP_DIR="$1"
FORMULA_DIR="$TAP_DIR/Formula"
OUT_FORMULA="$FORMULA_DIR/gitig.rb"
VERSION="$(node -p "require(process.argv[1]).version" "$ROOT_DIR/package.json")"

mkdir -p "$FORMULA_DIR"
"$ROOT_DIR/scripts/release-homebrew.sh" "$OUT_FORMULA"

printf 'Updated tap formula:\n  %s\n\nSuggested next commands:\n  cd "%s"\n  git add Formula/gitig.rb\n  git commit -m "gitig %s"\n  git push\n' "$OUT_FORMULA" "$TAP_DIR" "$VERSION"
