FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git \
  && apt-get purge -y --auto-remove \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /action
USER root

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

# Copy project files
COPY .python-version .
COPY pyproject.toml .
COPY uv.lock .
COPY src/ ./src/
COPY action.py .

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Set the entrypoint
ENTRYPOINT ["uv", "run", "/action/action.py"]
