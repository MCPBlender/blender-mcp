# syntax=docker/dockerfile:1

# Build stage: install runtime dependencies at the versions pinned in uv.lock, so
# the runtime dependency set does not drift between builds of the same tag. Plain
# `pip install .` would re-resolve at build time instead.
#
# Note: this pins runtime dependencies, not the whole build. The PEP 517 build
# requirements in pyproject.toml (setuptools, wheel) are not covered by uv.lock and
# are still resolved at build time, so images are not bit-for-bit reproducible.
#
# The digest below is ghcr.io/astral-sh/uv:0.5-python3.11-bookworm-slim. It must stay
# on the same Python minor version and Debian release as the runtime stage, because
# the virtual environment built here is executed there.
FROM ghcr.io/astral-sh/uv@sha256:9398ea109260fafedc26fecccfe26e5f511ad4fbc7a69235b7166c0315d526ba AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

# --frozen: install exactly what uv.lock pins, without re-resolving. (Not --locked:
# uv.lock records the project version as 1.8.1 while pyproject.toml is at 1.8.3, so
# --locked fails. The dependency set itself is identical, and relocking is a separate
# concern from this change.)
# --no-dev: production deps only. --no-editable: install a real copy so the runtime
# stage does not need ./src.
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage: base pinned by digest so the image does not drift underneath a tag.
FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

# PYTHONUNBUFFERED is required, not cosmetic: the MCP stdio transport stalls if
# stdout is block-buffered.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    BLENDER_HOST=host.docker.internal \
    BLENDER_PORT=9876

RUN useradd -m -u 1000 mcp

COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv
# Ship the license with the redistributed image.
COPY --from=builder /app/LICENSE /app/LICENSE

USER mcp

ENTRYPOINT ["blender-mcp"]
