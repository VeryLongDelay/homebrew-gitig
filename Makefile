PREFIX ?= $(HOME)/.local
BIN_DIR ?= $(PREFIX)/bin
TARGET ?= $(BIN_DIR)/gitig
SOURCE := $(CURDIR)/gitig.py

.PHONY: clean deploy-local uninstall-local test test-local

deploy-local:
	mkdir -p "$(BIN_DIR)"
	chmod +x "$(SOURCE)"
	ln -sf "$(SOURCE)" "$(TARGET)"
	@echo "Installed gitig to $(TARGET)"
	@echo "Run: $(TARGET) help"

uninstall-local:
	rm -f "$(TARGET)"
	@echo "Removed $(TARGET)"

test:
	python3 -m unittest discover -s tests -p 'test_*.py'
	python3 gitig.py selftest

test-local: deploy-local test
	"$(TARGET)" help

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete
	rm -rf build/ dist/ *.egg-info/ .eggs/
	rm -f *.pyo *~

	echo "Cleaned Python generated objects."
