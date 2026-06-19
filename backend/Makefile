.PHONY: lint test check-all

lint:
	python3 scripts/lint_btdeck.py
	ruff check app/

test:
	python3 -m pytest tests/ -v

check-all: lint test
	@echo "All checks passed!"
