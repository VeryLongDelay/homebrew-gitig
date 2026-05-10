#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


PLACEHOLDER_SHA = "REPLACE_ME"
SHA_PATTERN = re.compile(r'^\s*sha256\s+"([0-9a-f]{64}|REPLACE_ME)"\s*$')


def validate_formula_sha(path: Path) -> int:
    try:
        contents = path.read_text(encoding="utf8")
    except OSError as exc:
        print(f"Error: could not read {path}: {exc}", file=sys.stderr)
        return 1

    match = None
    for line in contents.splitlines():
        candidate = SHA_PATTERN.match(line)
        if candidate is not None:
            match = candidate
            break

    if match is None:
        print(f"Error: {path} is missing a valid sha256 line.", file=sys.stderr)
        return 1

    sha = match.group(1)
    if sha == PLACEHOLDER_SHA:
        print(
            f"Error: {path} still contains the placeholder sha256 {PLACEHOLDER_SHA}.",
            file=sys.stderr,
        )
        print("Run `make formula-sha` and update Formula/gitig.rb before committing.", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]) if args else Path("Formula/gitig.rb")
    return validate_formula_sha(target)


if __name__ == "__main__":
    raise SystemExit(main())
