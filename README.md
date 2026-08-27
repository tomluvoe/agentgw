# agentgw

An **agent harness**: the loop, skill loading, and tool management. Agent identity, skills, and extra tools live *outside* the harness and are included by config.

```text
clone → add an agent (AGENT.md) → point it at skills and tools → run
```

## What this is

| Layer | Role | Where it lives |
|---|---|---|
| **Harness** | ReAct loop, skill catalog/activation, tool registry, workspace jail, LLM adapter | `src/agentgw/` |
| **Agent** | Name, system prompt, model, tool policy, which skills/tools to include | `agents/<name>/AGENT.md` |
| **Skills** | `SKILL.md` instruction packs ([Agent Skills](https://agentskills.io/specification)) | shared `skills/` (or any roots you list) |
| **Tools** | Typed functions the model can call | harness builtins + optional Python modules |

Skills are **not** agents. Skills are **not** tools. A skill teaches the model how to use tools it already has. A tool is a function with a schema. The agent is a prompt plus a policy that *includes* skills and tools.

RAG, a web UI, cron, and channel bots are out of this repo’s core. Channels (CLI first, later REST / Discord / Telegram) should call `Harness.run()` and nothing else.

## Quick start

```bash
git clone git@github.com:tomluvoe/agentgw.git
cd agentgw
uv sync --group dev
cp .env.example .env   # add an API key

uv run agentgw skills --agent ./agents/demo
uv run agentgw run --agent ./agents/demo "hello"
uv run agentgw chat --agent ./agents/demo

# Long-running daemon + REST clients
uv sync --extra serve --group dev
uv run agentgw serve --agent ./agents/demo --port 8080
# another terminal:
export AGENTGW_URL=http://127.0.0.1:8080
uv run agentgw chat
```

Tests:

```bash
uv run pytest
uv run pytest -m harness   # end-to-end: AGENT.md → skills → tools → loop
```

CI runs both: unit tests, then a dedicated **Harness** job (`pytest -m harness`).

## Agent package

An agent is a directory with `AGENT.md`. Skills and tools are **referenced**, not copied.

```text
agents/demo/
└── AGENT.md          # identity + includes

skills/               # shared packs, reused by any agent
  greet/SKILL.md
  workspace-notes/SKILL.md

tools/                # shared extra Python tools
  echo.py
```

`AGENT.md`:

```markdown
---
name: demo
description: Example agent that includes shared skills and tools by path.
provider: openai
model: gpt-4o-mini
skills:
  roots:
    - ../../skills          # shared
    # - skills              # optional agent-local packs
  allow: []                 # empty = all eligible skills in those roots
  max_activated: 3
tools:
  allow: [read, write, list_dir, exec, echo]
  modules:
    - ../../tools           # shared
    # - tools               # optional agent-local modules
---

You are a local demo assistant. Prefer matching skills when they apply.
Stay inside the workspace. Be concise.
```

**Why not keep skills only under the agent?** Two agents would duplicate the same packs. Roots in `AGENT.md` are the sharing mechanism. An agent-local `skills/` or `tools/` directory is still useful for private or overriding packs — list it in `roots` / `modules` when you want it. Later roots win on name conflicts.

## Skills

Each skill is a folder with `SKILL.md`: YAML frontmatter (`name`, `description`) plus Markdown instructions. Optional `scripts/`, `references/`, and `assets/` are read or executed only when the agent uses file/exec tools — they are not dumped into the prompt.

Progressive disclosure:

1. **Catalog (always)** — every eligible skill’s name, description, and path.
2. **Full body (this turn)** — skills that match the user message (explicit `$name` / `/name`, name mention, or keyword overlap with the description), capped by `max_activated`.
3. **Resources** — the model can `read` other files in a skill directory if it needs them.

A vanilla Agent Skills file with only `name` and `description` loads. If a pack also uses `{baseDir}` or nested `metadata` gating (`requires.bins` / `requires.env` / `os`), those are honored so existing [OpenClaw](https://docs.openclaw.ai/tools/skills) `SKILL.md` trees can be pointed at without rewriting.

## Tools

Harness builtins (always registered, still subject to the agent allow/deny list):

| Tool | Behavior |
|---|---|
| `read` | Read a file **inside the workspace** |
| `write` | Write a file inside the workspace |
| `list_dir` | List files inside the workspace |
| `exec` | Run a shell command with cwd = workspace |

Extra tools are ordinary Python:

```python
from agentgw.tools.decorator import tool

@tool()
def echo(text: str) -> str:
    """Return the given text unchanged."""
    return text
```

Point `tools.modules` at the directory. The model only sees tools in `tools.allow` minus `tools.deny`. Execute-time checks use the same list (naming a denied tool does nothing). `ctx` is injected if the function accepts it and is never part of the schema.

File tools cannot resolve paths outside the workspace. `exec` is cwd-jailed, not a container.

## Run loop

```text
load AGENT.md → resolve skill roots & tool modules
     → drop ineligible skills (missing bins/env)
     → select L2 skills from the user message
     → system prompt = agent body + catalog + active bodies
     → LLM stream → allowed tool calls → repeat until text or max_iterations
```

LLM providers: OpenAI, Anthropic, xAI. The harness talks to them through `create_llm()`; channels never import an SDK. Set keys in `.env`. Selection order: CLI `--provider` / `--model`, then `AGENT.md`, then `AGENTGW_LLM_PROVIDER` / `AGENTGW_LLM_MODEL`.

```bash
uv run agentgw chat --agent ./agents/demo
uv run agentgw run --agent ./agents/demo "take a note: ship uv"
uv run agentgw tools --agent ./agents/demo
```

`--workspace` changes the jail root for a run.

## Daemon (long-running process)

`agentgw serve` is the agent. It stays up, holds the loaded package, and exposes REST. Conversations are stored under `<workspace>/.agentgw/sessions/` so they survive a restart.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + agent name |
| GET | `/v1/skills` | eligible skills |
| GET | `/v1/tools` | allowed tools |
| GET | `/v1/sessions` | session ids on disk |
| POST | `/v1/chat` | `{ "message", "session_id"? }` → `{ "session_id", "response" }` |

```bash
uv sync --extra serve --group dev
uv run agentgw serve --agent ./agents/demo --host 127.0.0.1 --port 8080
```

Then attach from another process (CLI is an HTTP client, same as curl):

```bash
export AGENTGW_URL=http://127.0.0.1:8080
uv run agentgw chat
uv run agentgw run --session <id> "continue"
```

`--agent` is not required when talking to a daemon. Discord/Telegram still start their own process today; they do not attach to `serve` yet.

## Channels

Every interface calls `Harness.run()`. `serve` binds one agent package for the lifetime of the process.

```bash
# Discord (mention the bot in a guild, or DM it)
uv sync --extra discord
export DISCORD_BOT_TOKEN=...
uv run agentgw discord --agent ./agents/demo

# Telegram
uv sync --extra telegram
export TELEGRAM_BOT_TOKEN=...
uv run agentgw telegram --agent ./agents/demo
```

## Layout

```text
src/agentgw/
  harness/     loop, session, workspace, prompt compile
  skills/      SKILL.md load, gate, catalog, selector
  tools/       registry, @tool, builtins
  agent/       AGENT.md package loader
  llm/         providers
  channels/    CLI (other channels later)
agents/demo/   example agent
skills/        shared skills
tools/         shared extra tools
```

## Roadmap

Tracked as GitHub issues on milestone [Harness rebuild](https://github.com/tomluvoe/agentgw/milestone/1):

0. [Harness contracts](https://github.com/tomluvoe/agentgw/issues/1) (`AgentSpec`, `SkillRecord`, `ToolPolicy`, `RunContext`)
1. [Skill + tool management](https://github.com/tomluvoe/agentgw/issues/2) (load, gate, catalog, selector, allowlist)
2. [Agent package, loop, CLI](https://github.com/tomluvoe/agentgw/issues/3)
3. [LLM providers as execution backend](https://github.com/tomluvoe/agentgw/issues/4)
4. [Channel adapters](https://github.com/tomluvoe/agentgw/issues/5) (REST, Discord, Telegram) — all call `Harness.run()`

Later: MCP as a tool source, stronger sandbox, RAG as an optional layer — not inside the harness.

## License

Private — all rights reserved.
