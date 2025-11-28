FROM python:3.12-slim

WORKDIR /action

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY action.py .

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Set the entrypoint
ENTRYPOINT ["uv", "run", "python", "/action/action.py"]
