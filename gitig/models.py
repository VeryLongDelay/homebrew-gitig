from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


Provider = Literal["github", "gitignoreio"]
SourceName = Literal["github", "github-global", "github-community", "gitignoreio", "all"]
DetectInclude = Literal["os", "editor"]
GitHubScope = Literal["all", "root", "global", "community"]


@dataclass
class Args:
    command: str | None
    rest: list[str]
    output: str
    output_explicit: bool
    force: bool
    append: bool
    year: str | None
    fullname: str | None
    project: str | None
    project_url: str | None
    source: SourceName
    no_cache: bool
    no_comments: bool
    quiet: bool
    json_output: bool
    detect_includes: list[DetectInclude]
    no_color: bool


@dataclass
class CatalogEntry:
    source: Provider
    name: str
    key: str
    display_name: str
    aliases: list[str]
    github_scope: GitHubScope | None = None


@dataclass
class CacheStatus:
    exists: bool
    fresh: bool
    age_ms: int | None
    ttl_ms: int
    path: str


@dataclass
class CatalogLoadResult:
    catalog: list[CatalogEntry]
    cache: CacheStatus


@dataclass
class LicenseCatalogEntry:
    key: str
    path: str
    title: str
    spdx_id: str | None
    hidden: bool
    aliases: list[str]


@dataclass
class LicenseTemplate:
    metadata: LicenseCatalogEntry
    body: str


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class StatsRow:
    label: str
    count: int


@dataclass
class SelfTestCase:
    name: str
    run: Callable[[], None]


def catalog_entry_from_cache(entry: dict[str, Any]) -> CatalogEntry:
    return CatalogEntry(
        source=entry["source"],
        name=entry["name"],
        key=entry["key"],
        display_name=entry.get("display_name", entry.get("displayName", entry["name"])),
        aliases=list(entry.get("aliases", [])),
        github_scope=entry.get("github_scope", entry.get("githubScope")),
    )


def license_catalog_entry_from_cache(entry: dict[str, Any]) -> LicenseCatalogEntry:
    return LicenseCatalogEntry(
        key=entry["key"],
        path=entry["path"],
        title=entry["title"],
        spdx_id=entry.get("spdx_id", entry.get("spdxId")),
        hidden=bool(entry.get("hidden", False)),
        aliases=list(entry.get("aliases", [])),
    )
