"""Heartbeat and cron jobs. A job is a user message injected on a timer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness

logger = logging.getLogger(__name__)


@dataclass
class Job:
    name: str
    message: str
    enabled: bool = True
    session: str = "heartbeat"
    every_seconds: int | None = None
    cron: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "message": self.message,
            "enabled": self.enabled,
            "session": self.session,
            "every_seconds": self.every_seconds,
            "cron": self.cron,
        }


def load_jobs(path: Path) -> list[Job]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("jobs") or []
    jobs: list[Job] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name") or not item.get("message"):
            logger.warning("Skipping invalid job entry: %s", item)
            continue
        every = item.get("every_seconds")
        jobs.append(
            Job(
                name=str(item["name"]),
                message=str(item["message"]).strip(),
                enabled=bool(item.get("enabled", True)),
                session=str(item.get("session") or "heartbeat"),
                every_seconds=int(every) if every is not None else None,
                cron=str(item["cron"]) if item.get("cron") else None,
            )
        )
    return jobs


class JobRunner:
    def __init__(self, harness: Harness, sessions: SessionMap, jobs: list[Job]):
        self.harness = harness
        self.sessions = sessions
        self.jobs = {job.name: job for job in jobs}
        self._scheduler = None

    def list_jobs(self) -> list[dict[str, Any]]:
        return [job.as_dict() for job in self.jobs.values()]

    async def run(self, name: str) -> dict[str, Any]:
        job = self.jobs.get(name)
        if job is None:
            raise KeyError(name)
        reply, session = await handle_inbound(
            self.harness, self.sessions, job.session, job.message
        )
        return {
            "job": job.name,
            "session_id": session.id,
            "response": reply,
        }

    def start(self) -> None:
        enabled = [
            job
            for job in self.jobs.values()
            if job.enabled and (job.every_seconds or job.cron)
        ]
        if not enabled:
            return
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.warning("apscheduler not installed; jobs will not fire on a timer")
            return

        scheduler = AsyncIOScheduler()
        for job in enabled:
            trigger = None
            if job.every_seconds:
                trigger = IntervalTrigger(seconds=job.every_seconds)
            elif job.cron:
                trigger = CronTrigger.from_crontab(job.cron)
            if trigger is None:
                continue
            scheduler.add_job(
                self.run,
                trigger=trigger,
                args=[job.name],
                id=job.name,
                replace_existing=True,
            )
            logger.info("Scheduled job %s", job.name)
        scheduler.start()
        self._scheduler = scheduler

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
