from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentgw.llm.anthropic_provider import AnthropicProvider
from agentgw.llm.factory import create_llm
from agentgw.llm.openai_provider import OpenAIProvider
from agentgw.llm.types import Message, ToolCall
from agentgw.llm.xai_provider import XAIProvider


class _Aiter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


@pytest.fixture
def no_dotenv(monkeypatch):
    monkeypatch.setattr("agentgw.llm.factory._load_dotenv", lambda: None)


def test_factory_requires_key(monkeypatch, no_dotenv):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        create_llm("openai")


def test_factory_unknown_provider(monkeypatch, no_dotenv):
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm("nope")


def test_factory_selects_xai(monkeypatch, no_dotenv):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    with patch("agentgw.llm.xai_provider.AsyncOpenAI") as cls:
        llm = create_llm("xai", model="grok-3")
        assert isinstance(llm, XAIProvider)
        assert llm._default_model == "grok-3"
        assert cls.call_args.kwargs["base_url"] == "https://api.x.ai/v1"


def test_factory_env_provider(monkeypatch, no_dotenv):
    monkeypatch.setenv("AGENTGW_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with patch("agentgw.llm.anthropic_provider.AsyncAnthropic"):
        llm = create_llm()
        assert isinstance(llm, AnthropicProvider)


def test_openai_message_conversion():
    with patch("agentgw.llm.openai_provider.AsyncOpenAI"):
        p = OpenAIProvider("sk")
    converted = p._convert_messages(
        [
            Message(role="system", content="sys"),
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content=None,
                tool_calls=[ToolCall(id="1", name="read", arguments='{"path":"a"}')],
            ),
            Message(role="tool", content="ok", tool_call_id="1", name="read"),
        ]
    )
    assert converted[0]["role"] == "system"
    assert converted[2]["tool_calls"][0]["function"]["name"] == "read"
    assert converted[3]["tool_call_id"] == "1"


@pytest.mark.asyncio
async def test_openai_chat_stream_text():
    with patch("agentgw.llm.openai_provider.AsyncOpenAI") as cls:
        client = cls.return_value
        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hello ", tool_calls=None),
                        finish_reason=None,
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="world", tool_calls=None),
                        finish_reason="stop",
                    )
                ]
            ),
        ]

        async def create(**kwargs):
            assert kwargs["stream"] is True
            assert kwargs["model"] == "gpt-test"
            return _Aiter(chunks)

        client.chat.completions.create = create
        p = OpenAIProvider("sk", default_model="gpt-test")
        out = []
        async for chunk in p.chat_stream([Message(role="user", content="Hi")]):
            if chunk.delta_content:
                out.append(chunk.delta_content)
        assert "".join(out) == "Hello world"


@pytest.mark.asyncio
async def test_openai_chat_non_stream():
    with patch("agentgw.llm.openai_provider.AsyncOpenAI") as cls:
        client = cls.return_value
        message = SimpleNamespace(content="done", tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)

        async def create(**kwargs):
            assert "stream" not in kwargs
            return SimpleNamespace(choices=[choice], usage=usage)

        client.chat.completions.create = create
        p = OpenAIProvider("sk")
        resp = await p.chat([Message(role="user", content="Hi")])
        assert resp.content == "done"
        assert resp.usage.total_tokens == 3


def test_anthropic_convert_system_and_tools():
    with patch("agentgw.llm.anthropic_provider.AsyncAnthropic"):
        p = AnthropicProvider("ant")
    system, msgs = p._convert_messages(
        [
            Message(role="system", content="be brief"),
            Message(role="user", content="Hi"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="c1", name="read", arguments='{"path":"a"}')],
            ),
            Message(role="tool", content="file", tool_call_id="c1", name="read"),
        ]
    )
    assert system == "be brief"
    assert msgs[0]["content"][0] == {"type": "text", "text": "Hi"}
    assert msgs[1]["content"][0]["type"] == "tool_use"
    assert msgs[2]["content"][0]["type"] == "tool_result"
    tools = p._convert_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )
    assert tools[0]["name"] == "read"
    assert tools[0]["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_anthropic_chat_stream_text():
    with patch("agentgw.llm.anthropic_provider.AsyncAnthropic") as cls:
        client = cls.return_value
        events = [
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text="Hey"),
                index=0,
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason="end_turn"),
            ),
        ]

        async def create(**kwargs):
            assert kwargs["stream"] is True
            assert kwargs["system"] == "sys"
            return _Aiter(events)

        client.messages.create = create
        p = AnthropicProvider("ant")
        out = []
        async for chunk in p.chat_stream(
            [Message(role="system", content="sys"), Message(role="user", content="Hi")]
        ):
            if chunk.delta_content:
                out.append(chunk.delta_content)
        assert out == ["Hey"]


@pytest.mark.asyncio
async def test_anthropic_chat_non_stream():
    with patch("agentgw.llm.anthropic_provider.AsyncAnthropic") as cls:
        client = cls.return_value
        block = SimpleNamespace(type="text", text="ok")
        usage = SimpleNamespace(input_tokens=4, output_tokens=5)

        async def create(**kwargs):
            return SimpleNamespace(
                content=[block],
                usage=usage,
                stop_reason="end_turn",
            )

        client.messages.create = create
        p = AnthropicProvider("ant")
        resp = await p.chat([Message(role="user", content="Hi")])
        assert resp.content == "ok"
        assert resp.usage.prompt_tokens == 4


@pytest.mark.asyncio
async def test_xai_chat_stream_passes_tools():
    with patch("agentgw.llm.xai_provider.AsyncOpenAI") as cls:
        client = cls.return_value
        captured = {}

        async def create(**kwargs):
            captured.update(kwargs)
            return _Aiter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="g", tool_calls=None),
                                finish_reason="stop",
                            )
                        ]
                    )
                ]
            )

        client.chat.completions.create = create
        p = XAIProvider("xai")
        tools = [{"type": "function", "function": {"name": "read"}}]
        texts = []
        async for chunk in p.chat_stream(
            [Message(role="user", content="Hi")], tools=tools
        ):
            if chunk.delta_content:
                texts.append(chunk.delta_content)
        assert texts == ["g"]
        assert captured["tools"] == tools


def test_channels_do_not_import_sdks():
    import ast
    from pathlib import Path

    cli = Path(__file__).resolve().parents[1] / "src" / "agentgw" / "channels" / "cli.py"
    tree = ast.parse(cli.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "openai" not in imported
    assert "anthropic" not in imported
