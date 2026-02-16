# agentgw v4 — Daemon Architecture

## Overview

agentgw has been transformed from separate CLI/web processes into a **long-running autonomous agent framework** with a persistent daemon/server and multiple client interfaces.

## What Changed

### Before (v0-v3)
```bash
# Separate processes for each interface
agentgw chat -s general_assistant          # Process 1: creates new service
agentgw web --port 8080                    # Process 2: foreground web server
agentgw scheduler --start                  # Process 3: separate scheduler
```

**Problems:**
- CLI creates new `AgentService` per command (no persistence)
- Web runs as foreground server (can't use CLI simultaneously)
- Scheduler is separate process (can't integrate with CLI/web)
- No way to connect multiple interfaces to same running service

### After (v4)
```bash
# Single daemon process
agentgw serve --port 8080
# ^ Runs web UI + scheduler + API in ONE long-running process

# Connect via CLI (in another terminal)
agentgw chat -s general_assistant
# ^ Now sends HTTP requests to daemon

# Or open browser
open http://localhost:8080

# Or use REST API
curl http://localhost:8080/api/skills
```

**Benefits:**
✅ **No more restarts** - Switch between CLI/web/API without stopping service
✅ **Long-running** - Daemon runs for weeks/months
✅ **Integrated scheduler** - Background jobs run automatically
✅ **Remote access** - CLI can connect to remote daemon via `AGENTGW_URL`
✅ **Better resource usage** - Single process vs multiple processes

---

## New Components

### 1. Daemon Server (`agentgw serve`)

**File:** `src/agentgw/interfaces/server.py`

The `DaemonServer` class combines FastAPI + Scheduler into a single long-running process:

```python
class DaemonServer:
    """Main daemon server combining FastAPI + Scheduler."""

    async def start(self, host: str = "127.0.0.1", port: int = 8080,
                    enable_scheduler: bool = True,
                    scheduler_config: Path | None = None):
        """Start daemon with FastAPI + optional scheduler."""
        # Initialize service
        await self._service.initialize()

        # Start scheduler if enabled
        if enable_scheduler:
            self._scheduler = await self._start_scheduler(scheduler_config)

        # Create FastAPI app (reuses existing web app)
        app = self._create_app()

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Start uvicorn server
        await server.serve()
```

**Usage:**
```bash
# Start daemon with scheduler
agentgw serve

# Start on all interfaces
agentgw serve --host 0.0.0.0 --port 8080

# Disable scheduler
agentgw serve --no-scheduler

# Custom scheduler config
agentgw serve --scheduler-config my_jobs.yaml

# Background daemon with PID file
agentgw serve --pidfile /var/run/agentgw.pid &
```

### 2. HTTP Client (`AgentGWClient`)

**File:** `src/agentgw/interfaces/cli_client.py`

HTTP client for connecting CLI commands to the daemon:

```python
class AgentGWClient:
    """HTTP client for agentgw daemon."""

    async def chat(self, skill_name: str, message: str,
                   session_id: str | None = None) -> AsyncIterator[str]:
        """Stream chat response via SSE."""

    async def run(self, skill_name: str, message: str) -> str:
        """Single-shot execution."""

    async def list_skills(self) -> list[dict]:
        """List available skills."""

    async def ingest(self, text: str, source: str, ...) -> dict:
        """Ingest document."""

    # ... more API methods
```

**Configuration:**
```bash
# Point CLI to daemon
export AGENTGW_URL=http://127.0.0.1:8080
export AGENTGW_API_KEY=your-api-key

# CLI commands now connect via HTTP
agentgw chat -s general_assistant
agentgw skills
agentgw ingest file.txt --tags docs
```

### 3. New API Endpoints

**Added `/api/run`** for non-streaming execution:
```bash
curl -X POST http://localhost:8080/api/run \
     -H "Content-Type: application/json" \
     -d '{"skill_name": "general_assistant", "message": "Hello"}'
```

**Added `/daemon/status`** for daemon monitoring:
```bash
curl http://localhost:8080/daemon/status

# Response:
{
  "status": "running",
  "scheduler": {
    "enabled": true,
    "jobs_count": 2,
    "jobs": [
      {"name": "daily_summary", "skill": "general_assistant", ...}
    ]
  },
  "service": {
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini"
  }
}
```

---

## Deployment

### Docker

**Dockerfile:**
```dockerfile
CMD ["agentgw", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

**docker-compose.yml:**
```yaml
services:
  agentgw:
    build: .
    ports:
      - "8080:8080"
    command: ["agentgw", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

**Usage:**
```bash
docker-compose up -d
```

### Systemd

**File:** `deployment/agentgw.service`

```ini
[Unit]
Description=agentgw Autonomous Agent Framework
After=network.target

[Service]
Type=simple
User=agentgw
ExecStart=/opt/agentgw/.venv/bin/agentgw serve --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Usage:**
```bash
sudo systemctl start agentgw
sudo systemctl enable agentgw
sudo systemctl status agentgw
```

---

## Files Changed

### New Files
- `src/agentgw/interfaces/server.py` - DaemonServer class
- `src/agentgw/interfaces/cli_client.py` - HTTP client
- `Dockerfile` - Docker build configuration
- `docker-compose.yml` - Docker Compose configuration
- `deployment/agentgw.service` - Systemd service file

### Modified Files
- `src/agentgw/interfaces/cli.py` - Added `serve` command
- `src/agentgw/interfaces/web/app.py` - Added `/api/run` endpoint
- `pyproject.toml` - Added `httpx>=0.27` dependency

### Unchanged
- All core components work as-is (AgentService, AgentLoop, etc.)
- All web UI templates (no changes needed)
- All existing API endpoints (fully compatible)

---

## Quick Start

### 1. Install Dependencies
```bash
pip install -e .
```

### 2. Start Daemon
```bash
# Terminal 1: Start daemon
agentgw serve

# Output:
# INFO:     Initializing agentgw service...
# INFO:     Scheduler started with 2 enabled jobs
# INFO:     Uvicorn running on http://127.0.0.1:8080
```

### 3. Use CLI (in another terminal)
```bash
# Terminal 2: Use CLI
agentgw skills
agentgw chat -s general_assistant
agentgw run -s summarize_document "Summarize this text"
```

### 4. Use Web UI
```bash
open http://localhost:8080
```

---

## Migration Guide

### Existing `agentgw web` Users

The old `agentgw web` command still works but shows a deprecation warning:

```bash
agentgw web --port 8080
# ⚠️  WARNING: 'agentgw web' is deprecated. Use 'agentgw serve' for daemon mode.
```

**Recommended migration:**
```bash
# Before
agentgw web --port 8080

# After
agentgw serve --port 8080
```

### Existing Scheduler Users

The scheduler is now integrated into the daemon:

```bash
# Before (separate process)
agentgw scheduler --start

# After (integrated into daemon)
agentgw serve  # Scheduler runs automatically
```

---

## Testing

### Verify Daemon Startup
```bash
agentgw serve --no-scheduler --port 8888

# Expected output:
# ✓ Service initialized successfully
# ✓ LLM provider: openai
# ✓ Skills loaded: 5
# ✓ Tools registered: 6
# ✓ Uvicorn running on http://127.0.0.1:8888
```

### Test API Endpoints
```bash
# Health check
curl http://localhost:8080/health

# Daemon status
curl http://localhost:8080/daemon/status

# List skills
curl http://localhost:8080/api/skills

# Run agent
curl -X POST http://localhost:8080/api/run \
     -H "Content-Type: application/json" \
     -d '{"skill_name": "general_assistant", "message": "Hello"}'
```

### Test Long-Running Stability
```bash
# Start daemon in background
agentgw serve &

# Use CLI immediately
agentgw chat -s general_assistant

# Wait 1 hour
sleep 3600

# CLI still works
agentgw skills
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                          │
│  agentgw CLI  │  Web Browser  │  HTTP/REST Clients      │
│  (HTTP client)│  (htmx UI)    │  (curl, Python SDK)     │
└───────┬───────────────┬───────────────┬─────────────────┘
        │               │               │
        │ HTTP          │ HTTP/SSE      │ HTTP/REST
        │               │               │
┌───────▼───────────────▼───────────────▼─────────────────┐
│              AGENTGW DAEMON (server)                     │
│  ┌────────────────────────────────────────────────┐     │
│  │         FastAPI (HTTP Server)                  │     │
│  ├────────────────────────────────────────────────┤     │
│  │              AgentService (singleton)          │     │
│  │  - SkillLoader    - MemoryStore                │     │
│  │  - ToolRegistry   - RAGStore                   │     │
│  │  - LLM Provider   - WebhookDelivery            │     │
│  ├────────────────────────────────────────────────┤     │
│  │        APScheduler (CronScheduler)             │     │
│  │        - Runs background jobs continuously     │     │
│  └────────────────────────────────────────────────┘     │
│                                                           │
│  Persistence: SQLite (conversations) + ChromaDB (RAG)    │
└───────────────────────────────────────────────────────────┘
```

---

## Future Work (Optional)

The following features are **optional** enhancements for v4.1+:

### Phase 2: Full CLI Client Conversion (Optional)

Convert ALL CLI commands to use HTTP client by default:

```python
# In cli.py, make HTTP client the default
def _get_client() -> AgentGWClient:
    base_url = os.environ.get("AGENTGW_URL", "http://127.0.0.1:8080")
    return AgentGWClient(base_url=base_url)

# Update all commands to use client
@cli.command("skills")
def list_skills():
    async def _list():
        client = _get_client()
        skills = await client.list_skills()
        # ...
    asyncio.run(_list())
```

This would enable:
- Remote CLI usage (connect to daemon on another machine)
- Better resource isolation (daemon handles all heavy lifting)
- Consistent behavior across all interfaces

---

## Summary

✅ **Daemon architecture implemented** - Single long-running process
✅ **CLI client created** - Can connect to daemon via HTTP
✅ **Scheduler integrated** - Runs automatically in daemon
✅ **Docker support** - Dockerfile and docker-compose.yml
✅ **Systemd support** - Service file for Linux deployments
✅ **Backward compatible** - Old commands still work with deprecation warnings

The v4 daemon architecture makes agentgw a true **autonomous agent framework** that can run continuously for weeks or months, with multiple interfaces connecting and disconnecting as needed.
