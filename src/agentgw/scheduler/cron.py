"""APScheduler-based cron scheduling for agent tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class ScheduledJob:
    """A scheduled job configuration."""

    def __init__(
        self,
        name: str,
        skill_name: str,
        message: str,
        cron_expression: str,
        enabled: bool = True,
        log_output: bool = True,
    ):
        self.name = name
        self.skill_name = skill_name
        self.message = message
        self.cron_expression = cron_expression
        self.enabled = enabled
        self.log_output = log_output


class CronScheduler:
    """Manages scheduled agent tasks using APScheduler."""

    def __init__(self, agent_service, log_dir: Path):
        self._service = agent_service
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, ScheduledJob] = {}

    def add_job(self, job: ScheduledJob) -> None:
        """Add a scheduled job."""
        if not job.enabled:
            logger.info("Job '%s' is disabled, skipping", job.name)
            return

        self._jobs[job.name] = job

        # Parse cron expression
        try:
            trigger = CronTrigger.from_crontab(job.cron_expression)
        except Exception as e:
            logger.error("Invalid cron expression for job '%s': %s", job.name, e)
            return

        # Schedule the job
        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job.name,
            args=[job],
            name=f"Agent Task: {job.name}",
            replace_existing=True,
        )
        logger.info("Scheduled job '%s' with cron '%s'", job.name, job.cron_expression)

    def remove_job(self, job_name: str) -> bool:
        """Remove a scheduled job."""
        if job_name in self._jobs:
            del self._jobs[job_name]
            try:
                self._scheduler.remove_job(job_name)
                logger.info("Removed job '%s'", job_name)
                return True
            except Exception as e:
                logger.warning("Failed to remove job '%s': %s", job_name, e)
                return False
        return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs with their next run times."""
        result = []
        for job in self._scheduler.get_jobs():
            scheduled_job = self._jobs.get(job.id)
            result.append({
                "name": job.id,
                "skill": scheduled_job.skill_name if scheduled_job else "unknown",
                "cron": scheduled_job.cron_expression if scheduled_job else "unknown",
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "enabled": scheduled_job.enabled if scheduled_job else False,
            })
        return result

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started with %d job(s)", len(self._jobs))

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown()
            logger.info("Scheduler shut down")

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("Executing scheduled job '%s' at %s", job.name, timestamp)

        try:
            # Create agent for the job
            agent, session, skill = await self._service.create_agent(job.skill_name)

            # Run the job to completion
            result = await agent.run_to_completion(job.message)

            # Log output if enabled
            if job.log_output:
                log_file = self._log_dir / f"{job.name}.log"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"Executed: {timestamp}\n")
                    f.write(f"Skill: {job.skill_name}\n")
                    f.write(f"Message: {job.message}\n")
                    f.write(f"Result:\n{result}\n")
                logger.info("Logged output to %s", log_file)

            logger.info("Completed scheduled job '%s'", job.name)

        except Exception as e:
            logger.error("Failed to execute scheduled job '%s': %s", job.name, e, exc_info=True)
