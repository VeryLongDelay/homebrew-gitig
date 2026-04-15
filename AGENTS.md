# 📦 Project Context: `gitig`

## Overview

**gitig** is a **CLI tool for generating `.gitignore` files and LICENSE files** from:

- GitHub gitignore repo
- gitignore.io (Toptal)
- choosealicense.com (GitHub)

It is designed to be:

- ⚡ fast (cache + parallel fetch)
- 🧠 smart (template detection, suggestions)
- 🧰 minimal (no external deps, stdlib only)
- 🖥️ terminal-first UX (spinner, colors, clean output)

---

# 🏗️ Key Features

## Core Commands

```bash
gitig list
gitig search <query>
gitig view <template>
gitig init <templates...>
gitig detect
gitig compact
gitig license
gitig doctor
gitig stats
gitig update
```

---

## 🚀 `update` command (latest addition)

Primary command for refreshing catalogs.

### Usage

```bash
gitig update
gitig update all

gitig update github
gitig update gh
gitig update ghg
gitig update ghc
gitig update tt
gitig update license
```

### Flags

```bash
gitig update --quiet
gitig update --json
```

### Behavior

- Refreshes:
  - GitHub gitignore catalog
  - gitignore.io catalog
  - license catalog

- Uses **parallel fetch** when updating multiple sources
- Writes to local cache
- Supports:
  - `--quiet` → no stdout output
  - `--json` → structured output (disables spinner)

### Backward compatibility

```bash
gitig update-catalog
gitig refresh-catalog
```

---

# 🎨 Spinner System

## Style

Uses braille animation:

```
⠋ ⠙ ⠚ ⠞ ⠖ ⠦ ⠴ ⠲ ⠳ ⠓
```

## Behavior

- Runs at **100ms interval**
- Clears line before redraw
- Writes to **stderr**
- Disabled when:
  - non-TTY
  - `--no-color`
  - `NO_COLOR` / `NO_COLOUR`
  - `--json` mode

## Colors

- Spinner: `#4788d0`
- `done`: `#4788d0`
- `failed`: red

---

# ⚡ Performance Optimizations

## 1. Parallel Fetch (NEW)

- `update all` runs:
  - GitHub
  - gitignore.io
  - license

- concurrently using threads

---

## 2. Configurable Cache TTL

Environment variables:

```bash
GITIG_GITHUB_CATALOG_CACHE_TTL_SECONDS
GITIG_GITIGNOREIO_CATALOG_CACHE_TTL_SECONDS
GITIG_LICENSE_CATALOG_CACHE_TTL_SECONDS
```

Defaults:

- 24 hours

---

## 3. HTTP Improvements

- Shared timeout (15s)
- Spinner wraps all network calls

---

## 4. Smarter Suggestions

- Shortlist before Levenshtein
- Reduced CPU cost

---

## 5. File System Optimization

- Precomputed probe existence in `detect`
- Reduced repeated `.exists()` calls

---

# 🧠 Architecture

## Key Components

### Catalog Loaders

```python
get_github_catalog_with_cache()
get_gitignoreio_catalog_with_cache()
get_license_catalog()
```

### Fetch Layer

```python
fetch_bytes()
fetch_json()
fetch_text()
```

All network calls go through:

- spinner
- timeout
- optional no-color

---

### Spinner

Single shared class used across:

- catalog fetch
- template fetch
- license fetch
- update command

---

### Cache

Stored in:

```bash
~/.cache/gitig/
```

Files:

- `github-catalog.json`
- `gitignoreio-catalog.json`
- `license-catalog.json`

---

# 🧪 Testing

Built-in:

```bash
gitig selftest
```

Covers:

- argument parsing
- template parsing
- license formatting
- edge cases

---

# ⚠️ Known Constraints

- No external dependencies (stdlib only)
- Spinner uses threads (lightweight but present)
- Unicode spinner requires modern terminal

---

# 🔥 Recent Changes (Important)

1. ✅ Replaced spinner with braille animation
2. ✅ Added color system + `--no-color`
3. ✅ Added `update` command (primary)
4. ✅ Added `--quiet` and `--json`
5. ✅ Added parallel fetch
6. ✅ Added configurable cache TTL
7. ✅ Fixed detect bug (`or True`)
8. ✅ Optimized suggestions + filesystem checks

---

# 🎯 Design Philosophy

- Prefer **simple CLI UX**
- Keep **one obvious command** (`update`)
- Optimize for **fast feedback**
- Avoid unnecessary dependencies
- Keep code **readable + hackable**

---

# 🧩 What I might want next

(Useful for next chat)

- delayed spinner start (avoid flicker)
- `--json` for other commands
- background auto-refresh
- cache invalidation strategy
- richer template metadata
- better fuzzy search

---
