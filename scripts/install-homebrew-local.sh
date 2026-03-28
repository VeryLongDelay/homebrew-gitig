#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage:
  install-homebrew-local.sh [tap-dir]

Examples:
  ./scripts/install-homebrew-local.sh
  ./scripts/install-homebrew-local.sh ../homebrew-tap
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAP_DIR="${1:-$ROOT_DIR/.homebrew-tap}"
FORMULA_DIR="$TAP_DIR/Formula"
FORMULA_PATH="$FORMULA_DIR/gitig.rb"
TAP_NAME="local/tap"

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "error: missing required command: $1" >&2
        exit 1
    }
}

require_cmd brew
require_cmd git
require_cmd npm
require_cmd node

BREW_BIN="$(command -v brew)"
BREW_PREFIX="$("$BREW_BIN" --prefix)"
MACHINE_ARCH="$(uname -m)"
SHELL_ARCH="$(uname -p 2>/dev/null || true)"

brew_cmd() {
    if [[ "$BREW_PREFIX" == "/opt/homebrew" && "$MACHINE_ARCH" == "arm64" ]]; then
        arch -arm64 "$BREW_BIN" "$@"
    else
        "$BREW_BIN" "$@"
    fi
}

mkdir -p "$FORMULA_DIR"

"$ROOT_DIR/scripts/release-homebrew.sh" "$FORMULA_PATH"

if [[ ! -d "$TAP_DIR/.git" ]]; then
    git -C "$TAP_DIR" init
fi

if [[ ! -f "$TAP_DIR/README.md" ]]; then
    cat > "$TAP_DIR/README.md" <<'README'
# homebrew-tap

Local Homebrew tap for testing gitig.
README
fi

git -C "$TAP_DIR" add Formula/gitig.rb README.md >/dev/null 2>&1 || true
if ! git -C "$TAP_DIR" diff --cached --quiet >/dev/null 2>&1; then
    git -C "$TAP_DIR" \
        -c user.name="gitig local tap" \
        -c user.email="local@example.com" \
        commit -m "Update gitig formula" >/dev/null
fi

brew_cmd untap "$TAP_NAME" >/dev/null 2>&1 || true
brew_cmd tap "$TAP_NAME" "$TAP_DIR"

brew_cmd uninstall --force gitig >/dev/null 2>&1 || true
brew_cmd install --build-from-source "$TAP_NAME/gitig"

echo
echo "Installed from local tap:"
echo "  $TAP_NAME/gitig"
echo "  brew prefix: $BREW_PREFIX"
echo "  machine arch: $MACHINE_ARCH"
echo "  shell arch: ${SHELL_ARCH:-unknown}"
echo
gitig help
