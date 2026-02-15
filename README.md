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
POST   /api/chat          — SSE streaming chat (send message, receive chunks)
POST   /api/route         — Planner agent (classify intent, recommend skill)
POST   /api/ingest        — Add text to RAG knowledge base
GET    /api/documents     — List ingested documents (filter by skills/source)
DELETE /api/documents     — Delete documents by source or IDs
POST   /api/feedback      — Submit +1/-1 feedback on a response
GET    /api/skills        — List available skills
GET    /api/sessions      — List recent sessions
GET    /api/sessions/{id}/messages — Get messages for a session
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
