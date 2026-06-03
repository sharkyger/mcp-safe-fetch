"""Allow ``python -m mcp_safe_fetch`` to run the MCP server.

The ``mcp-safe-fetch`` console script entry (see pyproject.toml's
``[project.scripts]``) and this ``-m`` module entry are equivalent.
The Dockerfile uses the ``-m`` path so it doesn't depend on the
console script being on PATH.
"""

from .server import run

if __name__ == "__main__":
    raise SystemExit(run())
