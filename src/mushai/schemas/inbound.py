from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class InboundMessage:
    text: str
    channel: str = "cli"
    session_id: str | None = None
    user_id = str | None = None
    channel_message_id: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)