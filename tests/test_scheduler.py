"""Tests for APScheduler-based cron scheduling."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentgw.scheduler.cron import CronScheduler, ScheduledJob


class TestScheduledJob:
    def test_job_creation(self):
        job = ScheduledJob(
            name="test_job",
            skill_name="general_assistant",
            message="Test message",
            cron_expression="0 9 * * *",
            enabled=True,
            log_output=True,
        )
        assert job.name == "test_job"
        assert job.skill_name == "general_assistant"
        assert job.message == "Test message"
        assert job.cron_expression == "0 9 * * *"
        assert job.enabled is True
        assert job.log_output is True


class TestCronScheduler:
    @pytest.fixture
    def mock_agent_service(self):
        service = MagicMock()
        # Mock create_agent to return a tuple
        mock_agent = AsyncMock()
        mock_agent.run_to_completion = AsyncMock(return_value="Test result")
        mock_session = MagicMock(id="test-session-123")
        mock_skill = MagicMock(name="general_assistant")
        service.create_agent = AsyncMock(return_value=(mock_agent, mock_session, mock_skill))
        return service

    @pytest.fixture
    def scheduler(self, mock_agent_service, tmp_dir):
        log_dir = tmp_dir / "logs"
        return CronScheduler(mock_agent_service, log_dir)

    def test_scheduler_initialization(self, scheduler, tmp_dir):
        assert scheduler._service is not None
        assert scheduler._log_dir == tmp_dir / "logs"
        assert scheduler._log_dir.exists()
        assert len(scheduler._jobs) == 0

    def test_add_job_disabled(self, scheduler):
        job = ScheduledJob(
            name="disabled_job",
            skill_name="general_assistant",
            message="Test",
            cron_expression="0 9 * * *",
            enabled=False,
        )
        scheduler.add_job(job)
        assert "disabled_job" not in scheduler._jobs

    def test_add_job_enabled(self, scheduler):
        job = ScheduledJob(
            name="enabled_job",
            skill_name="general_assistant",
            message="Test",
            cron_expression="0 9 * * *",
            enabled=True,
        )
        scheduler.add_job(job)
        assert "enabled_job" in scheduler._jobs

    def test_add_job_invalid_cron(self, scheduler):
        job = ScheduledJob(
            name="invalid_job",
            skill_name="general_assistant",
            message="Test",
            cron_expression="invalid cron",
            enabled=True,
        )
        scheduler.add_job(job)
        # Should not add job if cron expression is invalid
        assert "invalid_job" not in scheduler._jobs

    def test_remove_job(self, scheduler):
        job = ScheduledJob(
            name="removable_job",
            skill_name="general_assistant",
            message="Test",
            cron_expression="0 9 * * *",
            enabled=True,
        )
        scheduler.add_job(job)
        assert scheduler.remove_job("removable_job") is True
        assert "removable_job" not in scheduler._jobs

    def test_remove_nonexistent_job(self, scheduler):
        assert scheduler.remove_job("nonexistent") is False

    def test_list_jobs(self, scheduler):
        job1 = ScheduledJob(
            name="job1",
            skill_name="general_assistant",
            message="Test 1",
            cron_expression="0 9 * * *",
            enabled=True,
        )
        job2 = ScheduledJob(
            name="job2",
            skill_name="quick_assistant",
            message="Test 2",
            cron_expression="0 * * * *",
            enabled=True,
        )
        scheduler.add_job(job1)
        scheduler.add_job(job2)

        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        names = [j["name"] for j in jobs]
        assert "job1" in names
        assert "job2" in names

    @pytest.mark.asyncio
    async def test_execute_job(self, scheduler, mock_agent_service, tmp_dir):
        job = ScheduledJob(
            name="test_execution",
            skill_name="general_assistant",
            message="Execute this",
            cron_expression="0 9 * * *",
            enabled=True,
            log_output=True,
        )

        await scheduler._execute_job(job)

        # Verify agent was created
        mock_agent_service.create_agent.assert_called_once_with("general_assistant")

        # Verify log file was created
        log_file = tmp_dir / "logs" / "test_execution.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "Execute this" in log_content
        assert "Test result" in log_content

    @pytest.mark.asyncio
    async def test_execute_job_no_logging(self, scheduler, mock_agent_service):
        job = ScheduledJob(
            name="test_no_log",
            skill_name="general_assistant",
            message="Execute this",
            cron_expression="0 9 * * *",
            enabled=True,
            log_output=False,
        )

        await scheduler._execute_job(job)

        # Verify agent was created
        mock_agent_service.create_agent.assert_called_once()

        # Verify no log file was created (since log_output=False)
        # This is implicit - we just verify no exception was raised

    @pytest.mark.asyncio
    async def test_execute_job_error_handling(self, scheduler, mock_agent_service):
        # Make create_agent raise an exception
        mock_agent_service.create_agent.side_effect = ValueError("Test error")

        job = ScheduledJob(
            name="failing_job",
            skill_name="nonexistent",
            message="Will fail",
            cron_expression="0 9 * * *",
            enabled=True,
        )

        # Should not raise exception, just log error
        await scheduler._execute_job(job)

    def test_start_scheduler(self, scheduler):
        scheduler.start()
        assert scheduler._scheduler.running is True

    def test_shutdown_scheduler(self, scheduler):
        scheduler.start()
        scheduler.shutdown()
        assert scheduler._scheduler.running is False

    def test_cron_expression_validation(self, scheduler):
        # Valid expressions
        valid_jobs = [
            ("*/5 * * * *", "Every 5 minutes"),
            ("0 */2 * * *", "Every 2 hours"),
            ("30 9 * * 1-5", "9:30 AM on weekdays"),
            ("0 0 1 * *", "Midnight on 1st of each month"),
        ]

        for cron, desc in valid_jobs:
            job = ScheduledJob(
                name=f"job_{cron.replace(' ', '_')}",
                skill_name="general_assistant",
                message=desc,
                cron_expression=cron,
                enabled=True,
            )
            scheduler.add_job(job)
            assert job.name in scheduler._jobs
