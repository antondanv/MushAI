from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from autogen_agentchat.messages import BaseChatMessage, MultiModalMessage

from mushai.execution.team_factory import MagneticTeamFactory
from mushai.schemas.inbound import InboundMessage
from mushai.schemas.outbound import OutboundEvent


@dataclass(slots=True)
class RuntimeSessionState:
    session_id: str
    team_state: Mapping[str, Any] | None = None


class TeamRuntime:
    def __init__(self, factory: MagneticTeamFactory | None = None) -> None:
        self.factory = factory or MagneticTeamFactory()
        self._sessions: dict[str, RuntimeSessionState] = {}

    def _ensure_session(self, session_id: str) -> RuntimeSessionState:
        session = self._sessions.get(session_id)
        if session is None:
            session = RuntimeSessionState(session_id=session_id)
            self._sessions[session_id] = session
        return session
    
    def _message_to_text(self, message: BaseChatMessage | None) -> str:
        if message is None:
            return ""
        
        if isinstance(message, MultiModalMessage):
            return message.to_text().strip()
        
        content = message.content
        if isinstance(content, str):
            return content.strip()
        
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                else:
                    parts.append("<image>")
            return "\n".join(part for part in parts if part).strip()
    
        return str(content).strip()
    
    async def _close_client(self, client: Any) -> None:
        close_method = getattr(client, "close", None)
        if not callable(close_method):
            return

        result = close_method()
        if inspect.isawaitable(result):
            await result

    async def run(self, message: InboundMessage) -> list[OutboundEvent]:
        session_id = message.session_id or str(uuid4())
        run_id = str(uuid4())
        session = self._ensure_session(session_id)

        client = self.factory.create_model_client
        executor = self.factory.create_code_executor

        is_first_turn = session.team_state is None
        outbound_events: list[OutboundEvent] = [
            OutboundEvent(
                type="status",
                content="Run started.",
                session_id=session_id,
                run_id=run_id,
                source="runtime",
                trace_id=message.trace_id,
                metadata={
                    "channel": message.channel,
                    "is_first_turn": is_first_turn,
                },
            )
        ]

        try:
            async with executor as code_executor:
                team = self.factory.build_team(
                    client=client,
                    code_executor=code_executor,
                )
                
                if session.team_state is not None:
                    await team.load_state(session.team_state)
                    task = self.factory.buid_followup_task(message.text)
                else:
                    task = self.factory.build_inital_task(message.text)
                
                final_text = ""

                async for event in team.run_stream(task=task):
                    if type(event).__name__ != 'TaskResult':
                        continue
                        
                    if not getattr(event, "messages", None):
                        continue

                    final_chat_message: BaseChatMessage | None = None
                    for item in reversed(event.messages):
                        if isinstance(item, BaseChatMessage):
                            final_chat_message = item
                            break
                    
                    final_text = self._message_to_text(final_chat_message)

                session.team_state = await team.save_state()

            outbound_events.append(
                OutboundEvent(
                    type="message",
                    content=final_text or "Task completed.",
                    session_id=session_id,
                    run_id=run_id,
                    source="team",
                    trace=message.trace_id,
                    metadata={
                        "channel": message.channel,
                        "is_first_turn": is_first_turn,
                    }
                )
            )

        except Exception as exc:
            outbound_events.append(
                OutboundEvent(
                    type="erorr",
                    content=str(exc),
                    session_id=session_id,
                    run_id=run_id,
                    source="team",
                    trace=message.trace_id,
                    metadata={
                        "channel": message.channel,
                        "is_first_turn": is_first_turn,
                    }
                )
            )

        finally:
            await self._close_client(client)
        
        return outbound_events