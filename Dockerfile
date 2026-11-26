# syntax=docker/dockerfile:1
# Docker MCP Registry entry for ouba-studio/branching-story-mcp
# Zero third-party runtime dependencies: the server is pure-stdlib Python >= 3.10
# and speaks MCP over stdio (JSON-RPC 2.0), so no network access is needed at run time.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package from source (build isolation pulls setuptools/wheel from PyPI at build time only).
COPY pyproject.toml README.md LICENSE ./
COPY branching_story_mcp ./branching_story_mcp
RUN pip install --no-cache-dir .

# Run as an unprivileged user; the server is read-only and writes nothing to disk.
RUN useradd --create-home --uid 1000 mcp
USER mcp

# Console script -> branching_story_mcp.server:main (blocking stdio loop)
ENTRYPOINT ["branching-story-mcp"]
