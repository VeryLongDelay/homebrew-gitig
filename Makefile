.PHONY: clean build release-artifacts release formula-sha print-formula-sha formula-url test test-hook deploy-local test-local uninstall-local unlink-local install-hooks install-pre-commit run-pre-commit

PYTHON ?= python3
UV ?= uv
PRE_COMMIT ?= pre-commit
DIST_DIR ?= dist
FORMULA ?= Formula/gitig.rb
UV_CACHE_DIR ?= .uv-cache
PREFIX ?= $(HOME)/.local
BIN_DIR ?= $(PREFIX)/bin
INSTALL_NAME ?= gitig
INSTALL_PATH ?= $(BIN_DIR)/$(INSTALL_NAME)
REPO_ROOT := $(CURDIR)

VERSION := $(shell $(PYTHON) -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')

SDIST := $(DIST_DIR)/gitig-$(VERSION).tar.gz
WHEEL := $(DIST_DIR)/gitig-$(VERSION)-py3-none-any.whl
FORMULA_URL := https://github.com/verylongdelay/gitig/archive/refs/tags/v$(VERSION).tar.gz

clean:
	rm -rf $(DIST_DIR)

build: clean
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) build

release-artifact: release-artifacts

release-artifacts: build
	@echo "Built release artifacts:"
	@ls -1 $(SDIST) $(WHEEL)
	@echo
	@echo "Artifact checksums:"
	@shasum -a 256 $(SDIST) $(WHEEL)

test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python tests/test_gitig.py

test-hook:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m unittest tests.test_formula_hook

install-hooks:
	$(MAKE) install-pre-commit

install-pre-commit:
	chmod +x scripts/check_formula_sha.py
	$(PRE_COMMIT) install --config .pre-commit.yml
	@echo "Installed pre-commit hook from $(REPO_ROOT)/.pre-commit.yml"

run-pre-commit:
	$(PRE_COMMIT) run --config .pre-commit.yml --all-files

deploy-local:
	mkdir -p $(BIN_DIR)
	@printf '%s\n' '#!/bin/sh' 'exec "$(shell command -v $(UV) || printf %s $(UV))" run --project "$(REPO_ROOT)" gitig "$$@"' > $(INSTALL_PATH)
	chmod +x $(INSTALL_PATH)
	@echo "Installed $(INSTALL_PATH)"

test-local: deploy-local
	$(INSTALL_PATH) help

uninstall-local:
	rm -f $(INSTALL_PATH)
	@echo "Removed $(INSTALL_PATH)"

unlink-local: uninstall-local

formula-sha:
	@TMP_ARCHIVE="$${TMPDIR:-/tmp}/gitig-formula-$(VERSION).tar.gz"; \
	curl --fail --silent --show-error --location --output "$$TMP_ARCHIVE" "$(FORMULA_URL)"; \
	SHA="$$(shasum -a 256 "$$TMP_ARCHIVE" | awk '{print $$1}')"; \
	rm -f "$$TMP_ARCHIVE"; \
	echo "sha256 \"$$SHA\""; \
	echo "Formula: $(FORMULA)"; \
	echo "URL: $(FORMULA_URL)"

print-formula-sha: formula-sha

formula-url:
	@echo $(FORMULA_URL)

release: release-artifacts
	@echo
	@echo "Homebrew formula values:"
	@echo "url \"$(FORMULA_URL)\""
	@echo "Run 'make formula-sha' after the v$(VERSION) tag is published to GitHub."
