.PHONY: setup
setup:
	@echo "Installing Python 3.12 and syncing dependencies..."
	uv python install 3.12
	uv sync --all-extras

.PHONY: format
format:
	@echo "Formatting code..."
	uv run ruff format .

.PHONY: format-check
format-check:
	@echo "Checking code formatting..."
	uv run ruff format --check .

.PHONY: lint
lint:
	@echo "Running linter..."
	uv run ruff check .

.PHONY: fix
fix:
	@echo "Auto-fixing linting issues..."
	uv run ruff check --fix .
	@echo "Auto-formatting code..."
	uv run ruff format .

.PHONY: test
test:
	@echo "Running syntax checks..."
	uv run python -m compileall *.py src/
	@echo "Running tests..."
	uv run pytest -v

.PHONY: package
package:
	@echo "Creating runnable zip file..."
	rm -rf /tmp/analyzer
	mkdir -p /tmp/analyzer/src
	cp cli.py /tmp/analyzer/__main__.py
	cp src/*.py /tmp/analyzer/src
	uv export --format requirements.txt -o /tmp/analyzer/requirements.txt --no-hashes --no-dev
	uv run pip install -r /tmp/analyzer/requirements.txt --target /tmp/analyzer
	rm /tmp/analyzer/requirements.txt
