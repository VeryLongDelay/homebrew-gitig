#!/usr/bin/env bash
set -euo pipefail

# Print sha256 for the GitHub "archive refs/tags/<tag>.tar.gz" tarball used by
# Formula/gitig.rb. Does not persist anything.
#
# Usage:
#   ./scripts/formula-archive-sha256.sh v0.1.0
#   FORMULA_REPO_OWNER=you FORMULA_REPO=gitig ./scripts/formula-archive-sha256.sh v0.1.0
#
# Env:
#   FORMULA_REPO_OWNER  default: verylongdelay
#   FORMULA_REPO       default: gitig

owner="${FORMULA_REPO_OWNER:-verylongdelay}"
repo="${FORMULA_REPO:-gitig}"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "usage: $0 <tag>" >&2
  echo "  example: $0 v0.1.0" >&2
  exit 1
fi

if [[ "${tag}" != v* ]]; then
  tag="v${tag}"
fi

url="https://github.com/${owner}/${repo}/archive/refs/tags/${tag}.tar.gz"

hash_stream_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{ print $1 }'
  else
    shasum -a 256 | awk '{ print $1 }'
  fi
}

sha="$(curl -fsSL "${url}" | hash_stream_sha256)"
printf '%s\n' "${sha}"
