# mcp-safe-fetch image — runs the MCP server on stdio.
#
# Claude Desktop spawns this image as a child process via
# ``docker run --rm -i ghcr.io/sharkyger/mcp-safe-fetch:<tag>`` and
# communicates via stdin/stdout. The image carries the Python runtime,
# the MCP SDK, beautifulsoup4 + lxml (for the sanitizer), and the
# mcp_safe_fetch package itself. Runs as non-root by default; the host
# config should also pass ``--network=bridge --cap-drop=ALL --read-only``
# for full hardening (documented in README).

FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

# lxml needs libxml2/libxslt at runtime. apt-get is cleared after install
# so the resulting image carries no package manager artifacts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
 && rm -rf /var/lib/apt/lists/* \
 # Exact-pin must stay in lockstep with pyproject.toml so the host
 # and in-container installs resolve to byte-identical parsed-tree
 # behavior. lxml 6.1.1 closes PYSEC-2026-87 (5.x has no back-port).
 # mcp 1.27.1 is the past-freshness-hold admissible pin (2026-05-31).
 && pip install --no-cache-dir 'mcp==1.27.1' 'beautifulsoup4==4.14.3' 'lxml==6.1.1'

WORKDIR /app

# Build context is the repo root.
COPY src/mcp_safe_fetch /app/mcp_safe_fetch

# Run as a non-root user. The host should additionally pass
# --user nobody / --cap-drop=ALL / --read-only at run time, but baking
# the user in here is belt-and-braces.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin fetcher
USER fetcher

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-m", "mcp_safe_fetch"]
