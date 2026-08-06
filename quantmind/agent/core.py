"""Core agent primitives: tools, tool calls, and the agent session loop."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .llm import LLMClient
from .memory import InMemoryMemory

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Outcome of executing a tool."""

    success: bool
    payload: Any
    error: Optional[str] = None


@dataclass
class ToolCall:
    """A request to invoke a tool parsed from an LLM response."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ApprovalGate:
    """Pending approval state for a mutating tool call."""

    request_id: str
    tool_name: str
    arguments: Dict[str, Any]
    approved: Optional[bool] = None
    approved_at: Optional[str] = None


@dataclass
class Tool:
    """Agent-usable tool definition."""

    name: str
    description: str
    parameters: Dict[str, Any]
    requires_approval: bool = False
    handler: Optional[Callable[..., Awaitable[ToolResult]]] = None

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.handler is None:
            return ToolResult(False, None, "Tool has no handler")
        return await self.handler(**arguments)


@dataclass
class AgentEvent:
    """Structured event emitted by the agent session."""

    type: str
    data: Dict[str, Any]


@dataclass
class AgentSession:
    """A single agent conversation with tool-use and approval gates."""

    llm: LLMClient
    memory: InMemoryMemory = field(default_factory=InMemoryMemory)
    tools: Dict[str, Tool] = field(default_factory=dict)
    max_turns: int = 5
    auto_approve: bool = False
    session_id: str = ""

    def __post_init__(self) -> None:
        self._pending_approvals: Dict[str, ApprovalGate] = {}

    def add_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def register_approval(self, request_id: str, approved: bool) -> Optional[ApprovalGate]:
        gate = self._pending_approvals.get(request_id)
        if gate is None:
            return None
        gate.approved = approved
        gate.approved_at = str(asyncio.get_event_loop().time())
        return gate

    async def run(self, user_message: str, auto_approve: Optional[bool] = None) -> List[AgentEvent]:
        events: List[AgentEvent] = []
        self.memory.add_user_message(user_message)
        auto = self.auto_approve if auto_approve is None else auto_approve

        for turn in range(self.max_turns):
            logger.debug("Agent turn %d", turn + 1)
            messages = self.memory.to_llm_messages()
            response = await self.llm.chat(
                messages=messages,
                tools=[t.to_openai_schema() for t in self.tools.values()],
            )

            assistant_message = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            if assistant_message:
                events.append(
                    AgentEvent("assistant_message", {"content": assistant_message})
                )
                self.memory.add_assistant_message(assistant_message)

            if not tool_calls:
                break

            for tc in tool_calls:
                call = ToolCall(
                    id=tc.get("id") or str(uuid.uuid4()),
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                )
                events.append(
                    AgentEvent("tool_call", {"id": call.id, "name": call.name, "arguments": call.arguments})
                )

                tool = self.tools.get(call.name)
                if tool is None:
                    events.append(
                        AgentEvent("tool_result", {"id": call.id, "error": f"Unknown tool {call.name}"})
                    )
                    self.memory.add_tool_result(call.id, call.name, False, error=f"Unknown tool {call.name}")
                    continue

                if tool.requires_approval and not auto:
                    request_id = str(uuid.uuid4())
                    gate = ApprovalGate(
                        request_id=request_id,
                        tool_name=call.name,
                        arguments=call.arguments,
                    )
                    self._pending_approvals[request_id] = gate
                    events.append(
                        AgentEvent(
                            "approval_requested",
                            {
                                "request_id": request_id,
                                "tool_name": call.name,
                                "arguments": call.arguments,
                            },
                        )
                    )
                    # Stop loop until approved externally
                    return events

                try:
                    result = await tool.run(call.arguments)
                except Exception as exc:
                    logger.exception("Tool %s failed", call.name)
                    result = ToolResult(False, None, str(exc))

                events.append(
                    AgentEvent(
                        "tool_result",
                        {
                            "id": call.id,
                            "name": call.name,
                            "success": result.success,
                            "payload": result.payload,
                            "error": result.error,
                        },
                    )
                )
                self.memory.add_tool_result(
                    call.id, call.name, result.success, result.payload, result.error
                )

        return events
