.PHONY: install check test test-musescore

install:
	uv sync
	uv run prek install

check:
	uv run prek run --all-files

test:
	uv run pytest --no-musescore --cov

test-musescore:
	uv run pytest
