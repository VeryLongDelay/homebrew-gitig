# gitig

`gitig` is an ignorant Python CLI for generating `.gitignore` and `LICENSE` files.

It can:

- fetch templates from `github/gitignore`
- fetch templates from Toptal `gitignore.io`
- generate licenses from `github/choosealicense.com`
- combine multiple templates
- detect likely templates from the current project
- strip comments from generated output or existing files
- install shell completions
- show provider stats and diagnostics

## Features

- Python 3
- primary CLI entrypoint: `gitig.py`
- minimal dependencies
- case-insensitive template matching
- sticky provider prefixes such as `gh: node python`
- `--no-comments` / `-nc` support for `view`, `init`, and `detect`
- `compact` command for existing `.gitignore` files
- `license` subcommands for listing, searching, viewing, and generating licenses

## Install

### From a local checkout

```bash
python3 gitig.py help
```

### With Homebrew (tap in this repo)

```bash
brew tap verylongdelay/gitig
brew install gitig
gitig selftest
```

Note: `Formula/gitig.rb` is updated on tag releases to set the correct `url` and `sha256`.

## Commands

```text
gitig list
gitig search
gitig view
gitig init
gitig I
gitig i
gitig detect
gitig compact
gitig license
gitig doctor
gitig stats
gitig completion
gitig install-completion
gitig help
```

## Provider aliases

- `gh` → all GitHub templates
- `ghg` → GitHub `Global/` templates only
- `ghc` → GitHub `community/` templates only
- `tt` → `gitignore.io`

## Examples

```bash
gitig list --source gh
gitig list --source ghg
gitig list --source ghc
gitig list --source tt

gitig view gh:Node
gitig view ghg:macOS
gitig view ghc:Python/Poetry
gitig view tt:node
gitig view gh:Node -nc
gitig gh:Node
gitig gh:Node -nc

gitig init gh:Node,ghg:macOS --force
gitig init gh:Node ghg:macOS --force
gitig I gh:Node ghg:macOS
gitig i gh:node ghg:macos -nc
gitig i gh:node > .gitignore
gitig i gh:node --append -o Makefile
gitig i gh:node -a -o Makefile
gitig i gh:node -na -o Makefile
gitig i gh:node -anc -o Makefile

gitig i gh: node python
gitig i ghg: macos jetbrains
gitig i ghc: python/poetry javascript/node
gitig i tt: node macos vscode

gitig detect --source gh --include os,editor --force
gitig detect --source ghg --include os,editor -nc --force

gitig compact
gitig -c
gitig compact .gitignore
gitig compact .gitignore --output .gitignore.clean --force

gitig li mit --fullname "Jane Doe"
gitig -li mit --fullname "Jane Doe"
gitig license list
gitig license search apache
gitig license view mit
gitig license
gitig license init mit --fullname "Jane Doe"
gitig license init apache-2.0 --fullname "Jane Doe" --project gitig --projecturl https://example.com --year 2026 --output LICENSE
gitig license init unlicense > LICENSE

gitig doctor
gitig stats
gitig stats --source gh
gitig stats --source ghg
gitig stats --source ghc
gitig stats --source tt
```

## Sticky prefixes

These inputs are supported:

```bash
gitig i gh: node python
gitig i ghg: macos jetbrains
gitig i ghc: python/poetry javascript/node
gitig i tt: node macos vscode
gitig i gh: node,python
gitig i gh: node python,go
```

For example:

```bash
gitig i gh: node python
```

is treated like:

```bash
gitig i gh:node gh:python
```

## `--no-comments`

Supported for:

- `view`
- `init`
- `detect`

Behavior:

- removes full-line comments
- removes blank lines that become empty
- keeps actual ignore patterns
- keeps escaped `\#...` lines

## `compact`

`compact` strips comments from an existing `.gitignore`-style file.

Examples:

```bash
gitig compact
gitig compact .gitignore
gitig compact .gitignore --output .gitignore.clean --force
```

Default input is `.gitignore`.

## Shell completions

Supported shells:

- `bash`
- `zsh`
- `fish`

Commands:

```bash
gitig completion bash
gitig completion zsh
gitig completion fish

gitig install-completion bash
gitig install-completion zsh
gitig install-completion fish
```

## Notes

- GitHub templates are loaded from the `github/gitignore` repo tree, not only the templates API.
- `ghg` names are relative to `Global/`, so `ghg:macOS` resolves to `Global/macOS`.
- `ghc` names are relative to `community/`, so `ghc:Python/Poetry` resolves to `community/Python/Poetry`.
- `detect` supports `github`, `gh`, `ghg`, `gitignoreio`, and `tt`, but not `ghc`.
- `init` does not allow mixing GitHub and `gitignore.io` templates in the same run.

## Development

```bash
uv venv
. .venv/bin/activate

uv pip install -e .
gitig selftest
```

### Build (sdist/wheel)

```bash
uv build
python -m pip install dist/*.tar.gz
gitig selftest
```

## Publishing checklist

```bash
uv build
gitig selftest
```
