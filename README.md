# agentgw

A local Python AI agent framework with extendable capabilities, dynamically defined through YAML-based SKILLs and Python tool functions. Agents can be orchestrated to manage multi-step tasks, with persistent memory, RAG-based knowledge retrieval, and multiple interfaces.

## Features

- **YAML-defined SKILLs** — Define agent behaviors, tool access, and prompts in simple YAML files
- **@tool decorator** — Write Python functions, auto-generate OpenAI-compatible schemas from type hints
- **ReAct agent loop** — Streaming LLM responses with automatic tool calling and iteration guards
- **Planner agent** — LLM-based intent routing that selects the best skill for a given task
- **Sub-agent orchestration** — Skills can delegate tasks to other specialized skills with depth tracking
- **Conversation memory** — SQLite-backed session persistence with full history recall and session resume
- **RAG knowledge base** — ChromaDB vector storage with skill-based filtering and auto-injection into agent context
- **Document management** — View, search, and delete ingested documents via CLI, Web UI, or API
- **Per-skill models** — Each skill can specify its own LLM model (e.g., gpt-4o, claude-3-5-sonnet, grok-beta)
- **User feedback** — Rate responses (+1/-1) to build a feedback dataset per agent
- **Cron scheduling** — APScheduler-based task automation with configurable jobs
- **Webhook support** — HTTP notifications for agent events (started, completed, tool executed, etc.)
- **Web UI** — FastAPI + htmx with real-time SSE streaming, dark theme
- **CLI** — Full-featured command-line interface for chat, ingestion, scheduling, and management
- **REST API** — JSON endpoints with OpenAPI/Swagger docs at `/docs`
- **API Authentication** — Optional API key authentication for production deployments
- **Health checks** — `/health` endpoint for monitoring and load balancers
- **Graceful shutdown** — Proper cleanup of resources on termination
- **Multi-provider LLM** — OpenAI, Anthropic (Claude), and xAI (Grok) support with unified interface
- **Production-ready** — Docker, systemd, and deployment guides included

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd agentgw
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Verify
agentgw skills
agentgw --version
```

## Usage

### CLI

```bash
# Interactive chat with a skill
agentgw chat -s general_assistant

# Resume a previous session
agentgw chat -s general_assistant --session <session-id>

# Single-shot execution
agentgw run -s summarize_document "Summarize the key points of this text: ..."

# Override the LLM model
agentgw chat -s general_assistant --model gpt-4o-mini
```

### Chat Commands

During an interactive chat session:

| Command | Description |
|---------|-------------|
| `+1` / `-1` | Rate the last agent response |
| `/history` | Show conversation history for the current session |
| `exit` / `quit` | End the session |

### RAG Ingestion

Documents can be associated with specific skills (or left available to all):

```bash
# Ingest for specific skills only
agentgw ingest ./python-guide.md --skills code_assistant --skills general_assistant

# Ingest available to all skills (default)
agentgw ingest ./company-policies.md

# Combine skill filtering with tags
agentgw ingest ./api-reference.md --skills code_assistant --tags api --tags reference

# Ingest into a specific collection
agentgw ingest ./notes.txt --collection project-x --tags notes
```

**How skill filtering works:**
- Documents with `--skills` are only accessible to those specific skills
- Documents without `--skills` are available to **all** agents
- Tags provide additional categorization within a skill's scope

### Document Management

View and manage ingested documents:

```bash
# List all documents
agentgw documents

# Filter by skill
agentgw documents --skills code_assistant

# Filter by source name
agentgw documents --source python-guide

# Limit results
agentgw documents --limit 50

# Delete all chunks from a source
agentgw delete-documents --source python-guide.md

# Delete specific document by ID
agentgw delete-documents --id abc-123-def --id xyz-789-ghi

# Specify collection
agentgw documents --collection my-collection
```

### Session Management

```bash
# List recent sessions
agentgw sessions

# Filter by skill
agentgw sessions --skill general_assistant

# View full conversation history
agentgw history <session-id>
```

### Scheduled Jobs (Cron)

Schedule agent tasks to run automatically using cron expressions:

```bash
# Start the scheduler (reads config/scheduled_jobs.yaml)
agentgw scheduler --start

# List configured jobs
agentgw scheduler --list

# Use custom config file
agentgw scheduler --start --config my-jobs.yaml
```

**Example `config/scheduled_jobs.yaml`:**

```yaml
jobs:
  - name: daily_summary
    skill_name: general_assistant
    message: "Provide a brief summary of today's date"
    cron_expression: "0 9 * * *"  # Every day at 9 AM
    enabled: true
    log_output: true  # Write results to data/logs/

  - name: hourly_check
    skill_name: quick_assistant
    message: "Quick status check"
    cron_expression: "0 * * * *"  # Every hour
    enabled: true
```

**Cron expression format:** `minute hour day month day_of_week`

Examples:
- `*/5 * * * *` — Every 5 minutes
- `0 */2 * * *` — Every 2 hours
- `30 9 * * 1-5` — 9:30 AM on weekdays
- `0 0 1 * *` — Midnight on 1st of each month

### Webhooks

Receive HTTP notifications for agent events:

```bash
# List configured webhooks
agentgw webhooks --list

# Webhooks are auto-loaded from config/webhooks.yaml
```

**Example `config/webhooks.yaml`:**

```yaml
webhooks:
  - name: logger_webhook
    url: http://localhost:8080/webhook/agent-events
    events:
      - agent.started
      - agent.completed
      - agent.failed
      - tool.executed
    secret: your-webhook-secret
    enabled: true
```

**Available webhook events:**
- `agent.started` — Agent begins processing
- `agent.completed` — Agent finishes successfully
- `agent.failed` — Agent encounters error
- `tool.executed` — Tool function called
- `session.created` — New session created
- `feedback.received` — User feedback submitted

**Webhook payload format:**

```json
{
  "event": "agent.completed",
  "timestamp": "2024-01-15T10:30:00",
  "data": {
    "session_id": "abc123",
    "skill_name": "general_assistant",
    "result": "Response text..."
  }
}
```

Webhooks include:
- Automatic retries with exponential backoff (max 3 attempts)
- Secret authentication via `X-Webhook-Secret` header
- Fire-and-forget delivery (non-blocking)
- 30-second timeout per request

### Web UI

```bash
# Launch the web interface (default: http://127.0.0.1:8080)
agentgw web

# Custom host/port
agentgw web --host 0.0.0.0 --port 3000
```

The web UI provides:
- Skill selection with descriptions and tags
- Smart Router — describe a task and the planner picks the best skill
- Real-time streaming chat with session persistence
- Document ingestion with per-skill filtering and tagging
- Document browser with search, filtering, and deletion
- Session resume from the home page
- Feedback buttons on responses

### REST API

All web UI functionality is available via JSON endpoints:

```
# Core functionality
POST   /api/chat                    — SSE streaming chat
POST   /api/route                   — Planner agent routing
POST   /api/feedback                — Submit +1/-1 feedback

# Knowledge base
POST   /api/ingest                  — Add text to RAG
GET    /api/documents               — List documents (filter by skills/source)
DELETE /api/documents               — Delete by source or IDs

# Skills & sessions
GET    /api/skills                  — List available skills
GET    /api/sessions                — List recent sessions
GET    /api/sessions/{id}/messages  — Get session messages

# Configuration & monitoring (v3)
GET    /api/config                  — Current configuration
GET    /api/tools                   — List registered tools
POST   /api/tools/{name}/execute    — Execute tool directly
GET    /api/stats                   — Usage statistics
```

## Creating Skills

Skills are YAML files in the `skills/` directory:

```yaml
name: my_skill
description: >
  A short description used by the planner for routing.

system_prompt: |
  You are a specialized assistant. Instructions for the agent go here.

tools:
  - read_file
  - search_documents
  - list_files

model: gpt-4o  # Optional: override default model for this skill
temperature: 0.5
tags:
  - my-tag
  - another-tag

# Optional: auto-inject RAG results for this skill
rag_context:
  enabled: true
  skills: ["my_skill"]  # Defaults to [current skill name]
  tags: ["my-tag"]      # Additional tag filtering
  top_k: 3

# Optional: few-shot examples
examples:
  - user: "Example user message"
    assistant: "Example agent response"
```

### Required Fields

| Field | Description |
|-------|-------------|
| `name` | Unique identifier |
| `description` | Used by the planner for skill selection |
| `system_prompt` | The agent's system prompt |

### Optional Fields

| Field | Default | Description |
|-------|---------|-------------|
| `tools` | `[]` | Tool names this skill can use |
| `model` | global config | Override LLM model (e.g., `gpt-4o`, `gpt-4o-mini`) |
| `temperature` | `0.7` | LLM temperature (0.0-2.0) |
| `max_iterations` | `10` | Agent loop guard |
| `tags` | `[]` | For RAG filtering and planner routing |
| `examples` | `[]` | Few-shot examples injected into context |
| `sub_agents` | `[]` | Skills this agent can delegate to |
| `rag_context` | `null` | Auto-inject RAG results into system prompt |

**Model Selection Hierarchy:**
1. CLI override: `--model gpt-4o`
2. Skill-specific: `model: gpt-4o` in YAML
3. Global default: `config/settings.yaml`

See `examples/per_skill_models.md` for detailed guidance on choosing models.

### RAG Context Auto-Injection

When `rag_context.enabled` is true, the agent automatically searches the knowledge base before each turn and injects relevant results into its context:

```yaml
rag_context:
  enabled: true
  skills: ["my_skill"]     # Filter by skill (defaults to current skill)
  tags: ["documentation"]  # Additional tag filtering
  top_k: 3                 # Number of chunks to inject
```

**Skill-based filtering:**
- By default, searches only documents associated with the current skill
- Documents ingested with `--skills my_skill` are only available to that skill
- Documents ingested without `--skills` are available to **all** skills
- Override with explicit `skills: []` to search across all documents

### Sub-Agent Orchestration

Skills can delegate tasks to other specialized skills using the `delegate_to_agent` tool:

```yaml
name: project_manager
description: Coordinates complex multi-step projects
system_prompt: |
  You orchestrate tasks by delegating to specialized agents.
  Break down complex requests and delegate subtasks.

tools:
  - delegate_to_agent

sub_agents:
  - general_assistant
  - code_assistant
```

**How it works:**
- One skill delegates a task to another skill
- Each delegation increments orchestration depth
- Max depth prevents infinite recursion (default: 3)
- Results are returned and integrated by the orchestrator

**Example:**
```python
# In the orchestrator skill's execution
result = delegate_to_agent(
    skill_name="code_assistant",
    task="Write a Python function to validate emails",
    context="Use regex and handle edge cases"
)
```

See `examples/sub_agent_orchestration.md` for detailed guide.

## Configuration

### LLM Providers

agentgw supports multiple LLM providers. Configure via `config/settings.yaml` or environment variables:

**OpenAI (default):**
```yaml
llm:
  provider: openai
  model: gpt-4o-mini
```

Set `OPENAI_API_KEY` in `.env` or environment.

**Anthropic (Claude):**
```yaml
llm:
  provider: anthropic
  model: claude-3-5-sonnet-20241022
```

Set `ANTHROPIC_API_KEY` in `.env` or environment.

**xAI (Grok):**
```yaml
llm:
  provider: xai
  model: grok-beta
```

Set `XAI_API_KEY` in `.env` or environment.

**Per-skill model override:**
```yaml
# In skills/code_assistant.yaml
model: gpt-4o  # Use powerful model for coding

# In skills/quick_assistant.yaml
model: gpt-4o-mini  # Use fast, cheap model for simple tasks
```

**Model hierarchy:** CLI flag `--model` > skill YAML `model` > global config `llm.model`

### Environment Variables

```bash
# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
XAI_API_KEY=xai-...

# API Authentication (recommended for production)
AGENTGW_API_KEY=your-secure-key-here

# Override config (optional)
AGENTGW_LLM__PROVIDER=anthropic
AGENTGW_LLM__MODEL=claude-3-5-sonnet-20241022
AGENTGW_AGENT__MAX_ITERATIONS=15
AGENTGW_AGENT__MAX_ORCHESTRATION_DEPTH=5
```

## Security

### API Key Authentication

Enable authentication by setting an API key:

```bash
# Generate a secure key
openssl rand -hex 32

# Add to .env
AGENTGW_API_KEY=your-generated-key-here
```

Clients must include the API key in requests:

```bash
curl -H "Authorization: Bearer your-api-key" \
     http://localhost:8080/api/skills
```

**Public endpoints** (no auth required):
- `GET /` — Home page
- `GET /health` — Health check
- `GET /docs` — API documentation
- `GET /static/*` — Static assets

**Protected endpoints**: All `/api/*` routes require authentication when `AGENTGW_API_KEY` is set.

### Production Deployment

For production use, see [DEPLOYMENT.md](DEPLOYMENT.md) which covers:

- Docker deployment with docker-compose
- Systemd service configuration
- Nginx reverse proxy with SSL/TLS
- Security hardening and best practices
- Monitoring and health checks
- Backup and recovery procedures
- Kubernetes deployment examples

**Quick production checklist:**

✅ Set `AGENTGW_API_KEY` for authentication
✅ Use HTTPS with valid SSL certificate
✅ Enable firewall rules (only 80/443 exposed)
✅ Restrict file permissions (chmod 600 .env)
✅ Configure automatic backups
✅ Set up health check monitoring
✅ Use secrets manager for API keys

## Creating Tools

Tools are Python functions decorated with `@tool`:

```python
from agentgw.tools.decorator import tool

@tool()
async def my_tool(query: str, limit: int = 10) -> list[dict]:
    """Search for something useful.

    Args:
        query: What to search for.
        limit: Maximum results to return.
    """
    # Your implementation here
    return [{"result": "data"}]
```

The decorator automatically:
- Generates an OpenAI-compatible JSON schema from type hints
- Parses parameter descriptions from Google-style docstrings
- Registers the tool in the global registry
- Supports both sync and async functions

### Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with line limit |
| `list_files` | List files matching a glob pattern |
| `search_documents` | Search the RAG knowledge base |
| `ingest_document` | Add text to the knowledge base |
| `query_db` | Execute read-only SQL queries |
| `delegate_to_agent` | Delegate a task to another specialized skill |

## Configuration

### settings.yaml

```yaml
llm:
  provider: openai        # LLM provider
  model: gpt-4o           # Default model
  temperature: 0.7
  max_tokens: 4096

agent:
  max_iterations: 10      # Per agent loop
  max_orchestration_depth: 3  # Sub-agent recursion limit

storage:
  sqlite_path: data/agentgw.db
  chroma_path: data/chroma
  log_dir: data/logs

skills_dir: skills
tools_modules:
  - agentgw.tools         # Add your own tool modules here
```

### Environment Variables

Settings can be overridden with `AGENTGW_` prefixed environment variables:

```bash
OPENAI_API_KEY=sk-...              # Required
AGENTGW_LLM__MODEL=gpt-4o-mini    # Override default model
```

## Architecture

```
CLI / Web UI / REST API
        |
   AgentService          ← Shared service layer
        |
   PlannerAgent           ← Routes intent to skill
        |
    AgentLoop             ← ReAct: LLM → tool exec → repeat
     /       \
ToolRegistry  SkillLoader
     |
 Services: ChromaDB (RAG) | SQLite (memory) | LLM Provider
```

### Data Flow

1. User sends a message via CLI, Web UI, or API
2. (Optional) Planner agent classifies intent and selects a skill
3. AgentLoop builds messages: system prompt + RAG context + few-shot examples + history
4. LLM streams a response; if it includes tool calls, tools are executed and results fed back
5. Loop continues until the LLM returns text (no tool calls) or max iterations reached
6. Messages and feedback are persisted to SQLite

## Project Structure

```
agentgw/
├── config/settings.yaml
├── skills/                          # YAML skill definitions
│   ├── general_assistant.yaml
│   ├── summarize_document.yaml
│   └── project_manager.yaml         # Orchestrator example
├── src/agentgw/
│   ├── core/
│   │   ├── agent.py                 # ReAct agent loop
│   │   ├── config.py                # Pydantic Settings
│   │   ├── planner.py               # Intent routing
│   │   ├── service.py               # Shared service layer
│   │   ├── session.py               # Session state
│   │   ├── skill_loader.py          # YAML loading + validation
│   │   └── tool_registry.py         # @tool discovery + execution
│   ├── llm/
│   │   ├── base.py                  # LLMProvider Protocol
│   │   ├── openai_provider.py       # OpenAI streaming + tool calls
│   │   └── types.py                 # Message, ToolCall, StreamChunk
│   ├── tools/                       # Built-in @tool functions
│   ├── memory/                      # SQLite conversation + feedback
│   ├── rag/                         # ChromaDB + text chunking
│   ├── db/                          # SQLite connection manager
│   └── interfaces/
│       ├── cli.py                   # Click CLI
│       └── web/                     # FastAPI + htmx + SSE
├── tests/                           # 73 tests
└── data/                            # Runtime (gitignored)
```

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run with verbose logging
AGENTGW_LOG_LEVEL=DEBUG agentgw chat -s general_assistant
```

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| v0 | ✅ Done | Agent loop, tools, SKILLs, CLI, SQLite, ChromaDB, OpenAI |
| v0.5 | ✅ Done | Session resume, feedback, few-shot examples, RAG auto-inject, history |
| v1 | ✅ Done | Web UI, planner agent, SSE streaming, REST API, shared service layer |
| v1+ | ✅ Done | Skill-based RAG filtering, document management |
| v1.5 | ✅ Done | Sub-agent orchestration, `delegate_to_agent` meta-tool, depth tracking |
| v2 | Planned | APScheduler cron, Anthropic + xAI providers |
| v2.5 | Planned | Agent-generated new SKILLs from description |
| v3 | Planned | Full REST API expansion, webhook support |

## License

Private — all rights reserved.
