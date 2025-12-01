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
	uv run python -m py_compile *.py
	@echo "Running tests..."
	uv run pytest -v
