"""Long-running daemon server for agentgw."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from agentgw.core.service import AgentService
from agentgw.scheduler.cron import CronScheduler, ScheduledJob

logger = logging.getLogger(__name__)


class DaemonServer:
    """Main daemon server combining FastAPI + Scheduler."""

    def __init__(self, service: AgentService, pidfile: Path | None = None):
        self._service = service
        self._scheduler: CronScheduler | None = None
        self._pidfile = pidfile
        self._shutdown_event = asyncio.Event()

    async def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        enable_scheduler: bool = True,
        scheduler_config: Path | None = None,
    ):
        """Start daemon with FastAPI + optional scheduler."""

        # Initialize service
        logger.info("Initializing agentgw service...")
        await self._service.initialize()

        # Start scheduler if enabled
        if enable_scheduler:
            self._scheduler = await self._start_scheduler(scheduler_config)

        # Create FastAPI app
        app = self._create_app()

        # Write PID file
        if self._pidfile:
            self._pidfile.write_text(str(os.getpid()))
            logger.info(f"PID file written to {self._pidfile}")

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Start uvicorn server
        logger.info(f"Starting uvicorn server on {host}:{port}...")
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(config)

        # Run until shutdown signal
        try:
            await server.serve()
        finally:
            await self.shutdown()

    async def _start_scheduler(self, config_path: Path | None) -> CronScheduler | None:
        """Initialize and start the cron scheduler."""
        config_file = config_path or (self._service.root / "config" / "scheduled_jobs.yaml")

        if not config_file.exists():
            logger.warning(f"Scheduler config not found: {config_file}, skipping scheduler")
            return None

        try:
            # Load jobs from YAML config
            import yaml
            with open(config_file) as f:
                config_data = yaml.safe_load(f) or {}

            jobs_data = config_data.get("jobs", [])
            if not jobs_data:
                logger.info("No jobs defined in scheduler config")
                return None

            # Parse job configurations
            jobs = []
            for job_data in jobs_data:
                job = ScheduledJob(
                    name=job_data["name"],
                    skill_name=job_data["skill_name"],
                    message=job_data["message"],
                    cron_expression=job_data["cron_expression"],
                    enabled=job_data.get("enabled", True),
                    log_output=job_data.get("log_output", True),
                )
                jobs.append(job)

            enabled_jobs = [job for job in jobs if job.enabled]

            if not enabled_jobs:
                logger.info("No enabled jobs found in scheduler config")
                return None

            log_dir = self._service.root / self._service.settings.storage.log_dir

            scheduler = CronScheduler(self._service, log_dir)
            for job in enabled_jobs:
                scheduler.add_job(job)

            scheduler.start()
            logger.info(f"Scheduler started with {len(enabled_jobs)} enabled jobs")
            return scheduler
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}", exc_info=True)
            return None

    def _create_app(self) -> FastAPI:
        """Create FastAPI app with all routes."""
        from agentgw.interfaces.web.app import create_app

        # Reuse existing web app factory, passing our service instance
        app = create_app(service=self._service)

        # Add daemon-specific endpoints
        @app.get("/daemon/status", tags=["Daemon"])
        async def daemon_status():
            """Get daemon status including scheduler info."""
            scheduler_info = {
                "enabled": self._scheduler is not None,
                "jobs_count": len(self._scheduler._jobs) if self._scheduler else 0,
            }
            if self._scheduler:
                scheduler_info["jobs"] = [
                    {
                        "name": job.name,
                        "skill": job.skill_name,
                        "cron": job.cron_expression,
                        "enabled": job.enabled,
                    }
                    for job in self._scheduler._jobs.values()
                ]

            return {
                "status": "running",
                "scheduler": scheduler_info,
                "service": {
                    "llm_provider": self._service.settings.llm.provider,
                    "llm_model": self._service.settings.llm.model,
                },
            }

        return app

    def _setup_signal_handlers(self):
        """Handle SIGTERM/SIGINT for graceful shutdown."""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating graceful shutdown...")
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down daemon...")

        if self._scheduler:
            logger.info("Shutting down scheduler...")
            self._scheduler.shutdown()

        if hasattr(self._service, 'db_manager') and self._service.db_manager:
            logger.info("Closing database connections...")
            await self._service.db_manager.close()

        if self._pidfile and self._pidfile.exists():
            self._pidfile.unlink()
            logger.info(f"PID file removed: {self._pidfile}")

        logger.info("Daemon shut down successfully")
