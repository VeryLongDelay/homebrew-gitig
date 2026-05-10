from __future__ import annotations

from .models import Args, DetectInclude, SourceName


class UnrecognizedCommandError(ValueError):
    pass


SOURCE_ALIASES = {
    "gh": "github",
    "ghg": "github-global",
    "ghc": "github-community",
    "tt": "gitignoreio",
}

DETECT_INCLUDE_VALUES = ["os", "editor"]
SHELLS = ["bash", "zsh", "fish"]


def normalize_source_name(value: str) -> SourceName:
    normalized = value.strip().lower()
    if normalized == "all":
        return "all"
    if normalized in ("github", "github-global", "github-community", "gitignoreio"):
        return normalized  # type: ignore[return-value]
    if normalized in SOURCE_ALIASES:
        return SOURCE_ALIASES[normalized]  # type: ignore[return-value]
    raise ValueError("Invalid value for --source. Use github, gh, ghg, ghc, gitignoreio, tt, or all.")


def default_source_for_command(command: str | None) -> SourceName:
    if command in ("list", "search", "stats"):
        return "all"
    if command in ("view", "init", "I", "i", "detect"):
        return "github"
    return "all"


def parse_detect_includes(value: str) -> list[DetectInclude]:
    parts = [part.strip().lower() for part in value.split(",") if part.strip()]
    invalid = [part for part in parts if part not in DETECT_INCLUDE_VALUES]
    if invalid:
        raise ValueError(f"Invalid value for --include: {', '.join(invalid)}")
    return list(dict.fromkeys(parts))  # type: ignore[return-value]


def parse_args(argv: list[str]) -> Args:
    args = list(argv)
    output = ".gitignore"
    output_explicit = False
    force = False
    append = False
    year = None
    fullname = None
    project = None
    project_url = None
    source: SourceName | None = None
    no_cache = False
    no_comments = False
    quiet = False
    json_output = False
    no_color = False
    detect_includes: list[DetectInclude] = []
    filtered: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "-c" and not filtered:
            filtered.append("compact")
            i += 1
            continue

        if arg in ("-v", "--version", "--verison") and not filtered:
            filtered.append("version")
            i += 1
            continue

        if arg == "li" and not filtered:
            filtered.extend(["license", "init"])
            i += 1
            continue

        if arg == "-li" and not filtered:
            filtered.extend(["license", "init"])
            i += 1
            continue

        if arg in ("--output", "-o"):
            i += 1
            if i >= len(args) or not args[i]:
                raise ValueError("Missing value for --output")
            output = args[i]
            output_explicit = True
            i += 1
            continue

        if arg in ("--force", "-f"):
            force = True
            i += 1
            continue

        if arg in ("--fullname", "--author", "--owner"):
            i += 1
            if i >= len(args) or not args[i].strip():
                raise ValueError(f"Missing value for {arg}")
            fullname = args[i].strip()
            i += 1
            continue

        if arg == "--project":
            i += 1
            if i >= len(args) or not args[i].strip():
                raise ValueError("Missing value for --project")
            project = args[i].strip()
            i += 1
            continue

        if arg in ("--projecturl", "--project-url"):
            i += 1
            if i >= len(args) or not args[i].strip():
                raise ValueError(f"Missing value for {arg}")
            project_url = args[i].strip()
            i += 1
            continue

        if arg == "--year":
            i += 1
            if i >= len(args) or not args[i].strip():
                raise ValueError("Missing value for --year")
            year = args[i].strip()
            i += 1
            continue

        if arg in ("--append", "-a"):
            append = True
            i += 1
            continue

        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 2:
            cluster = arg[1:]
            if all(ch in "afnc" for ch in cluster):
                if "a" in cluster:
                    append = True
                if "f" in cluster:
                    force = True
                if "n" in cluster:
                    no_comments = True
                i += 1
                continue
            raise UnrecognizedCommandError("unrecognized command")

        if arg in ("--source", "-s"):
            i += 1
            if i >= len(args) or not args[i]:
                raise ValueError("Missing value for --source")
            source = normalize_source_name(args[i])
            i += 1
            continue

        if arg == "--include":
            i += 1
            if i >= len(args) or not args[i]:
                raise ValueError("Missing value for --include")
            detect_includes = parse_detect_includes(args[i])
            i += 1
            continue

        if arg == "--no-cache":
            no_cache = True
            i += 1
            continue

        if arg in ("--no-comments", "--no-comment", "-nc", "-n"):
            no_comments = True
            i += 1
            continue

        if arg == "--quiet":
            quiet = True
            i += 1
            continue

        if arg == "--json":
            json_output = True
            i += 1
            continue

        if arg in ("--no-color", "--no-colour"):
            no_color = True
            i += 1
            continue

        if arg.startswith("-"):
            raise UnrecognizedCommandError("unrecognized command")

        filtered.append(arg)
        i += 1

    command = filtered[0] if filtered else None
    rest = filtered[1:]
    return Args(
        command=command,
        rest=rest,
        output=output,
        output_explicit=output_explicit,
        force=force,
        append=append,
        year=year,
        fullname=fullname,
        project=project,
        project_url=project_url,
        source=source or default_source_for_command(command),
        no_cache=no_cache,
        no_comments=no_comments,
        quiet=quiet,
        json_output=json_output,
        detect_includes=detect_includes,
        no_color=no_color,
    )
