#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<USAGE
Usage:
  $(basename "$0") <owner> [tap-dir]

Examples:
  $(basename "$0") billxiong
  $(basename "$0") billxiong ../homebrew-tap

This creates a Homebrew tap repo scaffold for a repository typically named:
  homebrew-tap
USAGE
}

if [[ "${1:-}" == "" ]] || [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

OWNER="$1"
TAP_DIR="${2:-homebrew-tap}"
TAP_NAME="${OWNER}/tap"

mkdir -p "$TAP_DIR/Formula"
mkdir -p "$TAP_DIR/.github/workflows"

cat > "$TAP_DIR/README.md" <<README
# homebrew-tap

Homebrew tap for **gitig**.

## Install


tap this repository:

\`\`\`bash
brew tap ${TAP_NAME}
\`\`\`

install the formula:

\`\`\`bash
brew install gitig
\`\`\`

or in one line:

\`\`\`bash
brew install ${TAP_NAME}/gitig
\`\`\`

## Upgrade

\`\`\`bash
brew update
brew upgrade gitig
\`\`\`

## What this tap contains

- \`Formula/gitig.rb\`

## Releasing a new version

From the main \`gitig\` repo:

\`\`\`bash
npm run build
npm publish
./scripts/publish-homebrew-tap.sh ../${TAP_DIR}
\`\`\`

Then in this tap repo:

\`\`\`bash
git add Formula/gitig.rb README.md .github/workflows/test.yml
git commit -m "gitig <version>"
git push
\`\`\`
README

cat > "$TAP_DIR/.github/workflows/test.yml" <<'YAML'
name: test-formula

on:
  push:
    branches: [ main ]
  pull_request:
  workflow_dispatch:

jobs:
  brew-test:
    runs-on: macos-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Tap formula
        run: |
          brew tap --overwrite local/tap "$GITHUB_WORKSPACE"
          brew install --formula local/tap/gitig

      - name: Smoke test
        run: |
          gitig help
YAML

if [[ ! -f "$TAP_DIR/Formula/gitig.rb" ]]; then
    cat > "$TAP_DIR/Formula/.gitkeep" <<'KEEP'
# Remove this file after the first generated formula is added.
KEEP
fi

printf 'Created Homebrew tap scaffold:\n  %s\n\nNext:\n  1. Create a GitHub repo named homebrew-tap under %s.\n  2. Push this scaffold there.\n  3. From the gitig repo, run:\n       ./scripts/publish-homebrew-tap.sh %s\n' "$TAP_DIR" "$OWNER" "$TAP_DIR"
