FROM python:3.12-slim

WORKDIR /action

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY action.py .

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Set the entrypoint
ENTRYPOINT ["uv", "run", "/action/action.py"]
