.PHONY: install check test test-musescore clean skill

install:
	uv sync
	uv run prek install
	@echo "📥 Successfully installed the dependencies and the commit hooks."

check:
	uv run prek run --all-files
	@echo "🔍 Successfully executed the checks."

test:
	uv run pytest --no-musescore --cov
	@echo "🧪 Successfully executed the tests."

test-musescore:
	uv run pytest
	@echo "🧪 Successfully executed the tests, including MuseScore."

clean:
	@find . -type d \( -name '__pycache__' -o -name '.ruff_cache' -o -name '.pytest_cache' \) -exec rm -rf {} +
	@rm -f .coverage
	@rm -rf artifacts
	@echo "🧹 Successfully cleaned project."

skill:
	@mkdir -p artifacts
	@rm -f artifacts/musescore-drum-chart.zip
	cd skills && zip -qr ../artifacts/musescore-drum-chart.zip musescore-drum-chart
	@echo "📦 Packaged artifacts/musescore-drum-chart.zip (upload it in Claude Desktop or claude.ai)."
