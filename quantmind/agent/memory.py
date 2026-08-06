"""In-memory conversation and provenance memory for agent sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InMemoryMemory:
    """Simple conversation memory with tool-result provenance."""

    messages: List[Dict[str, Any]] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_result(
        self,
        call_id: str,
        name: str,
        success: bool,
        payload: Any = None,
        error: Optional[str] = None,
    ) -> None:
        content = {"success": success}
        if payload is not None:
            content["result"] = payload
        if error is not None:
            content["error"] = error
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": str(content),
            }
        )

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)
