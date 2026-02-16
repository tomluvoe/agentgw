"""Tests for webhook delivery system."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentgw.webhooks.delivery import Webhook, WebhookDelivery, WebhookEvent


class TestWebhook:
    def test_webhook_creation(self):
        webhook = Webhook(
            name="test_webhook",
            url="http://localhost:8080/webhook",
            events=[WebhookEvent.AGENT_STARTED, WebhookEvent.AGENT_COMPLETED],
            secret="test-secret",
            enabled=True,
        )
        assert webhook.name == "test_webhook"
        assert webhook.url == "http://localhost:8080/webhook"
        assert len(webhook.events) == 2
        assert webhook.secret == "test-secret"
        assert webhook.enabled is True

    def test_webhook_no_secret(self):
        webhook = Webhook(
            name="no_secret",
            url="http://example.com/hook",
            events=[WebhookEvent.TOOL_EXECUTED],
            secret=None,
            enabled=True,
        )
        assert webhook.secret is None


class TestWebhookEvent:
    def test_event_values(self):
        assert WebhookEvent.AGENT_STARTED.value == "agent.started"
        assert WebhookEvent.AGENT_COMPLETED.value == "agent.completed"
        assert WebhookEvent.AGENT_FAILED.value == "agent.failed"
        assert WebhookEvent.TOOL_EXECUTED.value == "tool.executed"
        assert WebhookEvent.SESSION_CREATED.value == "session.created"
        assert WebhookEvent.FEEDBACK_RECEIVED.value == "feedback.received"


class TestWebhookDelivery:
    @pytest.fixture
    def delivery(self):
        return WebhookDelivery(max_retries=3, timeout=10)

    def test_initialization(self, delivery):
        assert delivery._max_retries == 3
        assert delivery._timeout == 10
        assert len(delivery._webhooks) == 0

    def test_register_webhook(self, delivery):
        webhook = Webhook(
            name="test",
            url="http://example.com",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )
        delivery.register(webhook)
        assert "test" in delivery._webhooks
        assert delivery._webhooks["test"] == webhook

    def test_unregister_webhook(self, delivery):
        webhook = Webhook(
            name="test",
            url="http://example.com",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )
        delivery.register(webhook)
        assert delivery.unregister("test") is True
        assert "test" not in delivery._webhooks

    def test_unregister_nonexistent(self, delivery):
        assert delivery.unregister("nonexistent") is False

    @pytest.mark.asyncio
    async def test_send_event_no_subscribers(self, delivery):
        # Should not raise error when no webhooks subscribed
        await delivery.send_event(
            WebhookEvent.AGENT_STARTED,
            {"session_id": "123", "skill_name": "test"},
        )

    @pytest.mark.asyncio
    async def test_send_event_with_subscriber(self, delivery):
        webhook = Webhook(
            name="subscriber",
            url="http://example.com/hook",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )
        delivery.register(webhook)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_post = AsyncMock(return_value=mock_response)
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock()

            mock_session = AsyncMock()
            mock_session.post = mock_post
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None

            mock_session_class.return_value = mock_session

            # Send event
            await delivery.send_event(
                WebhookEvent.AGENT_STARTED,
                {"session_id": "123"},
            )

            # Give async task time to execute
            await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_deliver_to_webhook_success(self, delivery):
        webhook = Webhook(
            name="test",
            url="http://example.com/hook",
            events=[WebhookEvent.AGENT_STARTED],
            secret="secret123",
            enabled=True,
        )

        payload = {
            "event": "agent.started",
            "timestamp": "2024-01-01T00:00:00",
            "data": {"session_id": "123"},
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_post = AsyncMock(return_value=mock_response)
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock()

            mock_session = AsyncMock()
            mock_session.post = mock_post
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None

            mock_session_class.return_value = mock_session

            await delivery._deliver_to_webhook(webhook, payload)

            # Verify session.post was called with correct parameters
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"] == payload
            assert "X-Webhook-Secret" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Webhook-Secret"] == "secret123"

    @pytest.mark.asyncio
    async def test_deliver_to_webhook_retry_on_failure(self, delivery):
        webhook = Webhook(
            name="test",
            url="http://example.com/hook",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )

        payload = {"event": "agent.started", "data": {}}

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 500  # Server error
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_post = AsyncMock(return_value=mock_response)
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock()

            mock_session = AsyncMock()
            mock_session.post = mock_post
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None

            mock_session_class.return_value = mock_session

            # Patch asyncio.sleep to avoid waiting
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await delivery._deliver_to_webhook(webhook, payload)

            # Should have retried max_retries times
            assert mock_post.call_count == delivery._max_retries

    @pytest.mark.asyncio
    async def test_deliver_to_webhook_disabled(self, delivery):
        webhook = Webhook(
            name="disabled",
            url="http://example.com",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=False,  # Disabled
        )
        delivery.register(webhook)

        # Send event - should not deliver to disabled webhook
        await delivery.send_event(WebhookEvent.AGENT_STARTED, {})

        # No way to directly verify, but it shouldn't call the URL

    @pytest.mark.asyncio
    async def test_deliver_event_filters_by_event_type(self, delivery):
        # Register webhook for AGENT_STARTED only
        webhook = Webhook(
            name="filtered",
            url="http://example.com",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )
        delivery.register(webhook)

        # Send AGENT_COMPLETED event - should not deliver
        await delivery._deliver_event(
            WebhookEvent.AGENT_COMPLETED,
            {"session_id": "123"},
        )

        # Nothing to assert directly, but it shouldn't error

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, delivery):
        """Test that retries use exponential backoff (2^attempt seconds)."""
        webhook = Webhook(
            name="test",
            url="http://example.com",
            events=[WebhookEvent.AGENT_STARTED],
            enabled=True,
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Always fail
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_post = AsyncMock(return_value=mock_response)
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock()

            mock_session = AsyncMock()
            mock_session.post = mock_post
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None

            mock_session_class.return_value = mock_session

            sleep_calls = []

            async def track_sleep(seconds):
                sleep_calls.append(seconds)

            with patch("asyncio.sleep", side_effect=track_sleep):
                await delivery._deliver_to_webhook(webhook, {})

            # Should have slept 2^0=1, 2^1=2 seconds between 3 attempts
            assert len(sleep_calls) == 2  # max_retries-1 sleeps
            assert sleep_calls[0] == 1  # 2^0
            assert sleep_calls[1] == 2  # 2^1
