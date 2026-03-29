Here’s a **clean, updated context summary** you can paste into a new chat to continue development seamlessly.

---

# gitig – Project Context (2026)

I am building a CLI tool called **`gitig`** for generating and managing `.gitignore` files and project licenses.

---

# Core Purpose

`gitig` allows users to:

- fetch `.gitignore` templates from:
  - **github/gitignore**
  - **gitignore.io**
- fetch license templates from:
  - **github/choosealicense.com**

- combine multiple templates
- detect likely templates from the current project
- strip comments from `.gitignore` files
- generate `LICENSE` files from choosealicense templates
- install shell completions
- show stats and diagnostics

---

# Tech Stack

- **Node.js + TypeScript (no Bun)**
- compiled to:

  ```
  dist/gitig.js
  ```

- single CLI entrypoint
- minimal dependencies (ideally none at runtime)

---

# Design Goals

- fast CLI startup
- zero / minimal runtime dependencies
- strict TypeScript safety (no “possibly undefined”)
- small readable functions
- case-insensitive matching
- good CLI ergonomics

---

# CLI Commands

Supported commands:

```bash
list
search
view
init (aliases: I, i)
detect
compact
license (subcommands: list, search, view, init; bare `license <name>` aliases init)
doctor
stats
check
selftest
completion
install-completion
help
```

---

# Providers

### Supported

- `github`
- `gitignoreio`

### Aliases

```bash
gh   → GitHub (all)
ghg  → GitHub Global/
ghc  → GitHub community/
tt   → gitignore.io
```

---

# Template Resolution

### GitHub Source

- repo: `github/gitignore`
- branch: `main`
- uses recursive tree API
- supports:
  - root templates
  - `Global/`
  - `community/`

### License Source

- repo: `github/choosealicense.com`
- branch: `gh-pages`
- reads `_licenses/*.txt`
- parses YAML front matter for `title`, `spdx-id`, and `hidden`
- ignores hidden licenses in the public catalog

---

# Template Parsing Behavior

Handled by `parseTemplateArgs`.

Supports:

### Sticky prefixes

```bash
gitig i gh: node python
→ gh:node gh:python
```

### Mixed separators

```bash
gitig i gh:node,python go
```

### Case-insensitive

```bash
gh:node
ghg:macos
ghc:python/poetry
```

---

# Validation Rules

### ❌ Do NOT mix providers

```bash
gitig i gh:Node tt:node   # error
```

### `detect`

Supports:

- `gh`, `ghg`, `tt`
- ❌ not `ghc`

---

# Flags

```bash
--output, -o
--append, -a
-na
--force, -f
--fullname
--author
--owner
--project
--projecturl
--year
--source, -s
--include
--no-cache
--no-comments, -nc
```

---

# `--no-comments` Behavior

- removes full-line comments
- preserves escaped comments:

  ```
  \# literal
  ```

- collapses duplicate blank lines
- keeps meaningful spacing

Used in:

```bash
view
init
detect
compact
```

### `--append` Behavior

- for `init` and `detect`
- appends into the target file instead of requiring overwrite
- dedupes immediately when the file already exists
- `-na` appends with full-line comments stripped
- when `init` or `detect` are redirected with `>`, generated content goes to stdout and the `Wrote ...` status line is suppressed

### License Commands

- `license list` prints available license slugs
- `license search <query>` searches slug, title, and SPDX id
- `license view <license>` prints the raw license body without front matter
- `license init <license>` writes a rendered `LICENSE` file
- bare `license` aliases `license list`
- `license init` supports `--fullname`, `--project`, `--projecturl`, and `--year`
- `--author` and `--owner` are compatibility aliases for `--fullname`
- `license init` defaults `--output` to `LICENSE`
- if no placeholders are provided, only `[year]` is filled with the current year
- `license init` replaces placeholders like `[year]`, `[yyyy]`, `[fullname]`, `[project]`, `[projecturl]`, and `[name of copyright owner]`

---

# `compact`

```bash
gitig compact
gitig compact .gitignore
gitig compact .gitignore --output clean --force
```

Now shares logic with `--no-comments`.

---

# Caching

Stored in:

```bash
~/.cache/gitig
```

Includes:

- GitHub catalog
- gitignore.io catalog

Features:

- TTL: 24h
- `--no-cache`
- cache status reporting

---

# `stats` Improvements

Shows:

- provider counts
- GitHub scope counts
- cache:
  - hit / miss / stale / bypassed
  - cache age
  - cache path

---

# `doctor`

Checks:

- cache health + age
- provider availability
- detection behavior
- completion install paths

---

# Self Tests

Command:

```bash
gitig check
gitig selftest
```

Covers:

- template parsing edge cases
- sticky prefix behavior
- mixed separators

No external dependencies.

---

# Shell Completions

Supports:

```bash
bash
zsh
fish
```

Commands:

```bash
gitig completion <shell>
gitig install-completion <shell>
```

Design:

- includes aliases (`i`, `I`)
- includes flags (`-nc`)
- structured to allow **future template-aware completion**

---

# Local Development

## Build

```bash
npm run build
```

## Run

```bash
node dist/gitig.js help
```

## Link globally (dev)

```bash
npm link
```

---

# ⚠️ Important Build Detail

After `npm run build`, the executable bit can be lost.

### Required

- `gitig.ts` must start with:

  ```ts
  #!/usr/bin/env node
  ```

- build script must include:

```json
"build": "tsc -p tsconfig.json && chmod +x dist/gitig.js"
```

Otherwise:

```bash
zsh: permission denied: gitig
```

---

# Installation (local, no Homebrew)

### Recommended

```bash
npm install -g .
```

or:

```bash
npm link
```

---

# Homebrew Support

Supports:

- local tap testing
- published tap

## Key distinction

### Local testing

Uses:

```
file://.../gitig-x.x.x.tgz
```

### Published

Uses:

```
https://registry.npmjs.org/gitig/-/gitig-x.x.x.tgz
```

---

# Scripts

### `release-homebrew.sh`

Modes:

```bash
--mode local   # for testing
--mode npm     # for real releases
```

---

### `install-homebrew-local.sh`

- creates local git-backed tap
- installs via:

```bash
brew install local/tap/gitig
```

- handles Apple Silicon (`arch -arm64`)

---

# GitHub Actions

- triggers on tags (`v*`)
- builds
- runs selftest
- optionally publishes to npm (skips if no token)
- updates Homebrew tap

---

# Example Usage

```bash
gitig list --source gh
gitig view gh:Node -nc
gitig i gh: node python
gitig i ghg: macos jetbrains
gitig detect --source gh --include os,editor
gitig compact
gitig stats
gitig doctor
gitig selftest
```

---

# Next Possible Improvements

Good next steps:

- template-aware shell completion
- GitHub Releases + changelog automation
- version/tag consistency check
- binary build (pkg / single-file)
- faster catalog caching (ETag support)
- plugin system (future)

---
