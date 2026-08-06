"""FastAPI backend for the QuantMind agent."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..agent.core import AgentEvent, AgentSession, Tool
from ..agent.llm import EchoLLM, LLMClient, OpenAILLM
from ..agent.memory import InMemoryMemory
from ..agent.tools import TOOLS

logger = logging.getLogger(__name__)

# In-memory session store (sufficient for Phase 8; swap for Redis later)
_sessions: Dict[str, AgentSession] = {}


def _get_llm() -> LLMClient:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAILLM(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    return EchoLLM()


def _create_session(session_id: Optional[str] = None) -> AgentSession:
    session_id = session_id or f"sess-{len(_sessions)+1}"
    session = AgentSession(
        llm=_get_llm(),
        memory=InMemoryMemory(),
        tools={},
        auto_approve=os.getenv("QUANTMIND_AUTO_APPROVE", "false").lower() == "true",
    )
    for tool in TOOLS:
        session.add_tool(tool)
    _sessions[session_id] = session
    return session_id, session


def _get_session(session_id: str) -> AgentSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    yield
    _sessions.clear()


app = FastAPI(title="QuantMind Agent API", version="0.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    approved: bool


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    if req.session_id:
        session = _get_session(req.session_id)
        session_id = req.session_id
    else:
        session_id, session = _create_session()
    events = await session.run(req.message)
    return {
        "session_id": session_id,
        "events": [_event_to_dict(e) for e in events],
    }


@app.get("/api/chat/stream")
async def chat_stream(session_id: str, message: str) -> EventSourceResponse:
    if session_id:
        try:
            session = _get_session(session_id)
        except HTTPException:
            _, session = _create_session(session_id)
    else:
        session_id, session = _create_session()

    async def generator() -> AsyncGenerator[Dict[str, Any], None]:
        for event in await session.run(message):
            yield {"data": json.dumps(_event_to_dict(event))}

    return EventSourceResponse(generator(), media_type="text/event-stream")


@app.post("/api/approval/{request_id}")
async def approval(request_id: str, req: ApprovalRequest) -> Dict[str, Any]:
    for session in _sessions.values():
        gate = session.register_approval(request_id, req.approved)
        if gate is not None:
            # Resume the pending tool execution by re-running the last user turn
            # For simplicity, the caller should issue a new /api/chat with empty message
            return {
                "request_id": request_id,
                "approved": req.approved,
                "tool_name": gate.tool_name,
            }
    raise HTTPException(status_code=404, detail="Approval request not found")


def _event_to_dict(event: AgentEvent) -> Dict[str, Any]:
    return {"type": event.type, "data": event.data}
