FROM ghcr.io/astral-sh/uv:alpine AS builder

COPY pyproject.toml .
COPY uv.lock .

RUN uv export --no-hashes --format requirements-txt > requirements.txt

FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git \
  && apt-get purge -y --auto-remove \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /action

# Copy project files
COPY --from=builder requirements.txt .
COPY pyproject.toml .
COPY src/ ./src/
COPY action.py .

# Install dependencies using uv
RUN pip install -r requirements.txt

# Set the entrypoint
ENTRYPOINT ["python", "action.py"]
