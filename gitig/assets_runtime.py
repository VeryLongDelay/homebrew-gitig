from __future__ import annotations

from importlib import resources


def read_asset(*parts: str) -> str:
    return resources.files("gitig.assets").joinpath(*parts).read_text("utf8")


def print_help() -> None:
    print(read_asset("help.txt").strip())


def get_completion_text(shell_name: str) -> str:
    return read_asset("completions", f"{shell_name}.txt")
