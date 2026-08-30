FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY agents ./agents
COPY skills ./skills
COPY tools ./tools

RUN uv sync --frozen --extra serve --no-dev \
    && mkdir -p /data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

# Mount a host directory on /data so sessions and memory survive recreates.
CMD ["agentgw", "serve", "--agent", "/app/agents/demo", "--workspace", "/data", \
     "--host", "0.0.0.0", "--port", "8080"]
