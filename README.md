# agentgw

A local Python AI agent framework with extendable capabilities, dynamically defined through YAML-based SKILLs and Python tool functions. Agents can be orchestrated to manage multi-step tasks, with persistent memory, RAG-based knowledge retrieval, and multiple interfaces.

## Features

- **YAML-defined SKILLs** — Define agent behaviors, tool access, and prompts in simple YAML files
- **@tool decorator** — Write Python functions, auto-generate OpenAI-compatible schemas from type hints
- **ReAct agent loop** — Streaming LLM responses with automatic tool calling and iteration guards
- **Planner agent** — LLM-based intent routing that selects the best skill for a given task
- **Conversation memory** — SQLite-backed session persistence with full history recall and session resume
- **RAG knowledge base** — ChromaDB vector storage with tag-based filtering and auto-injection into agent context
- **User feedback** — Rate responses (+1/-1) to build a feedback dataset per agent
- **Web UI** — FastAPI + htmx with real-time SSE streaming, dark theme
- **CLI** — Full-featured command-line interface for chat, ingestion, and management
- **REST API** — JSON endpoints for programmatic access
- **LLM abstraction** — Provider protocol supports swapping between OpenAI, Anthropic, xAI

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

```bash
# Ingest a document with tags
agentgw ingest ./docs/api-reference.md --tags api --tags reference

# Ingest into a specific collection
agentgw ingest ./notes.txt --collection project-x --tags notes
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
- Document ingestion with tagging
- Session resume from the home page
- Feedback buttons on responses

### REST API

All web UI functionality is available via JSON endpoints:

```
POST /api/chat          — SSE streaming chat (send message, receive chunks)
POST /api/route         — Planner agent (classify intent, recommend skill)
POST /api/ingest        — Add text to RAG knowledge base
POST /api/feedback      — Submit +1/-1 feedback on a response
GET  /api/skills        — List available skills
GET  /api/sessions      — List recent sessions
GET  /api/sessions/{id}/messages — Get messages for a session
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

temperature: 0.5
tags:
  - my-tag
  - another-tag

# Optional: auto-inject RAG results matching these tags
rag_context:
  enabled: true
  tags: ["my-tag"]
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
| `model` | global config | Override the LLM model |
| `temperature` | `0.7` | LLM temperature |
| `max_iterations` | `10` | Agent loop guard |
| `tags` | `[]` | For RAG filtering and planner routing |
| `examples` | `[]` | Few-shot examples injected into context |
| `sub_agents` | `[]` | Skills this agent can delegate to (future) |
| `rag_context` | `null` | Auto-inject RAG results into system prompt |

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
│   └── summarize_document.yaml
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
├── tests/                           # 42 tests
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
| v0 | Done | Agent loop, tools, SKILLs, CLI, SQLite, ChromaDB, OpenAI |
| v0.5 | Done | Session resume, feedback, few-shot examples, RAG auto-inject, history |
| v1 | Done | Web UI, planner agent, SSE streaming, REST API, shared service layer |
| v1.5 | Planned | Sub-agent orchestration, `delegate_to_agent` meta-tool |
| v2 | Planned | APScheduler cron, Anthropic + xAI providers |
| v2.5 | Planned | Agent-generated new SKILLs from description |
| v3 | Planned | Full REST API, webhook support |

## License

Private — all rights reserved.
