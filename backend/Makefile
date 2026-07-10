.PHONY: lint test check-all

lint:
	python3 -m black --check app/
	python3 -m flake8 app/
	python3 -m mypy app/
	python3 scripts/lint_btdeck.py
	python3 -m ruff check app/

test:
	python3 -m pytest tests/ -v

check-all: lint test
	@echo "All checks passed!"
