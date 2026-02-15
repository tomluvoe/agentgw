# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
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
- Added 19 new tests (61 tests total, all passing)

### Changed
- RAG metadata now includes both `skills` and `tags` fields
- `rag_context.skills` defaults to `[current_skill_name]` for automatic scoping
- CLI `ingest` command accepts `--skills` parameter
- Web UI ingest form includes skills input field
- Updated skill schema documentation

## [0.1.0] - Initial Release

### Features Implemented Through v1
- ✅ **v0**: Core agent loop (ReAct pattern), tool system, skill loading, SQLite + ChromaDB, OpenAI provider, streaming
- ✅ **v0.5**: Session resume, feedback (+1/-1), few-shot examples, RAG auto-injection
- ✅ **v1**: Planner agent, FastAPI web UI with SSE streaming, REST API, shared service layer

### Roadmap
- **v1.5**: Sub-agent orchestration with `delegate_to_agent` meta-tool
- **v2**: APScheduler cron scheduling, Anthropic + xAI LLM providers
- **v2.5**: Agent-generated new SKILLs from user description
- **v3**: Full REST API, webhook support
