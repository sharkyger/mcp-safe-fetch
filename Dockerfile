# mcp-safe-fetch image — runs the MCP server on stdio.
#
# Claude Desktop spawns this image as a child process via
# ``docker run --rm -i ghcr.io/sharkyger/mcp-safe-fetch:<tag>`` and
# communicates via stdin/stdout. The image carries the Python runtime,
# the MCP SDK, beautifulsoup4 + lxml (for the sanitizer), and the
# mcp_safe_fetch package itself. Runs as non-root by default; the host
# config should also pass ``--network=bridge --cap-drop=ALL --read-only``
# for full hardening (documented in README).

FROM python:3.14-slim@sha256:d7a925f9eb9639a93e455b9f12c167569358818c0f62b51b88edbc8fcf34c421

# lxml needs libxml2/libxslt at runtime. apt-get is cleared after install
# so the resulting image carries no package manager artifacts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build context is the repo root. The package and its exact-pinned deps
# install from pyproject.toml — the single pin source Dependabot's pip
# ecosystem watches — so the image can never drift from the manifest
# (pin rationale lives next to the pins in pyproject.toml).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as a non-root user. The host should additionally pass
# --user nobody / --cap-drop=ALL / --read-only at run time, but baking
# the user in here is belt-and-braces.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin fetcher
USER fetcher

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-m", "mcp_safe_fetch"]
