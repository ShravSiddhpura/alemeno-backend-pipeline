FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv directly from compiled binaries
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /workspace

# Copy configuration descriptors first to exploit Docker layer caching
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 8000