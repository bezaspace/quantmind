import json
import os
import tempfile
from datetime import datetime

import polars as pl
import pytest

from quantmind.agent.core import AgentEvent, AgentSession, Tool, ToolResult
from quantmind.agent.llm import EchoLLM, LLMClient
from quantmind.agent.memory import InMemoryMemory
from quantmind.agent.tools import get_tool, run_backtest, save_backtest_bundle
from quantmind.api.main import app


class MutateLLM(LLMClient):
    async def chat(self, messages, tools=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {
                        "name": "mutate",
                        "arguments": json.dumps({}),
                    },
                }
            ],
        }


def test_agent_session_echo():
    session = AgentSession(llm=EchoLLM(), memory=InMemoryMemory())
    events = await_tool(session.run("hello"))
    assert events[0].type == "assistant_message"
    assert "echo: hello" in events[0].data["content"]


def test_tool_run_with_handler():
    async def handler(x: int) -> ToolResult:
        return ToolResult(True, {"x": x * 2})

    tool = Tool(name="double", description="", parameters={}, handler=handler)
    result = await_tool(tool.run({"x": 3}))
    assert result.success
    assert result.payload["x"] == 6


def test_tool_result_failure():
    async def handler() -> ToolResult:
        return ToolResult(False, None, "boom")

    tool = Tool(name="boom", description="", parameters={}, handler=handler)
    result = await_tool(tool.run({}))
    assert not result.success
    assert result.error == "boom"


def test_approval_gate():
    session = AgentSession(llm=MutateLLM(), memory=InMemoryMemory())

    async def handler() -> ToolResult:
        return ToolResult(True, {"ok": True})

    tool = Tool(
        name="mutate",
        description="",
        parameters={},
        handler=handler,
        requires_approval=True,
    )
    session.add_tool(tool)
    events = await_tool(session.run("run mutate", auto_approve=False))
    assert events[-1].type == "approval_requested"
    request_id = events[-1].data["request_id"]
    gate = session.register_approval(request_id, True)
    assert gate.approved is True


def test_get_tool():
    tool = get_tool("get_ohlcv")
    assert tool.name == "get_ohlcv"
    with pytest.raises(KeyError):
        get_tool("nonexistent")


def test_memory_conversation():
    memory = InMemoryMemory()
    memory.add_user_message("hi")
    memory.add_assistant_message("hello")
    memory.add_tool_result("1", "tool", True, {"a": 1})
    assert len(memory.to_llm_messages()) == 3


def test_save_backtest_bundle_tool():
    equity = pl.DataFrame(
        {
            "Datetime": ["2023-01-01", "2023-01-02"],
            "TotalEquity": [1000.0, 1100.0],
        }
    )
    trades = pl.DataFrame(
        {
            "Datetime": ["2023-01-01"],
            "Symbol": ["SYM"],
            "Side": ["BUY"],
            "Price": [100.0],
            "Quantity": [10.0],
            "Fee": [0.0],
            "PnL": [0.0],
            "Reason": ["buy"],
        }
    )
    result_json = json.dumps(
        {
            "equity_curve": equity.to_dicts(),
            "trades": trades.to_dicts(),
            "total_return": 0.1,
            "max_drawdown": 0.0,
            "num_trades": 1,
            "win_rate": 1.0,
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run.iafbt")
        result = await_tool(save_backtest_bundle(path, result_json))
        assert result.success
        assert os.path.exists(path)


def await_tool(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


# FastAPI tests
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_endpoint(client):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert len(data["events"]) > 0


def test_chat_stream(client):
    resp = client.get("/api/chat/stream?session_id=test-1&message=hello")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
