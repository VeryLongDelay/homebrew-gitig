#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_JSON="$ROOT_DIR/package.json"
FORMULA_TEMPLATE="$ROOT_DIR/Formula/gitig.rb"
OUT_FORMULA="${1:-$ROOT_DIR/.brew/gitig.rb}"
WORK_DIR="$ROOT_DIR/.brew"

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "error: missing required command: $1" >&2
        exit 1
    }
}

require_cmd node
require_cmd npm
require_cmd shasum

mkdir -p "$WORK_DIR"

VERSION="$(node -p "require(process.argv[1]).version" "$PACKAGE_JSON")"
PACK_OUTPUT="$(cd "$ROOT_DIR" && npm pack --silent --ignore-scripts --pack-destination "$WORK_DIR")"
TARBALL="$WORK_DIR/$PACK_OUTPUT"
SHA256="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"

sed \
    -e "s/__VERSION__/$VERSION/g" \
    -e "s/__SHA256__/$SHA256/g" \
    "$FORMULA_TEMPLATE" > "$OUT_FORMULA"

cat <<EOF
Created:
  $OUT_FORMULA

Version:
  $VERSION

Tarball:
  $TARBALL

SHA256:
  $SHA256

Next:
  1. Publish version $VERSION to npm.
  2. Commit the generated formula into your tap repo under Formula/gitig.rb.
  3. Run: brew install <tap>/gitig
EOF
