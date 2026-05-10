from __future__ import annotations

import sys
import tomllib
from importlib import metadata
from pathlib import Path

from .args import UnrecognizedCommandError, parse_args
from .assets_runtime import print_help
from .core import (
    cmd_compact,
    cmd_completion,
    cmd_detect,
    cmd_diff,
    cmd_doctor,
    cmd_explain,
    cmd_init,
    cmd_install_completion,
    cmd_license_init,
    cmd_license_list,
    cmd_license_search,
    cmd_license_view,
    cmd_list,
    cmd_search,
    cmd_selftest,
    cmd_stats,
    cmd_update_catalog,
    cmd_view,
    resolve_license_invocation,
    should_force_stdout_for_implicit_init,
)


def get_version() -> str:
    try:
        return metadata.version("gitig")
    except metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            project = tomllib.loads(pyproject_path.read_text("utf8")).get("project", {})
            version = project.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
    return "0.0.0"


def print_version() -> None:
    print(get_version())


def main() -> None:
    try:
        parsed = parse_args(sys.argv[1:])
        command = parsed.command
        if command == "list":
            cmd_list(parsed.source, parsed.no_cache)
            return
        if command == "search":
            cmd_search(" ".join(parsed.rest), parsed.source, parsed.no_cache)
            return
        if command == "view":
            cmd_view(" ".join(parsed.rest), parsed.source, parsed.no_cache, parsed.no_comments)
            return
        if command in ("init", "i", "I"):
            cmd_init(parsed.rest, parsed.source, parsed.output, parsed.output_explicit, parsed.force, parsed.append, parsed.no_cache, parsed.no_comments)
            return
        if command == "detect":
            cmd_detect(parsed.source, parsed.output, parsed.output_explicit, parsed.force, parsed.append, parsed.no_cache, parsed.detect_includes, parsed.no_comments)
            return
        if command == "compact":
            cmd_compact(parsed.rest[0] if parsed.rest else None, parsed.output, parsed.force)
            return
        if command in ("license", "li"):
            action, license_args = resolve_license_invocation(parsed.rest)
            if action == "list":
                cmd_license_list(parsed.no_cache)
                return
            if action == "search":
                cmd_license_search(" ".join(license_args), parsed.no_cache)
                return
            if action == "view":
                cmd_license_view(" ".join(license_args), parsed.no_cache)
                return
            cmd_license_init(
                " ".join(license_args),
                parsed.output if parsed.output_explicit else "LICENSE",
                parsed.output_explicit,
                parsed.force,
                parsed.append,
                parsed.no_cache,
                {
                    "year": parsed.year,
                    "fullname": parsed.fullname,
                    "project": parsed.project,
                    "project_url": parsed.project_url,
                },
            )
            return
        if command == "doctor":
            cmd_doctor(parsed.no_cache, json_output=parsed.json_output)
            return
        if command == "stats":
            cmd_stats(parsed.source, parsed.no_cache, json_output=parsed.json_output)
            return
        if command == "explain":
            cmd_explain(" ".join(parsed.rest), parsed.source, parsed.no_cache)
            return
        if command == "diff":
            if len(parsed.rest) < 2:
                raise ValueError("diff requires two templates")
            cmd_diff(parsed.rest[0], parsed.rest[1], parsed.source, parsed.no_cache, parsed.no_comments)
            return
        if command in ("check", "selftest"):
            cmd_selftest(parse_args)
            return
        if command == "completion":
            cmd_completion(parsed.rest[0] if parsed.rest else "")
            return
        if command == "install-completion":
            cmd_install_completion(parsed.rest[0] if parsed.rest else "")
            return
        if command in ("update", "update-catalog", "refresh-catalog"):
            cmd_update_catalog(parsed.rest[0] if parsed.rest else None, quiet=parsed.quiet, json_output=parsed.json_output)
            return
        if command == "version":
            print_version()
            return
        if command in ("help", "--help", "-h", None):
            print_help()
            return
        force_stdout = should_force_stdout_for_implicit_init(parsed.output_explicit, parsed.append)
        cmd_init([command, *parsed.rest], parsed.source, parsed.output, parsed.output_explicit, parsed.force, parsed.append, parsed.no_cache, parsed.no_comments, force_stdout=force_stdout)
    except (BrokenPipeError, KeyboardInterrupt):
        raise SystemExit(1)
    except UnrecognizedCommandError:
        print("Unrecognized command. Run `gitig help` for usage information.", file=sys.stderr)
        raise SystemExit(1)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
