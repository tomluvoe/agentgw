# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (Production Readiness Features)
- **API Key Authentication**: Bearer token authentication via `AGENTGW_API_KEY`
  - APIKeyMiddleware for protecting endpoints
  - Public endpoints: /, /health, /docs, /static/*
  - All /api/* routes require authentication when configured
- **OpenAPI/Swagger Documentation**: Interactive API docs at `/docs` and `/redoc`
  - Endpoints organized by tags (Chat, Skills, Sessions, Knowledge Base, Tools, System)
  - Request/response models fully documented
- **Health Check Endpoint**: `/health` for monitoring and load balancers
  - Returns service status, version, provider, and model
  - Used in Docker HEALTHCHECK and Kubernetes probes
- **Graceful Shutdown**: Clean resource cleanup on termination
  - Database connections closed properly
  - Lifespan context manager for startup/shutdown hooks
- **Deployment Guide**: Comprehensive DEPLOYMENT.md with:
  - Docker and docker-compose examples
  - Systemd service configuration
  - Nginx reverse proxy with SSL/TLS
  - Security best practices and hardening
  - Monitoring, backup, and Kubernetes deployment

### Added (v2 & v3)
- **Cron scheduling (v2)**: APScheduler-based task scheduling
  - `CronScheduler` class for managing scheduled agent tasks
  - YAML configuration in `config/scheduled_jobs.yaml`
  - CLI: `agentgw scheduler --start` to run scheduled jobs
  - CLI: `agentgw scheduler --list` to view configured jobs
  - Automatic job execution with logging to `data/logs/`
- **Multi-provider LLM support (v2)**: Support for OpenAI, Anthropic, and xAI
  - `AnthropicProvider` with full streaming and tool calling support
  - `XAIProvider` for Grok models (OpenAI-compatible API)
  - Provider selection via `llm.provider` config (openai/anthropic/xai)
  - Per-provider API keys in config/environment
- **Webhook system (v3)**: Event-driven webhook delivery
  - `WebhookDelivery` class with retry logic and exponential backoff
  - Events: agent.started, agent.completed, agent.failed, tool.executed, session.created
  - YAML configuration in `config/webhooks.yaml`
  - CLI: `agentgw webhooks --list` to view configured webhooks
  - Fire-and-forget delivery with `asyncio.create_task`
  - Webhook secret authentication support
- **Extended REST API (v3)**: Additional endpoints for configuration and monitoring
  - `GET /api/config` - Current configuration
  - `GET /api/tools` - List all registered tools
  - `POST /api/tools/{tool_name}/execute` - Execute tool directly
  - `GET /api/stats` - Usage statistics

### Added (v1.5)
- **Per-skill model selection**: Each skill can specify its own LLM model
  - Example skills demonstrating model selection (`code_assistant`, `quick_assistant`)
  - Model hierarchy: CLI override > skill YAML > global default
  - Comprehensive guide in `examples/per_skill_models.md`
- **Sub-agent orchestration**: Skills can now delegate tasks to other specialized skills
  - New `delegate_to_agent` meta-tool for task delegation
  - Orchestration depth tracking with configurable max depth (default: 3)
  - Context variables for async depth management
  - Example `project_manager` orchestrator skill
  - Prevents infinite recursion with depth limits
- **Skill-based RAG filtering**: Documents can now be associated with specific skills
  - Use `--skills skill1 skill2` when ingesting to limit document access
  - Leave empty to make documents available to all agents
  - Auto-filtering by current skill in `rag_context`
  - Post-filtering in Python for precise skill/tag matching
  - Backward compatible with tag-only filtering
- **Document management**: View, search, and delete ingested documents
  - CLI: `agentgw documents` to list, filter by skill/source
  - CLI: `agentgw delete-documents` to remove by source or ID
  - Web UI: `/documents` page with search, preview, and delete
  - API: `GET /api/documents` and `DELETE /api/documents`
- Added 37 new tests (79 tests total, all passing)

### Changed
- RAG metadata now includes both `skills` and `tags` fields
- `rag_context.skills` defaults to `[current_skill_name]` for automatic scoping
- CLI `ingest` command accepts `--skills` parameter
- Web UI ingest form includes skills input field
- Updated skill schema documentation

## [0.1.0] - Initial Release

### Features Implemented Through v1.5
- ✅ **v0**: Core agent loop (ReAct pattern), tool system, skill loading, SQLite + ChromaDB, OpenAI provider, streaming
- ✅ **v0.5**: Session resume, feedback (+1/-1), few-shot examples, RAG auto-injection
- ✅ **v1**: Planner agent, FastAPI web UI with SSE streaming, REST API, shared service layer
- ✅ **v1.5**: Sub-agent orchestration, delegate_to_agent meta-tool, depth tracking

### Roadmap
- **v2**: ✅ APScheduler cron scheduling, Anthropic + xAI LLM providers (COMPLETE)
- **v3**: ✅ Full REST API expansion, webhook support (COMPLETE)
- **v3.5**: Agent-generated new SKILLs from user description (NEXT)
