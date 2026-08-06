"""FastAPI backend for the QuantMind agent."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from ..agent.core import AgentEvent, AgentSession
from ..agent.llm import EchoLLM, LLMClient, OpenAILLM
from ..agent.memory import InMemoryMemory
from ..agent.tools import TOOLS
from ..audit import get_audit_logger
from ..config import get_settings
from .auth import require_api_key
from .middleware import AuditMiddleware

logger = logging.getLogger(__name__)

# In-memory session store (sufficient for dev; swap for Redis in production)
_sessions: Dict[str, AgentSession] = {}

limiter = Limiter(key_func=get_remote_address)


def _get_llm(settings=None) -> LLMClient:
    settings = settings or get_settings()
    if settings.openai_api_key:
        return OpenAILLM(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    return EchoLLM()


def _create_session(session_id: Optional[str] = None) -> tuple[str, AgentSession]:
    session_id = session_id or f"sess-{len(_sessions)+1}"
    settings = get_settings()
    session = AgentSession(
        llm=_get_llm(settings),
        memory=InMemoryMemory(),
        tools={},
        max_turns=settings.max_agent_turns,
        auto_approve=settings.auto_approve,
        session_id=session_id,
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
    settings = get_settings()
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
    get_audit_logger(settings.audit_db_path)
    yield
    _sessions.clear()


app = FastAPI(title="QuantMind Agent API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    approved: bool


class AuditQuery(BaseModel):
    action: Optional[str] = None
    session_id: Optional[str] = None
    limit: int = 100


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/disclaimer")
async def disclaimer() -> Dict[str, str]:
    return {
        "text": (
            "QuantMind is for educational and research purposes only. "
            "It does not provide investment advice. Trading involves risk, "
            "including loss of capital. Past performance does not guarantee future results. "
            "Always consult a SEBI-registered investment advisor before making investment decisions."
        )
    }


@app.post("/api/chat")
@limiter.limit("60/minute")
async def chat(
    request: Request,
    req: ChatRequest,
    api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    audit = get_audit_logger()
    if req.session_id:
        session = _get_session(req.session_id)
        session_id = req.session_id
    else:
        session_id, session = _create_session()

    audit.log(
        action="chat",
        actor=api_key,
        session_id=session_id,
        payload={"message": req.message},
    )
    events = await session.run(req.message)
    return {
        "session_id": session_id,
        "events": [_event_to_dict(e) for e in events],
    }


@app.get("/api/chat/stream")
@limiter.limit("60/minute")
async def chat_stream(
    request: Request,
    session_id: str,
    message: str,
    api_key: str = Depends(require_api_key),
) -> EventSourceResponse:
    try:
        if session_id:
            try:
                session = _get_session(session_id)
            except HTTPException:
                session_id, session = _create_session(session_id)
        else:
            session_id, session = _create_session()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit = get_audit_logger()
    audit.log(
        action="chat_stream",
        actor=api_key,
        session_id=session_id,
        payload={"message": message},
    )

    async def generator() -> AsyncGenerator[Dict[str, Any], None]:
        for event in await session.run(message):
            yield {"data": json.dumps(_event_to_dict(event))}

    return EventSourceResponse(generator(), media_type="text/event-stream")


@app.post("/api/approval/{request_id}")
@limiter.limit("60/minute")
async def approval(
    request: Request,
    request_id: str,
    req: ApprovalRequest,
    api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    audit = get_audit_logger()
    for session in _sessions.values():
        gate = session.register_approval(request_id, req.approved)
        if gate is not None:
            audit.log(
                action="approval",
                actor=api_key,
                session_id=session.session_id,
                payload={
                    "request_id": request_id,
                    "approved": req.approved,
                    "tool_name": gate.tool_name,
                },
            )
            return {
                "request_id": request_id,
                "approved": req.approved,
                "tool_name": gate.tool_name,
            }
    raise HTTPException(status_code=404, detail="Approval request not found")


@app.post("/api/audit/query")
@limiter.limit("60/minute")
async def audit_query(
    request: Request,
    q: AuditQuery,
    api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    audit = get_audit_logger()
    audit.log(
        action="audit_query",
        actor=api_key,
        session_id=q.session_id,
        payload={"action_filter": q.action, "limit": q.limit},
    )
    return audit.query(action=q.action, session_id=q.session_id, limit=q.limit)


def _event_to_dict(event: AgentEvent) -> Dict[str, Any]:
    return {"type": event.type, "data": event.data}
