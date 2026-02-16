"""Shared service layer used by CLI, Web UI, and future REST API."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agentgw.core.agent import AgentLoop, get_current_orchestration_depth
from agentgw.core.config import Settings, get_project_root, load_settings
from agentgw.core.planner import PlannerAgent, PlannerResult
from agentgw.core.session import Session
from agentgw.core.skill_loader import Skill, SkillLoader
from agentgw.core.tool_registry import ToolRegistry
from agentgw.db.sqlite import DatabaseManager
from agentgw.llm.openai_provider import OpenAIProvider
from agentgw.llm.anthropic_provider import AnthropicProvider
from agentgw.llm.xai_provider import XAIProvider
from agentgw.memory.store import MemoryStore
from agentgw.rag.chroma import RAGStore
from agentgw.tools.rag_tools import set_rag_store
from agentgw.tools.sql_tools import set_db_manager
from agentgw.tools.delegation_tools import set_agent_service
from agentgw.webhooks.delivery import WebhookDelivery
from agentgw.webhooks.loader import load_webhooks_from_config

logger = logging.getLogger(__name__)


class AgentService:
    """Central service that initializes and wires all components.

    Shared by CLI, FastAPI web UI, and future REST API.
    """

    def __init__(self, settings: Settings | None = None, root: Path | None = None):
        self._load_env()
        self.settings = settings or load_settings()
        self.root = root or get_project_root()
        self._initialized = False

        # Skill loader
        skills_dir = self.root / self.settings.skills_dir
        self.skill_loader = SkillLoader(skills_dir)
        self.skill_loader.load_all()

        # Tool registry
        self.tool_registry = ToolRegistry()
        self.tool_registry.discover(self.settings.tools_modules)

        # Storage
        db_path = self.root / self.settings.storage.sqlite_path
        self.memory = MemoryStore(db_path)

        # DB manager for sql_tools
        self.db_manager = DatabaseManager(db_path)

        chroma_path = self.root / self.settings.storage.chroma_path
        self.rag_store = RAGStore(chroma_path)

        # Webhook delivery system
        self.webhook_delivery = WebhookDelivery(
            max_retries=self.settings.webhook_max_retries,
            timeout=self.settings.webhook_timeout,
        )

        # Wire tool dependencies
        set_rag_store(self.rag_store)
        set_db_manager(self.db_manager)
        set_agent_service(self)  # For delegation tool

        # LLM provider (lazy init)
        self._llm: OpenAIProvider | AnthropicProvider | XAIProvider | None = None

    @staticmethod
    def _load_env():
        try:
            from dotenv import load_dotenv
            load_dotenv(get_project_root() / ".env")
        except ImportError:
            pass

    @property
    def llm(self) -> OpenAIProvider | AnthropicProvider | XAIProvider:
        """Lazily initialize the LLM provider based on configuration."""
        if self._llm is None:
            provider = self.settings.llm.provider.lower()

            if provider == "openai":
                api_key = self.settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
                if not api_key:
                    raise RuntimeError("OPENAI_API_KEY not set. Add it to .env or environment.")
                self._llm = OpenAIProvider(
                    api_key=api_key,
                    default_model=self.settings.llm.model,
                )
            elif provider == "anthropic":
                api_key = self.settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env or environment.")
                self._llm = AnthropicProvider(
                    api_key=api_key,
                    default_model=self.settings.llm.model,
                )
            elif provider == "xai":
                api_key = self.settings.xai_api_key or os.environ.get("XAI_API_KEY", "")
                if not api_key:
                    raise RuntimeError("XAI_API_KEY not set. Add it to .env or environment.")
                self._llm = XAIProvider(
                    api_key=api_key,
                    default_model=self.settings.llm.model,
                )
            else:
                raise ValueError(f"Unknown LLM provider: {provider}. Choose: openai, anthropic, xai")

        return self._llm

    async def initialize(self) -> None:
        """Initialize async components (DB schema, etc.)."""
        if not self._initialized:
            await self.memory.initialize()

            # Load webhook configurations
            webhooks_config = self.root / "config" / "webhooks.yaml"
            if webhooks_config.exists():
                load_webhooks_from_config(webhooks_config, self.webhook_delivery)

            self._initialized = True

    async def create_agent(
        self,
        skill_name: str,
        session_id: str | None = None,
        model_override: str | None = None,
        orchestration_depth: int | None = None,
    ) -> tuple[AgentLoop, Session, Skill]:
        """Create an agent loop for a skill, optionally resuming a session.

        Args:
            skill_name: Name of the skill to load
            session_id: Optional session ID to resume
            model_override: Optional model override
            orchestration_depth: Orchestration depth (auto-detected if None)

        Returns (agent, session, skill) tuple.
        """
        await self.initialize()

        skill = self.skill_loader.load(skill_name)
        if skill is None:
            available = [s.name for s in self.skill_loader.list_skills()]
            raise ValueError(f"Skill '{skill_name}' not found. Available: {available}")

        if model_override:
            skill.model = model_override

        # Resume or create session
        if session_id:
            session = Session(id=session_id, skill_name=skill_name)
            # Load history into session
            history = await self.memory.get_history(session_id)
            for msg in history:
                session.add_message(msg)
            logger.info("Resumed session %s with %d messages", session_id, len(history))
        else:
            session = Session.create(skill_name=skill_name)
            await self.memory.create_session(skill_name, session_id=session.id)

        # Auto-detect orchestration depth if not provided
        if orchestration_depth is None:
            orchestration_depth = get_current_orchestration_depth()

        agent = AgentLoop(
            skill=skill,
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory=self.memory,
            rag_store=self.rag_store,
            session=session,
            orchestration_depth=orchestration_depth,
            webhook_delivery=self.webhook_delivery,
        )
        return agent, session, skill

    async def route_message(self, user_message: str) -> PlannerResult:
        """Use the planner agent to route a message to the best skill."""
        await self.initialize()
        planner = PlannerAgent(llm=self.llm, skill_loader=self.skill_loader)
        return await planner.route(user_message)
