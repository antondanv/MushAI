from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OutboundEvent:
    type: str
    content: str
    session_id: str
    run_id: str
    source: str = "runtime"
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)