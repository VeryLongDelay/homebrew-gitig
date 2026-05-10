#!/usr/bin/env bash
set -euo pipefail

# Compute the GitHub archive tarball sha256 for a tag and update Formula/gitig.rb
# (url + sha256 lines). Intended to be run before committing a formula bump.
#
# Usage:
#   ./scripts/write-gitig-formula-sha.sh v0.1.0
#
# Env: same as scripts/formula-archive-sha256.sh (FORMULA_REPO_OWNER, FORMULA_REPO)

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
formula="${root}/Formula/gitig.rb"

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "usage: $0 <tag>" >&2
  echo "  example: $0 v0.1.0" >&2
  exit 1
fi

owner="${FORMULA_REPO_OWNER:-verylongdelay}"
repo="${FORMULA_REPO:-gitig}"
if [[ "${tag}" != v* ]]; then
  tag="v${tag}"
fi

url="https://github.com/${owner}/${repo}/archive/refs/tags/${tag}.tar.gz"
sha="$("${root}/scripts/formula-archive-sha256.sh" "${tag}")"

if [[ ! -f "${formula}" ]]; then
  echo "formula not found: ${formula}" >&2
  exit 1
fi

tmp="$(mktemp)"
sed \
  -e "s|^  url \".*\"|  url \"${url}\"|" \
  -e "s|^  sha256 \".*\"|  sha256 \"${sha}\"|" \
  "${formula}" >"${tmp}"
mv "${tmp}" "${formula}"

echo "Updated ${formula}"
echo "  url     ${url}"
echo "  sha256  ${sha}"
