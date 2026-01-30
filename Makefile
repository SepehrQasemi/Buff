.PHONY: lint test format-check

lint:
	ruff check .

test:
	pytest -q

format-check:
	ruff format --check .
