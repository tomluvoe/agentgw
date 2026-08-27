# Changelog

## 0.2.0

Rebuild as a harness. Skills are Agent Skills `SKILL.md` packs. Tools are functions. Agents are `AGENT.md` files that include skills and tools by path.

Removed from the core: RAG/Chroma, YAML-as-agent, planner router, web UI, cron, webhooks.

Install and run with `uv`.

REST (`agentgw serve`), Discord, and Telegram channels all call the same harness.
