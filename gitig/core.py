from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from difflib import unified_diff
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .args import SHELLS
from .assets_runtime import get_completion_text
from .models import (
    CacheStatus,
    CatalogEntry,
    CatalogLoadResult,
    DetectInclude,
    DoctorCheck,
    GitHubScope,
    LicenseCatalogEntry,
    LicenseTemplate,
    Provider,
    SelfTestCase,
    SourceName,
    StatsRow,
    catalog_entry_from_cache,
    license_catalog_entry_from_cache,
)
from .spinner import Spinner

GITHUB_API_BASE = "https://api.github.com"
GITHUB_REPO = "github/gitignore"
GITHUB_BRANCH = "main"
GITHUB_TREE_URL = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITIGNORE_IO_BASE = "https://www.toptal.com/developers/gitignore/api"
LICENSE_REPO = "github/choosealicense.com"
LICENSE_BRANCH = "gh-pages"
LICENSE_TREE_URL = f"{GITHUB_API_BASE}/repos/{LICENSE_REPO}/git/trees/{LICENSE_BRANCH}?recursive=1"
LICENSE_RAW_BASE = f"https://raw.githubusercontent.com/{LICENSE_REPO}/{LICENSE_BRANCH}"

CACHE_DIR = Path.home() / ".cache" / "gitig"
DEFAULT_CACHE_TTL_MS = 1000 * 60 * 60 * 24
FETCH_TIMEOUT_SECONDS = 15


def normalize_text(value: str) -> str:
    return value.strip().replace("\\", "/")


def normalize_loose(value: str) -> str:
    return (
        normalize_text(value)
        .removesuffix(".gitignore")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
        .replace(":", "")
        .lower()
    )


def unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values), key=lambda v: v.lower())


def assert_single_source(source: SourceName, command: str) -> SourceName:
    if source == "all":
        raise ValueError(f"{command} requires --source github/gh/ghg/ghc or gitignoreio/tt")
    return source


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def path_exists(path: str | Path) -> bool:
    return Path(path).exists()


def get_cache_ttl_ms(env_name: str, default_ms: int = DEFAULT_CACHE_TTL_MS) -> int:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default_ms
    try:
        seconds = int(raw.strip())
    except ValueError:
        return default_ms
    return max(0, seconds * 1000)


def github_catalog_cache_ttl_ms() -> int:
    return get_cache_ttl_ms("GITIG_GITHUB_CATALOG_CACHE_TTL_SECONDS")


def gitignoreio_catalog_cache_ttl_ms() -> int:
    return get_cache_ttl_ms("GITIG_GITIGNOREIO_CATALOG_CACHE_TTL_SECONDS")


def license_catalog_cache_ttl_ms() -> int:
    return get_cache_ttl_ms("GITIG_LICENSE_CATALOG_CACHE_TTL_SECONDS")


def maybe_start_background_refresh(name: str, loader: Callable[[], Any]) -> None:
    if os.getenv("GITIG_DISABLE_BACKGROUND_REFRESH"):
        return

    def _run() -> None:
        try:
            loader()
        except Exception:
            return

    thread = threading.Thread(target=_run, name=f"gitig-refresh-{name}", daemon=True)
    thread.start()


def load_with_cache_refresh(
    cache_name: str,
    ttl_ms: int,
    no_cache: bool,
    refresh_fn: Callable[[bool, bool | None], Any],
    from_cache: Callable[[Any], Any],
    no_color: bool | None = None,
) -> tuple[Any, CacheStatus]:
    cache_path = cache_path_for(cache_name)
    cache = get_cache_status(cache_path, ttl_ms)
    if not no_cache:
        try:
            cached = json.loads(cache_path.read_text("utf8")) if cache.exists else None
        except Exception:
            cached = None
        if cached is not None:
            value = from_cache(cached)
            if not cache.fresh:
                maybe_start_background_refresh(cache_name, lambda: refresh_fn(False, no_color))
            return value, cache
    value = refresh_fn(True, no_color)
    return value, get_cache_status(cache_path, ttl_ms)


def write_cache_payload(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(CACHE_DIR)
    wrapped = {
        "meta": {
            "etag": payload.get("etag"),
            "last_modified": payload.get("last_modified"),
            "fetched_at": int(time.time() * 1000),
        },
        "catalog": payload.get("catalog", []),
    }
    path.write_text(json.dumps(wrapped, indent=2), "utf8")


def read_cache_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text("utf8"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    if "meta" in value and "catalog" in value:
        meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
        return {
            "etag": meta.get("etag"),
            "last_modified": meta.get("last_modified"),
            "catalog": value.get("catalog", []),
        }
    if "catalog" in value:
        return {
            "etag": value.get("etag"),
            "last_modified": value.get("last_modified"),
            "catalog": value.get("catalog", []),
        }
    return None


def fetch_bytes(
    url: str,
    accept_json: bool = False,
    status: str | None = None,
    spinner_enabled: bool = True,
    no_color: bool | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    headers = {"User-Agent": "gitig-python"}
    if accept_json:
        headers["Accept"] = "application/vnd.github+json"
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)
    try:
        with Spinner(status or f"Fetching {url}", enabled=None if spinner_enabled else False, no_color=no_color), urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, response.read(), response_headers
    except HTTPError as exc:
        if exc.code == 304:
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
            return 304, b"", response_headers
        raise RuntimeError(f"Request failed: {exc.code} {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc


def fetch_json(
    url: str,
    status: str | None = None,
    spinner_enabled: bool = True,
    no_color: bool | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    _, body, _ = fetch_bytes(
        url,
        accept_json=True,
        status=status,
        spinner_enabled=spinner_enabled,
        no_color=no_color,
        extra_headers=extra_headers,
    )
    return json.loads(body.decode("utf8"))


def fetch_text(
    url: str,
    status: str | None = None,
    spinner_enabled: bool = True,
    no_color: bool | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str:
    _, body, _ = fetch_bytes(
        url,
        status=status,
        spinner_enabled=spinner_enabled,
        no_color=no_color,
        extra_headers=extra_headers,
    )
    return body.decode("utf8")


def cache_path_for(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def get_cache_status(path: Path, ttl_ms: int = DEFAULT_CACHE_TTL_MS) -> CacheStatus:
    if not path.exists():
        return CacheStatus(False, False, None, ttl_ms, str(path))
    age_ms = int(time.time() * 1000 - path.stat().st_mtime * 1000)
    return CacheStatus(True, age_ms <= ttl_ms, age_ms, ttl_ms, str(path))


def touch_cache_path(path: Path) -> None:
    now = time.time()
    os.utime(path, (now, now))


def refresh_github_catalog(spinner_enabled: bool = True, no_color: bool | None = None) -> CatalogLoadResult:
    cache_path = cache_path_for("github-catalog")
    ttl_ms = github_catalog_cache_ttl_ms()
    cached = read_cache_payload(cache_path)
    extra_headers: dict[str, str] = {}
    if cached:
        etag = cached.get("etag")
        last_modified = cached.get("last_modified")
        if etag:
            extra_headers["If-None-Match"] = str(etag)
        if last_modified:
            extra_headers["If-Modified-Since"] = str(last_modified)
    status_code, body, headers = fetch_bytes(
        GITHUB_TREE_URL,
        accept_json=True,
        status="Refreshing GitHub template catalog",
        spinner_enabled=spinner_enabled,
        no_color=no_color,
        extra_headers=extra_headers or None,
    )
    if status_code == 304 and cached is not None:
        touch_cache_path(cache_path)
        catalog = [catalog_entry_from_cache(entry) for entry in cached.get("catalog", [])]
        return CatalogLoadResult(catalog, get_cache_status(cache_path, ttl_ms))
    tree = json.loads(body.decode("utf8"))
    catalog: list[CatalogEntry] = []
    for item in tree["tree"]:
        if item.get("type") != "blob":
            continue
        entry = classify_github_template(item["path"])
        if entry is not None:
            catalog.append(entry)
    catalog.sort(key=lambda item: item.display_name.lower())
    write_cache_payload(
        cache_path,
        {
            "etag": headers.get("etag") or tree.get("sha"),
            "last_modified": headers.get("last-modified"),
            "catalog": [asdict(entry) for entry in catalog],
        },
    )
    return CatalogLoadResult(catalog, get_cache_status(cache_path, ttl_ms))


def refresh_gitignoreio_catalog(spinner_enabled: bool = True, no_color: bool | None = None) -> CatalogLoadResult:
    cache_path = cache_path_for("gitignoreio-catalog")
    ttl_ms = gitignoreio_catalog_cache_ttl_ms()
    text = fetch_text(
        f"{GITIGNORE_IO_BASE}/list",
        "Refreshing gitignore.io template catalog",
        spinner_enabled=spinner_enabled,
        no_color=no_color,
    )
    keys = [part.strip() for part in text.replace("\n", ",").split(",") if part.strip()]
    catalog = [
        CatalogEntry("gitignoreio", key, key, key, unique_sorted([key, f"tt:{key}", f"gitignoreio:{key}"]))
        for key in unique_sorted(keys)
    ]
    write_cache_payload(cache_path, {"etag": None, "catalog": [asdict(entry) for entry in catalog]})
    return CatalogLoadResult(catalog, get_cache_status(cache_path, ttl_ms))


def refresh_license_catalog(spinner_enabled: bool = True, no_color: bool | None = None) -> list[LicenseCatalogEntry]:
    cache_path = cache_path_for("license-catalog")
    cached = read_cache_payload(cache_path)
    extra_headers: dict[str, str] = {}
    if cached:
        etag = cached.get("etag")
        last_modified = cached.get("last_modified")
        if etag:
            extra_headers["If-None-Match"] = str(etag)
        if last_modified:
            extra_headers["If-Modified-Since"] = str(last_modified)
    status_code, body, headers = fetch_bytes(
        LICENSE_TREE_URL,
        accept_json=True,
        status="Refreshing license catalog",
        spinner_enabled=spinner_enabled,
        no_color=no_color,
        extra_headers=extra_headers or None,
    )
    if status_code == 304 and cached is not None:
        touch_cache_path(cache_path)
        catalog = [license_catalog_entry_from_cache(entry) for entry in cached.get("catalog", [])]
        return [entry for entry in catalog if not entry.hidden]
    tree = json.loads(body.decode("utf8"))
    paths = sorted(
        item["path"]
        for item in tree["tree"]
        if item.get("type") == "blob" and item["path"].startswith("_licenses/") and item["path"].endswith(".txt")
    )
    catalog = [
        build_license_catalog_entry(
            path,
            fetch_text(
                f"{LICENSE_RAW_BASE}/{path}",
                f"Refreshing license metadata {path.removeprefix('_licenses/').removesuffix('.txt')}",
                spinner_enabled=spinner_enabled,
                no_color=no_color,
            ),
        )
        for path in paths
    ]
    write_cache_payload(
        cache_path,
        {
            "etag": headers.get("etag") or tree.get("sha"),
            "last_modified": headers.get("last-modified"),
            "catalog": [asdict(entry) for entry in catalog],
        },
    )
    return [entry for entry in catalog if not entry.hidden]


def _normalize_update_target(target: str | None) -> str:
    normalized = (target or "all").strip().lower()
    alias_map = {
        "": "all",
        "gh": "github",
        "ghg": "github-global",
        "ghc": "github-community",
        "tt": "gitignoreio",
        "licenses": "license",
    }
    normalized = alias_map.get(normalized, normalized)
    valid = {"all", "github", "github-global", "github-community", "gitignoreio", "license"}
    if normalized not in valid:
        raise ValueError("update requires one of: all, github, github-global, github-community, gitignoreio, license")
    return normalized


def _build_update_result(name: str, count: int, cache_path: Path) -> dict[str, Any]:
    return {"target": name, "count": count, "cache_path": str(cache_path), "status": "updated"}


def cmd_update_catalog(target: str | None = None, quiet: bool = False, json_output: bool = False) -> None:
    normalized = _normalize_update_target(target)
    spinner_enabled = not json_output
    github_refresh_result: CatalogLoadResult | None = None
    github_refresh_lock = threading.Lock()

    def get_refreshed_github() -> CatalogLoadResult:
        nonlocal github_refresh_result
        with github_refresh_lock:
            if github_refresh_result is None:
                github_refresh_result = refresh_github_catalog(spinner_enabled=False)
            return github_refresh_result

    def refresh_target(name: str) -> dict[str, Any]:
        if name == "github":
            github = get_refreshed_github()
            return _build_update_result("github", len(github.catalog), cache_path_for("github-catalog"))
        if name == "github-global":
            github = get_refreshed_github()
            return _build_update_result("github-global", len([entry for entry in github.catalog if entry.github_scope == "global"]), cache_path_for("github-catalog"))
        if name == "github-community":
            github = get_refreshed_github()
            return _build_update_result("github-community", len([entry for entry in github.catalog if entry.github_scope == "community"]), cache_path_for("github-catalog"))
        if name == "gitignoreio":
            gitignoreio = refresh_gitignoreio_catalog(spinner_enabled=False)
            return _build_update_result("gitignoreio", len(gitignoreio.catalog), cache_path_for("gitignoreio-catalog"))
        licenses = refresh_license_catalog(spinner_enabled=False)
        return _build_update_result("license", len(licenses), cache_path_for("license-catalog"))

    targets = [normalized] if normalized != "all" else ["github", "gitignoreio", "license"]
    start_time = time.time()
    results: list[dict[str, Any]] = []

    with Spinner("Updating catalogs", enabled=None if spinner_enabled else False):
        if len(targets) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as executor:
                future_map = {executor.submit(refresh_target, name): name for name in targets}
                for future in concurrent.futures.as_completed(future_map):
                    results.append(future.result())
        else:
            results.append(refresh_target(targets[0]))

    order = {name: index for index, name in enumerate(targets)}
    results.sort(key=lambda item: order.get(item["target"], 999))
    payload = {
        "target": normalized,
        "updated": results,
        "duration_ms": int((time.time() - start_time) * 1000),
        "parallel": len(targets) > 1,
    }

    if json_output:
        print(json.dumps(payload, indent=2))
        return
    if quiet:
        return
    for item in results:
        print(f"Updated {item['target']} catalog ({item['count']} entries)")


def format_age_ms(age_ms: int | None) -> str:
    if age_ms is None:
        return "missing"
    total_seconds = max(0, age_ms // 1000)
    minutes = total_seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days > 0:
        return f"{days}d {hours % 24}h"
    if hours > 0:
        return f"{hours}h {minutes % 60}m"
    if minutes > 0:
        return f"{minutes}m {total_seconds % 60}s"
    return f"{total_seconds}s"


def format_cache_status(status: CacheStatus, no_cache: bool) -> str:
    if no_cache:
        return f"bypassed ({status.path})"
    if not status.exists:
        return f"miss; file missing ({status.path})"
    if not status.fresh:
        return f"stale; age={format_age_ms(status.age_ms)} ttl={format_age_ms(status.ttl_ms)} ({status.path})"
    return f"hit; age={format_age_ms(status.age_ms)} ttl={format_age_ms(status.ttl_ms)} ({status.path})"


def classify_github_template(path: str) -> CatalogEntry | None:
    if not path.endswith(".gitignore"):
        return None
    if path.startswith("Global/"):
        relative = path[len("Global/") : -len(".gitignore")]
        full = path[:-len(".gitignore")]
        return CatalogEntry("github", full, path, full, unique_sorted([full, relative, f"{relative}.gitignore", f"Global/{relative}", f"ghg:{relative}", f"github-global:{relative}"]), "global")
    if path.startswith("community/"):
        relative = path[len("community/") : -len(".gitignore")]
        full = path[:-len(".gitignore")]
        return CatalogEntry("github", full, path, full, unique_sorted([full, relative, f"{relative}.gitignore", f"community/{relative}", f"ghc:{relative}", f"github-community:{relative}"]), "community")
    if "/" in path:
        return None
    name = path[:-len(".gitignore")]
    return CatalogEntry("github", name, path, name, unique_sorted([name, f"{name}.gitignore", f"gh:{name}", f"github:{name}"]), "root")


def source_to_github_scope(source: SourceName) -> GitHubScope | None:
    if source == "github":
        return "all"
    if source == "github-global":
        return "global"
    if source == "github-community":
        return "community"
    return None


def filter_github_catalog_by_scope(catalog: list[CatalogEntry], scope: GitHubScope) -> list[CatalogEntry]:
    if scope == "all":
        return catalog
    return [entry for entry in catalog if entry.github_scope == scope]


def get_github_catalog_with_cache(no_cache: bool, no_color: bool | None = None) -> CatalogLoadResult:
    ttl_ms = github_catalog_cache_ttl_ms()

    def from_cache(payload: Any) -> list[CatalogEntry]:
        catalog = payload.get("catalog", payload)
        return [catalog_entry_from_cache(entry) for entry in catalog]

    catalog, cache = load_with_cache_refresh("github-catalog", ttl_ms, no_cache, refresh_github_catalog, from_cache, no_color)
    return CatalogLoadResult(catalog, cache)


def get_gitignoreio_catalog_with_cache(no_cache: bool, no_color: bool | None = None) -> CatalogLoadResult:
    ttl_ms = gitignoreio_catalog_cache_ttl_ms()

    def from_cache(payload: Any) -> list[CatalogEntry]:
        catalog = payload.get("catalog", payload)
        return [catalog_entry_from_cache(entry) for entry in catalog]

    catalog, cache = load_with_cache_refresh("gitignoreio-catalog", ttl_ms, no_cache, refresh_gitignoreio_catalog, from_cache, no_color)
    return CatalogLoadResult(catalog, cache)


def get_catalog(source: SourceName, no_cache: bool) -> list[CatalogEntry]:
    if source in ("github", "github-global", "github-community"):
        catalog = get_github_catalog_with_cache(no_cache).catalog
        scope = source_to_github_scope(source)
        return catalog if scope is None else filter_github_catalog_by_scope(catalog, scope)
    if source == "gitignoreio":
        return get_gitignoreio_catalog_with_cache(no_cache).catalog
    github = get_github_catalog_with_cache(no_cache).catalog
    gitignoreio = get_gitignoreio_catalog_with_cache(no_cache).catalog
    return sorted(github + gitignoreio, key=lambda entry: (entry.display_name.lower(), entry.source))


def parse_provider_prefix(value: str) -> tuple[Provider | None, GitHubScope | None, str]:
    trimmed = normalize_text(value)
    if ":" not in trimmed:
        return None, None, trimmed
    raw_provider, raw_name = trimmed.split(":", 1)
    provider = raw_provider.lower()
    name = raw_name.strip()
    if provider in ("github", "gh"):
        return "github", "all", name
    if provider in ("ghg", "github-global"):
        return "github", "global", name
    if provider in ("ghc", "github-community"):
        return "github", "community", name
    if provider in ("gitignoreio", "tt"):
        return "gitignoreio", None, name
    return None, None, trimmed


def normalize_scoped_github_name(name: str, scope: GitHubScope) -> str:
    normalized = normalize_text(name)
    if normalized.lower().endswith(".gitignore"):
        normalized = normalized[: -len(".gitignore")]
    if scope == "global":
        return normalized if normalized.startswith("Global/") else f"Global/{normalized}"
    if scope == "community":
        return normalized if normalized.startswith("community/") else f"community/{normalized}"
    return normalized


def resolve_entry(name: str, catalog: list[CatalogEntry]) -> CatalogEntry | None:
    provider, scope, raw_name = parse_provider_prefix(name)
    scoped = catalog
    if provider is not None:
        scoped = [entry for entry in scoped if entry.source == provider]
    if provider == "github" and scope is not None:
        scoped = filter_github_catalog_by_scope(scoped, scope)
    raw = normalize_text(raw_name)
    loose = normalize_loose(raw_name)
    candidates = [raw]
    if provider == "github" and scope is not None:
        candidates.append(normalize_scoped_github_name(raw_name, scope))
    for candidate in candidates:
        for entry in scoped:
            if entry.display_name == candidate:
                return entry
    lower_candidates = [candidate.lower() for candidate in candidates]
    for entry in scoped:
        if entry.display_name.lower() in lower_candidates:
            return entry
    for entry in scoped:
        if any(alias.lower() == raw.lower() for alias in entry.aliases):
            return entry
    for entry in scoped:
        if normalize_loose(entry.display_name) == loose or any(normalize_loose(alias) == loose for alias in entry.aliases):
            return entry
    return None


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for i, char_b in enumerate(b, start=1):
        current = [i]
        for j, char_a in enumerate(a, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def shortlist_suggestion_candidates(query: str, values: list[str], limit: int = 64) -> list[str]:
    q = normalize_loose(query)
    ranked: list[tuple[tuple[int, int, int, str], str]] = []
    for value in values:
        normalized = normalize_loose(value)
        contains = 0 if q and (q in normalized or normalized in q) else 1
        prefix = 0 if q and normalized.startswith(q[: min(len(q), 3)]) else 1
        length_gap = abs(len(normalized) - len(q))
        ranked.append(((contains, prefix, length_gap, normalized), value))
    ranked.sort(key=lambda item: item[0])
    return [value for _, value in ranked[:limit]]


def fuzzy_match_score(query: str, candidate: str) -> int:
    q = normalize_loose(query)
    c = normalize_loose(candidate)
    if not q or not c:
        return max(len(q), len(c))
    contains_bonus = 0 if (q in c or c in q) else 3
    prefix_bonus = 0 if c.startswith(q[: min(len(q), 3)]) else 2
    length_gap = abs(len(c) - len(q)) // 2
    return levenshtein(q, c) + contains_bonus + prefix_bonus + length_gap


def format_suggestions(query: str, catalog: list[CatalogEntry]) -> str:
    shortlisted = set(shortlist_suggestion_candidates(query, [entry.display_name for entry in catalog]))
    ranked: list[tuple[int, CatalogEntry]] = []
    for entry in catalog:
        if shortlisted and entry.display_name not in shortlisted:
            continue
        score = min(fuzzy_match_score(query, candidate) for candidate in [entry.display_name, *entry.aliases])
        ranked.append((score, entry))
    ranked.sort(key=lambda item: (item[0], item[1].display_name.lower()))
    suggestions = [item[1] for item in ranked[:5]]
    if not suggestions:
        return ""
    lines = []
    for entry in suggestions:
        prefix = "tt" if entry.source == "gitignoreio" else "ghg" if entry.github_scope == "global" else "ghc" if entry.github_scope == "community" else "gh"
        suggested = entry.display_name
        if entry.github_scope == "global":
            suggested = suggested.removeprefix("Global/")
        elif entry.github_scope == "community":
            suggested = suggested.removeprefix("community/")
        lines.append(f"  - {prefix}:{suggested}")
    return "Did you mean:\n" + "\n".join(lines)


def get_github_template_content(path: str) -> str:
    return fetch_text(f"{GITHUB_RAW_BASE}/{path}", f"Fetching GitHub template {path.removesuffix('.gitignore')}")


def get_gitignoreio_template_content(keys: list[str]) -> str:
    joined = ",".join(key.strip() for key in keys if key.strip())
    if not joined:
        raise ValueError("Please provide at least one gitignore.io template")
    return fetch_text(f"{GITIGNORE_IO_BASE}/{quote(joined)}", f"Fetching gitignore.io template {joined}")


def is_comment_line(trimmed: str) -> bool:
    return trimmed.startswith("#") and not trimmed.startswith("\\#")


def compact_ignore_content(content: str) -> str:
    kept: list[str] = []
    previous_blank = False
    for line in content.replace("\r\n", "\n").split("\n"):
        trimmed = line.strip()
        if not trimmed:
            if not previous_blank and kept:
                kept.append("")
                previous_blank = True
            continue
        if is_comment_line(trimmed):
            continue
        kept.append(line)
        previous_blank = False
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept) + ("\n" if kept else "")


def apply_no_comments(content: str, no_comments: bool) -> str:
    return compact_ignore_content(content) if no_comments else content


def dedupe_lines(content: str) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for line in content.replace("\r\n", "\n").split("\n"):
        if line in seen:
            continue
        seen.add(line)
        output.append(line)
    return "\n".join(output).rstrip("\n") + "\n"


def merge_appended_content(existing: str, content: str) -> str:
    separator = "" if existing.endswith("\n") or not existing or not content else "\n"
    return dedupe_lines(existing + separator + content)


def parse_template_args(parts: list[str]) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        tokens.extend(token.strip() for token in part.split(","))
    tokens = [token for token in tokens if token]
    expanded: list[str] = []
    sticky_prefix = ""
    for token in tokens:
        normalized = normalize_text(token)
        if normalized.endswith(":"):
            sticky_prefix = normalized
            continue
        provider, _, _ = parse_provider_prefix(normalized)
        if provider is not None:
            expanded.append(normalized)
            sticky_prefix = normalized[: normalized.index(":") + 1]
            continue
        expanded.append(f"{sticky_prefix}{normalized}" if sticky_prefix else normalized)
    return expanded


def expand_preset_bundles(raw_names: list[str]) -> list[str]:
    bundles = {"python": ["gh:Python"], "node": ["gh:Node"], "rust": ["gh:Rust"], "go": ["gh:Go"]}
    expanded: list[str] = []
    for name in raw_names:
        key = normalize_loose(name)
        expanded.extend(bundles.get(key, [name]))
    return expanded


def build_init_content(raw_names: list[str], source: SourceName, no_cache: bool, no_comments: bool) -> str:
    requested_names = parse_template_args(expand_preset_bundles(raw_names))
    if not requested_names:
        raise ValueError("Please provide at least one template name")
    effective_sources: list[SourceName] = []
    for requested_name in requested_names:
        provider, scope, _ = parse_provider_prefix(requested_name)
        if provider is None:
            effective_sources.append(assert_single_source(source, "init"))
        elif provider == "gitignoreio":
            effective_sources.append("gitignoreio")
        elif scope == "global":
            effective_sources.append("github-global")
        elif scope == "community":
            effective_sources.append("github-community")
        else:
            effective_sources.append("github")
    effective_sources = unique_sorted(effective_sources)  # type: ignore[assignment]
    has_github = any(item.startswith("github") for item in effective_sources)
    has_gitignoreio = "gitignoreio" in effective_sources
    if has_github and has_gitignoreio:
        raise ValueError("init cannot mix GitHub templates and gitignore.io templates in one command")
    catalog = get_catalog(effective_sources[0], no_cache)
    resolved: list[CatalogEntry] = []
    for requested_name in requested_names:
        entry = resolve_entry(requested_name, catalog)
        if entry is None:
            print(f"Template not found: {requested_name}", file=sys.stderr)
            suggestions = format_suggestions(requested_name, catalog)
            if suggestions:
                print(suggestions, file=sys.stderr)
            raise SystemExit(1)
        resolved.append(entry)
    if resolved and resolved[0].source == "github":
        parts: list[str] = []
        for entry in resolved:
            section = get_github_template_content(entry.key)
            cleaned = apply_no_comments(section, no_comments).rstrip("\n")
            if not cleaned:
                continue
            parts.append(cleaned if no_comments else f"# --- {entry.display_name} ---\n{cleaned}")
        return "\n\n".join(parts) + ("\n" if parts else "")
    generated = get_gitignoreio_template_content([entry.key for entry in resolved])
    return apply_no_comments(dedupe_lines(generated), no_comments)


def write_generated_content(output: str, content: str, force: bool, append: bool) -> None:
    path = Path(output)
    if append:
        if not path.exists():
            path.write_text(content, "utf8")
            return
        path.write_text(merge_appended_content(path.read_text("utf8"), content), "utf8")
        return
    if path.exists() and not force:
        print(f"{output} already exists. Use --force to overwrite.", file=sys.stderr)
        raise SystemExit(1)
    path.write_text(content, "utf8")


def display_name_for_source(entry: CatalogEntry, source: SourceName) -> str:
    if source == "github-global":
        return entry.display_name.removeprefix("Global/")
    if source == "github-community":
        return entry.display_name.removeprefix("community/")
    return entry.display_name


def get_detected_extras(provider: Provider, includes: list[DetectInclude]) -> list[str]:
    values: set[str] = set()
    system = sys.platform
    if "os" in includes:
        if provider == "github":
            values.add("Global/macOS" if system == "darwin" else "Global/Windows" if system.startswith("win") else "Global/Linux")
        else:
            values.add("macos" if system == "darwin" else "windows" if system.startswith("win") else "linux")
    if "editor" in includes:
        has_vscode = path_exists(".vscode") or path_exists(".vscode/settings.json")
        has_idea = path_exists(".idea")
        has_vs = path_exists(".vs")
        if provider == "github":
            values.add("Global/JetBrains" if has_idea else "Global/VisualStudio" if has_vs else "Global/VisualStudioCode")
        else:
            if has_idea:
                values.add("jetbrains")
            elif has_vs:
                values.add("visualstudio")
            elif has_vscode:
                values.add("vscode")
    return list(values)


def detect_templates(source: SourceName, includes: list[DetectInclude]) -> list[str]:
    provider: Provider = "gitignoreio" if source == "gitignoreio" else "github"
    rules: list[tuple[str, list[str], list[str]]] = [
        ("package.json", ["Node"], ["node"]),
        ("bun.lock", ["Node"], ["node"]),
        ("bun.lockb", ["Node"], ["node"]),
        ("pnpm-lock.yaml", ["Node"], ["node"]),
        ("yarn.lock", ["Node"], ["node"]),
        ("package-lock.json", ["Node"], ["node"]),
        ("Cargo.toml", ["Rust"], ["rust"]),
        ("go.mod", ["Go"], ["go"]),
        ("pyproject.toml", ["Python"], ["python"]),
        ("requirements.txt", ["Python"], ["python"]),
        ("Pipfile", ["Python"], ["python"]),
        (".venv", ["Python"], ["python"]),
    ]
    probe_exists = {probe: path_exists(probe) for probe, _, _ in rules}
    found: set[str] = set()
    for probe, github_values, gitignoreio_values in rules:
        if probe_exists[probe]:
            for value in (github_values if provider == "github" else gitignoreio_values):
                found.add(value)
    for extra in get_detected_extras(provider, includes):
        found.add(extra)
    if provider == "github":
        scope = source_to_github_scope(source)
        if scope == "global":
            return [name.removeprefix("Global/") for name in found if name.startswith("Global/")]
        if scope == "community":
            return [name.removeprefix("community/") for name in found if name.startswith("community/")]
    return list(found)


def parse_front_matter(content: str) -> tuple[dict[str, str], str]:
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end_index = normalized.find("\n---\n", 4)
    if end_index < 0:
        return {}, normalized
    front_matter = normalized[4:end_index]
    body = normalized[end_index + 5 :]
    metadata: dict[str, str] = {}
    for line in front_matter.split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip()
    return metadata, body


def create_license_aliases(slug: str, title: str, spdx_id: str | None) -> list[str]:
    aliases = [slug, title]
    if spdx_id:
        aliases.append(spdx_id)
    return unique_sorted(aliases)


def build_license_catalog_entry(path: str, content: str) -> LicenseCatalogEntry:
    slug = path.removeprefix("_licenses/").removesuffix(".txt")
    metadata, _ = parse_front_matter(content)
    title = metadata.get("title", slug)
    spdx_id = metadata.get("spdx-id")
    hidden = metadata.get("hidden") == "true"
    return LicenseCatalogEntry(slug, path, title, spdx_id, hidden, create_license_aliases(slug, title, spdx_id))


def get_license_catalog(no_cache: bool) -> list[LicenseCatalogEntry]:
    cache_path = cache_path_for("license-catalog")
    if not no_cache:
        cached = read_cache_payload(cache_path)
        if cached is not None:
            catalog = cached.get("catalog", cached)
            return [license_catalog_entry_from_cache(entry) for entry in catalog if not entry.get("hidden", False)]
    tree = fetch_json(LICENSE_TREE_URL, "Fetching license catalog")
    paths = sorted(
        item["path"]
        for item in tree["tree"]
        if item.get("type") == "blob" and item["path"].startswith("_licenses/") and item["path"].endswith(".txt")
    )
    catalog = [build_license_catalog_entry(path, fetch_text(f"{LICENSE_RAW_BASE}/{path}", f"Fetching license metadata {path.removeprefix('_licenses/').removesuffix('.txt')}")) for path in paths]
    if not no_cache:
        write_cache_payload(cache_path, {"etag": None, "catalog": [asdict(entry) for entry in catalog]})
    return [entry for entry in catalog if not entry.hidden]


def resolve_license_entry(name: str, catalog: list[LicenseCatalogEntry]) -> LicenseCatalogEntry | None:
    raw = normalize_text(name)
    loose = normalize_loose(name)
    for entry in catalog:
        if entry.key == raw or entry.title == raw or entry.spdx_id == raw:
            return entry
    lower = raw.lower()
    for entry in catalog:
        if entry.key.lower() == lower or entry.title.lower() == lower or (entry.spdx_id and entry.spdx_id.lower() == lower):
            return entry
    for entry in catalog:
        if any(normalize_loose(alias) == loose for alias in entry.aliases):
            return entry
    return None


def format_license_suggestions(query: str, catalog: list[LicenseCatalogEntry]) -> str:
    q = normalize_loose(query)
    ranked: list[tuple[int, LicenseCatalogEntry]] = []
    for entry in catalog:
        score = min(0 if normalize_loose(alias) in q or q in normalize_loose(alias) else levenshtein(q, normalize_loose(alias)) for alias in entry.aliases)
        ranked.append((score, entry))
    ranked.sort(key=lambda item: (item[0], item[1].key))
    suggestions = [entry.key for _, entry in ranked[:5]]
    return "" if not suggestions else "Did you mean:\n" + "\n".join(f"  - {item}" for item in suggestions)


def get_license_template(entry: LicenseCatalogEntry) -> LicenseTemplate:
    content = fetch_text(f"{LICENSE_RAW_BASE}/{entry.path}", f"Fetching license template {entry.key}")
    _, body = parse_front_matter(content)
    return LicenseTemplate(build_license_catalog_entry(entry.path, content), body if body.endswith("\n") else body + "\n")


def apply_license_placeholders(content: str, values: dict[str, str | None]) -> str:
    output = content
    year = values["year"] or str(time.gmtime().tm_year)
    output = output.replace("[year]", year).replace("[yyyy]", year).replace("<year>", year)
    fullname = values.get("fullname")
    if fullname:
        for token in ("[fullname]", "[name of copyright owner]", "[name of author]", "[copyright holder]", "<fullname>"):
            output = output.replace(token, fullname)
    project = values.get("project")
    if project:
        output = output.replace("[project]", project).replace("<project>", project)
    project_url = values.get("project_url")
    if project_url:
        for token in ("[projecturl]", "[project-url]", "<projecturl>", "<project-url>"):
            output = output.replace(token, project_url)
    return output


def should_write_to_stdout(output_explicit: bool) -> bool:
    return not output_explicit and not sys.stdout.isatty()


def resolve_license_invocation(rest: list[str]) -> tuple[str, list[str]]:
    if not rest:
        return "list", []
    action = rest[0].strip().lower()
    if action in ("list", "search", "view", "init"):
        return action, rest[1:]
    return "init", rest


def cmd_explain(name: str, source: SourceName, no_cache: bool) -> None:
    entry = resolve_entry(name, get_catalog(assert_single_source(source, "explain"), no_cache))
    if entry is None:
        raise ValueError(f"Template not found: {name}")
    print(json.dumps(asdict(entry), indent=2))


def cmd_diff(left: str, right: str, source: SourceName, no_cache: bool, no_comments: bool) -> None:
    content_left = build_init_content([left], source, no_cache, no_comments).splitlines(keepends=True)
    content_right = build_init_content([right], source, no_cache, no_comments).splitlines(keepends=True)
    sys.stdout.writelines(unified_diff(content_left, content_right, fromfile=left, tofile=right))


def cmd_list(source: SourceName, no_cache: bool) -> None:
    for entry in get_catalog(source, no_cache):
        print(display_name_for_source(entry, source))


def cmd_search(query: str, source: SourceName, no_cache: bool) -> None:
    query_loose = normalize_loose(query)
    results = [
        entry
        for entry in get_catalog(source, no_cache)
        if query_loose in normalize_loose(entry.display_name) or any(query_loose in normalize_loose(alias) for alias in entry.aliases)
    ]
    for entry in results:
        print(display_name_for_source(entry, source))


def cmd_view(name: str, source: SourceName, no_cache: bool, no_comments: bool) -> None:
    print(build_init_content([name], assert_single_source(source, "view"), no_cache, no_comments), end="")


def cmd_init(raw_names: list[str], source: SourceName, output: str, output_explicit: bool, force: bool, append: bool, no_cache: bool, no_comments: bool, force_stdout: bool = False) -> None:
    content = build_init_content(raw_names, source, no_cache, no_comments)
    if force_stdout or should_write_to_stdout(output_explicit):
        sys.stdout.write(content)
        return
    write_generated_content(output, content, force, append)
    print(f"Wrote {output}", file=sys.stderr)


def should_force_stdout_for_implicit_init(output_explicit: bool, append: bool) -> bool:
    return not output_explicit and not append


def cmd_detect(source: SourceName, output: str, output_explicit: bool, force: bool, append: bool, no_cache: bool, includes: list[DetectInclude], no_comments: bool) -> None:
    detected = detect_templates(assert_single_source(source, "detect"), includes)
    if not detected:
        raise ValueError("No templates detected")
    cmd_init(detected, source, output, output_explicit, force, append, no_cache, no_comments)


def cmd_license_list(no_cache: bool) -> None:
    catalog = get_license_catalog(no_cache)
    slug_width = max(len("Slug"), *(len(entry.key) for entry in catalog))
    spdx_width = max(len("SPDX"), *(len(entry.spdx_id or "") for entry in catalog))
    print(f"{'Slug'.ljust(slug_width)}  {'SPDX'.ljust(spdx_width)}  Title")
    print(f"{'-' * slug_width}  {'-' * spdx_width}  -----")
    for entry in catalog:
        print(f"{entry.key.ljust(slug_width)}  {(entry.spdx_id or '').ljust(spdx_width)}  {entry.title}")


def cmd_license_search(query: str, no_cache: bool) -> None:
    query_loose = normalize_loose(query)
    matches = [
        entry
        for entry in get_license_catalog(no_cache)
        if query_loose in normalize_loose(entry.key)
        or query_loose in normalize_loose(entry.title)
        or any(query_loose in normalize_loose(alias) for alias in entry.aliases)
    ]
    for entry in matches:
        print(entry.key)


def cmd_license_view(name: str, no_cache: bool) -> None:
    catalog = get_license_catalog(no_cache)
    entry = resolve_license_entry(name, catalog)
    if entry is None:
        print(f"License not found: {name}", file=sys.stderr)
        suggestions = format_license_suggestions(name, catalog)
        if suggestions:
            print(suggestions, file=sys.stderr)
        raise SystemExit(1)
    sys.stdout.write(get_license_template(entry).body)


def cmd_license_init(name: str, output: str, output_explicit: bool, force: bool, append: bool, no_cache: bool, values: dict[str, str | None]) -> None:
    catalog = get_license_catalog(no_cache)
    entry = resolve_license_entry(name, catalog)
    if entry is None:
        print(f"License not found: {name}", file=sys.stderr)
        suggestions = format_license_suggestions(name, catalog)
        if suggestions:
            print(suggestions, file=sys.stderr)
        raise SystemExit(1)
    content = apply_license_placeholders(get_license_template(entry).body, values)
    if should_write_to_stdout(output_explicit):
        sys.stdout.write(content)
        return
    write_generated_content(output, content, force, append)
    print(f"Wrote {output}", file=sys.stderr)


def cmd_compact(input_path: str | None, output_path: str, force: bool) -> None:
    source_path = Path(input_path or ".gitignore")
    if not source_path.exists():
        raise ValueError(f"Input file not found: {source_path}")
    compacted = compact_ignore_content(source_path.read_text("utf8"))
    if output_path == "-" or (output_path == ".gitignore" and not force and input_path is None and not sys.stdout.isatty()):
        sys.stdout.write(compacted)
        return
    write_generated_content(output_path, compacted, force, False)


def cmd_completion(shell_name: str) -> None:
    if shell_name not in SHELLS:
        raise ValueError("completion requires one of: bash, zsh, fish")
    print(get_completion_text(shell_name), end="")


def get_completion_install_target(shell_name: str) -> tuple[Path, str]:
    if shell_name == "bash":
        return Path.home() / ".gitig-completion.bash", "Add this to your shell profile if needed: source ~/.gitig-completion.bash"
    if shell_name == "zsh":
        return Path.home() / ".zsh" / "completions" / "_gitig", "Add this to your ~/.zshrc if needed: fpath=(~/.zsh/completions $fpath) && autoload -Uz compinit && compinit"
    if shell_name == "fish":
        return Path.home() / ".config" / "fish" / "completions" / "gitig.fish", "Fish should load this automatically in new shells."
    raise ValueError("install-completion requires one of: bash, zsh, fish")


def cmd_install_completion(shell_name: str) -> None:
    path, note = get_completion_install_target(shell_name)
    ensure_dir(path.parent)
    path.write_text(get_completion_text(shell_name), "utf8")
    print(f"Installed {shell_name} completion to {path}")
    print(note)


def print_doctor_checks(title: str, checks: list[DoctorCheck]) -> None:
    print(f"\n{title}")
    for check in checks:
        print(f"  {'OK ' if check.ok else 'NO '} {check.name}: {check.detail}")


def can_read_write_dir(path: Path) -> bool:
    try:
        ensure_dir(path)
        probe = path / ".gitig-write-test"
        probe.write_text("ok", "utf8")
        probe.unlink()
        return True
    except Exception:
        return False


def safe_load_catalog(source: SourceName, no_cache: bool) -> tuple[bool, str, int]:
    try:
        if source in ("github", "github-global", "github-community"):
            result = get_github_catalog_with_cache(no_cache)
            scope = source_to_github_scope(source)
            filtered = result.catalog if scope is None else filter_github_catalog_by_scope(result.catalog, scope)
            return True, f"{len(filtered)} templates available; cache {format_cache_status(result.cache, no_cache)}", len(filtered)
        if source == "gitignoreio":
            result = get_gitignoreio_catalog_with_cache(no_cache)
            return True, f"{len(result.catalog)} templates available; cache {format_cache_status(result.cache, no_cache)}", len(result.catalog)
        github = get_github_catalog_with_cache(no_cache)
        gitignoreio = get_gitignoreio_catalog_with_cache(no_cache)
        count = len(github.catalog) + len(gitignoreio.catalog)
        return True, f"{count} templates available; github cache {format_cache_status(github.cache, no_cache)}; gitignore.io cache {format_cache_status(gitignoreio.cache, no_cache)}", count
    except Exception as exc:
        return False, str(exc), 0


def get_platform_summary() -> str:
    if sys.platform == "darwin":
        return "darwin (macOS)"
    if sys.platform.startswith("win"):
        return "win32 (Windows)"
    return f"{sys.platform} (Unix-like)"


def cmd_doctor(no_cache: bool, json_output: bool = False) -> None:
    env_checks = [
        DoctorCheck("cache directory", can_read_write_dir(CACHE_DIR), f"{CACHE_DIR}"),
        DoctorCheck("platform", True, get_platform_summary()),
    ]
    provider_checks = [
        DoctorCheck(name, ok, detail)
        for name, (ok, detail, _) in {
            "github all": safe_load_catalog("github", no_cache),
            "github global": safe_load_catalog("github-global", no_cache),
            "github community": safe_load_catalog("github-community", no_cache),
            "gitignore.io": safe_load_catalog("gitignoreio", no_cache),
        }.items()
    ]
    detect_checks: list[DoctorCheck] = []
    for source, label in [("github", "detect gh"), ("github-global", "detect ghg"), ("gitignoreio", "detect tt")]:
        try:
            detected = detect_templates(source, ["os", "editor"])  # type: ignore[arg-type]
            detect_checks.append(DoctorCheck(label, True, ", ".join(detected) if detected else "no templates detected"))
        except Exception as exc:
            detect_checks.append(DoctorCheck(label, False, str(exc)))
    completion_checks = [DoctorCheck(f"{shell_name} completion target", True, str(get_completion_install_target(shell_name)[0])) for shell_name in SHELLS]
    all_checks = env_checks + provider_checks + detect_checks + completion_checks
    failed = len([check for check in all_checks if not check.ok])
    if json_output:
        print(
            json.dumps(
                {
                    "environment": [asdict(check) for check in env_checks],
                    "providers": [asdict(check) for check in provider_checks],
                    "detection": [asdict(check) for check in detect_checks],
                    "completions": [asdict(check) for check in completion_checks],
                    "summary": {"passed": len(all_checks) - failed, "total": len(all_checks)},
                },
                indent=2,
            )
        )
        if failed:
            raise SystemExit(1)
        return
    print("gitig doctor")
    print_doctor_checks("Environment", env_checks)
    print_doctor_checks("Providers", provider_checks)
    print_doctor_checks("Detection", detect_checks)
    print_doctor_checks("Completions", completion_checks)
    print(f"\nSummary: {len(all_checks) - failed}/{len(all_checks)} checks passed")
    if failed:
        raise SystemExit(1)


def pad_right(value: str, width: int) -> str:
    return value if len(value) >= width else value + " " * (width - len(value))


def print_stats_table(rows: list[StatsRow]) -> None:
    label_width = max(len("Label"), *(len(row.label) for row in rows))
    count_width = max(len("Count"), *(len(str(row.count)) for row in rows))
    print(f"{pad_right('Label', label_width)}  {pad_right('Count', count_width)}")
    print(f"{'-' * label_width}  {'-' * count_width}")
    for row in rows:
        print(f"{pad_right(row.label, label_width)}  {pad_right(str(row.count), count_width)}")


def cmd_stats(source: SourceName, no_cache: bool, json_output: bool = False) -> None:
    if json_output:
        if source == "all":
            github = get_github_catalog_with_cache(no_cache)
            gitignoreio = get_gitignoreio_catalog_with_cache(no_cache)
            print(json.dumps({
                "github_total": len(github.catalog),
                "github_root": len([entry for entry in github.catalog if entry.github_scope == "root"]),
                "github_global": len([entry for entry in github.catalog if entry.github_scope == "global"]),
                "github_community": len([entry for entry in github.catalog if entry.github_scope == "community"]),
                "gitignoreio_total": len(gitignoreio.catalog),
                "all_combined": len(github.catalog) + len(gitignoreio.catalog),
            }, indent=2))
            return
    if source == "all":
        github = get_github_catalog_with_cache(no_cache)
        gitignoreio = get_gitignoreio_catalog_with_cache(no_cache)
        rows = [
            StatsRow("github total", len(github.catalog)),
            StatsRow("github root", len([entry for entry in github.catalog if entry.github_scope == "root"])),
            StatsRow("github global", len([entry for entry in github.catalog if entry.github_scope == "global"])),
            StatsRow("github community", len([entry for entry in github.catalog if entry.github_scope == "community"])),
            StatsRow("gitignore.io total", len(gitignoreio.catalog)),
            StatsRow("all combined", len(github.catalog) + len(gitignoreio.catalog)),
        ]
        print_stats_table(rows)
        print(f"\nGitHub cache: {format_cache_status(github.cache, no_cache)}")
        print(f"gitignore.io cache: {format_cache_status(gitignoreio.cache, no_cache)}")
        return
    if source == "gitignoreio":
        result = get_gitignoreio_catalog_with_cache(no_cache)
        print_stats_table([StatsRow("gitignore.io", len(result.catalog))])
        print(f"\nCache: {format_cache_status(result.cache, no_cache)}")
        return
    result = get_github_catalog_with_cache(no_cache)
    scope = source_to_github_scope(source)
    filtered = result.catalog if scope is None else filter_github_catalog_by_scope(result.catalog, scope)
    label = "github global" if source == "github-global" else "github community" if source == "github-community" else "github"
    print_stats_table([StatsRow(label, len(filtered))])
    print(f"\nCache: {format_cache_status(result.cache, no_cache)}")


def assert_equal_strings(actual: list[str], expected: list[str], label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_equal_string(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _test_parse_append(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["init", "gh:Node", "--append", "-o", "Makefile"])
    assert_equal_string(str(parsed.append), "True", "append flag")
    assert_equal_string(str(parsed.output_explicit), "True", "output explicit flag")
    assert_equal_string(parsed.output, "Makefile", "append output path")


def _test_parse_na(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["init", "gh:Node", "-na"])
    assert_equal_string(str(parsed.append), "True", "append shorthand")
    assert_equal_string(str(parsed.no_comments), "True", "no comments shorthand")


def _test_parse_anc(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["init", "gh:Node", "-anc"])
    assert_equal_string(str(parsed.append), "True", "append compact shorthand")
    assert_equal_string(str(parsed.no_comments), "True", "append compact no comments shorthand")


def _test_parse_nac(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["init", "gh:Node", "-nac"])
    assert_equal_string(str(parsed.append), "True", "append mixed-order shorthand")
    assert_equal_string(str(parsed.no_comments), "True", "append mixed-order no comments shorthand")


def _test_parse_compact_alias(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["-c", ".gitignore"])
    assert_equal_string(parsed.command or "", "compact", "compact alias command")
    assert_equal_strings(parsed.rest, [".gitignore"], "compact alias args")


def _test_parse_flag_order(parse_args: Callable[[list[str]], Any]) -> None:
    parsed_after = parse_args(["gh:python", "-nac"])
    parsed_before = parse_args(["-nac", "gh:python"])
    assert_equal_string(parsed_after.command or "", "gh:python", "flag order command after")
    assert_equal_string(parsed_before.command or "", "gh:python", "flag order command before")
    assert_equal_string(str(parsed_after.append), "True", "flag order append after")
    assert_equal_string(str(parsed_before.append), "True", "flag order append before")
    assert_equal_string(str(parsed_after.no_comments), "True", "flag order no comments after")
    assert_equal_string(str(parsed_before.no_comments), "True", "flag order no comments before")


def _test_parse_license_fields(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["license", "init", "mit", "--fullname", "Jane Doe", "--project", "gitig", "--year", "2026"])
    assert_equal_string(parsed.fullname or "", "Jane Doe", "license fullname")
    assert_equal_string(parsed.project or "", "gitig", "license project")
    assert_equal_string(parsed.year or "", "2026", "license year")


def _test_parse_fullname_aliases(parse_args: Callable[[list[str]], Any]) -> None:
    author_parsed = parse_args(["license", "init", "mit", "--author", "Jane Doe"])
    owner_parsed = parse_args(["license", "init", "mit", "--owner", "Jane Doe"])
    assert_equal_string(author_parsed.fullname or "", "Jane Doe", "license author alias")
    assert_equal_string(owner_parsed.fullname or "", "Jane Doe", "license owner alias")


def _test_parse_quiet_flag(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["update", "--quiet"])
    assert_equal_string(str(parsed.quiet), "True", "quiet flag")


def _test_parse_json_flag(parse_args: Callable[[list[str]], Any]) -> None:
    parsed = parse_args(["update", "--json"])
    assert_equal_string(str(parsed.json_output), "True", "json flag")


def _test_parse_front_matter() -> None:
    metadata, body = parse_front_matter("---\ntitle: MIT License\nspdx-id: MIT\nhidden: false\n---\nBody\n")
    assert_equal_string(metadata.get("title", ""), "MIT License", "front matter title")
    assert_equal_string(body, "Body\n", "front matter body")


def _test_apply_license_placeholders() -> None:
    rendered = apply_license_placeholders(
        "Copyright [year] [fullname]\n[project]\n[projecturl]\n",
        {"year": "2026", "fullname": "Jane Doe", "project": "gitig", "project_url": "https://example.com/gitig"},
    )
    assert_equal_string(rendered, "Copyright 2026 Jane Doe\ngitig\nhttps://example.com/gitig\n", "license placeholders")


def get_self_tests(parse_args: Callable[[list[str]], Any]) -> list[SelfTestCase]:
    return [
        SelfTestCase("parseTemplateArgs supports sticky gh prefix across spaces", lambda: assert_equal_strings(parse_template_args(["gh:", "node", "python"]), ["gh:node", "gh:python"], "sticky gh prefix")),
        SelfTestCase("parseTemplateArgs supports mixed comma and space input", lambda: assert_equal_strings(parse_template_args(["gh:", "node,python", "go"]), ["gh:node", "gh:python", "gh:go"], "mixed comma and space input")),
        SelfTestCase("parseTemplateArgs switches sticky prefix when explicit prefix appears", lambda: assert_equal_strings(parse_template_args(["gh:", "node", "tt:macos", "vscode"]), ["gh:node", "tt:macos", "tt:vscode"], "sticky prefix switching")),
        SelfTestCase("parseArgs recognizes append flags", lambda: _test_parse_append(parse_args)),
        SelfTestCase("parseArgs recognizes -na as append without comments", lambda: _test_parse_na(parse_args)),
        SelfTestCase("parseArgs recognizes -anc as append without comments", lambda: _test_parse_anc(parse_args)),
        SelfTestCase("parseArgs recognizes -nac as append without comments", lambda: _test_parse_nac(parse_args)),
        SelfTestCase("parseArgs recognizes -c as compact alias", lambda: _test_parse_compact_alias(parse_args)),
        SelfTestCase("parseArgs allows flags before or after template input", lambda: _test_parse_flag_order(parse_args)),
        SelfTestCase("implicit init only forces stdout without append or explicit output", lambda: assert_equal_string(str(should_force_stdout_for_implicit_init(False, False)), "True", "implicit init stdout default")),
        SelfTestCase("parseArgs recognizes license fullname, project, and year", lambda: _test_parse_license_fields(parse_args)),
        SelfTestCase("parseArgs keeps --author and --owner as fullname aliases", lambda: _test_parse_fullname_aliases(parse_args)),
        SelfTestCase("parseArgs recognizes --quiet", lambda: _test_parse_quiet_flag(parse_args)),
        SelfTestCase("parseArgs recognizes --json", lambda: _test_parse_json_flag(parse_args)),
        SelfTestCase("resolveLicenseInvocation defaults to list", lambda: assert_equal_string(resolve_license_invocation([])[0], "list", "license default action")),
        SelfTestCase("mergeAppendedContent dedupes repeated lines", lambda: assert_equal_string(merge_appended_content("a\nb\n", "b\nc\n"), "a\nb\nc\n", "append dedupe")),
        SelfTestCase("parseTemplateArgs trims empty comma segments", lambda: assert_equal_strings(parse_template_args(["gh:", "node,,python", "", "go,"]), ["gh:node", "gh:python", "gh:go"], "empty comma segments")),
        SelfTestCase("compactIgnoreContent preserves escaped comment lines and collapses blanks", lambda: assert_equal_string(compact_ignore_content("# comment\nfoo\n\n\n\\#literal\n   # another\nbar\n\n"), "foo\n\n\\#literal\nbar\n", "escaped comments")),
        SelfTestCase("parseFrontMatter extracts title and body", _test_parse_front_matter),
        SelfTestCase("applyLicensePlaceholders replaces known license tokens", _test_apply_license_placeholders),
        SelfTestCase("bash completion contains template stub hook", lambda: assert_equal_string(str("_gitig_template_stub" in get_completion_text("bash")), "True", "bash completion hook")),
        SelfTestCase("zsh completion knows check and selftest commands", lambda: assert_equal_string(str("check selftest" in get_completion_text("zsh")), "True", "zsh completion")),
        SelfTestCase("completion exposes license commands", lambda: assert_equal_string(str("license" in get_completion_text("fish")), "True", "fish completion")),
    ]


def cmd_selftest(parse_args: Callable[[list[str]], Any]) -> None:
    tests = get_self_tests(parse_args)
    passed = 0
    print("gitig selftest")
    for test in tests:
        try:
            test.run()
            print(f"  OK  {test.name}")
            passed += 1
        except Exception as exc:
            print(f"  NO  {test.name}: {exc}")
    print(f"\nSummary: {passed}/{len(tests)} checks passed")
    if passed != len(tests):
        raise SystemExit(1)
