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
