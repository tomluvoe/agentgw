"""Public harness entry: load package, select skills, run the loop."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from agentgw.agent.package import AgentPackage, load_package
from agentgw.harness.loop import AgentLoop
from agentgw.harness.prompt import compile_system_prompt
from agentgw.harness.session import Session
from agentgw.harness.spec import AgentSpec, RunContext
from agentgw.skills.selector import select_skills


class Harness:
    def __init__(self, package: AgentPackage, llm):
        self.package = package
        self.llm = llm

    @classmethod
    def from_path(
        cls,
        agent_path: Path,
        llm,
        *,
        workspace: Path | None = None,
        extra_skill_roots: list[Path] | None = None,
    ) -> Harness:
        package = load_package(
            agent_path,
            workspace_override=workspace,
            extra_skill_roots=extra_skill_roots,
        )
        return cls(package, llm)

    def compile(self, user_message: str) -> AgentSpec:
        pkg = self.package
        activated = select_skills(
            user_message,
            pkg.skills,
            always=pkg.skill_always,
            max_activated=pkg.max_activated,
        )
        system = compile_system_prompt(pkg.system_prompt, pkg.skills, activated)
        ctx = RunContext(
            workspace=pkg.workspace,
            skill_dirs={s.name: s.directory for s in pkg.skills},
        )
        return AgentSpec(
            name=pkg.name,
            description=pkg.description,
            system_prompt=system,
            model=pkg.model,
            provider=pkg.provider,
            temperature=pkg.temperature,
            max_iterations=pkg.max_iterations,
            tool_policy=pkg.tool_policy,
            activated_skills=tuple(activated),
            catalog_skills=tuple(pkg.skills),
            workspace=pkg.workspace,
            context=ctx,
        )

    async def run(
        self,
        user_message: str,
        session: Session | None = None,
    ) -> AsyncIterator[str]:
        session = session or Session.create(self.package.name)
        spec = self.compile(user_message)
        loop = AgentLoop(spec, self.llm, self.package.registry, session)
        async for chunk in loop.run(user_message):
            yield chunk

    async def run_to_completion(
        self,
        user_message: str,
        session: Session | None = None,
    ) -> str:
        chunks: list[str] = []
        async for chunk in self.run(user_message, session=session):
            chunks.append(chunk)
        return "".join(chunks)
