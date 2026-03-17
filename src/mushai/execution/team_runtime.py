from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Mapping
from uuid import uuid4

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    BaseChatMessage,
    CodeExecutionEvent,
    CodeGenerationEvent,
    MultiModalMessage,
    SelectSpeakerEvent,
    ThoughtEvent,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    UserInputRequestedEvent,
)

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
    
    def _short_text(self, text: str, limit: int = 160) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."
    
    def _event_to_outbound(
        self,
        event: Any,
        *,
        session_id: str,
        run_id: str,
        trace_id: str | None,
    ) -> OutboundEvent | None:
        source = getattr(event, "source", "team")

        if isinstance(event, SelectSpeakerEvent):
            selected = ", ".join(event.content)
            return OutboundEvent(
                type="agent_selected",
                content=f"{source} selected: {selected}",
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"selected_agents": event.content},
            )
        
        if isinstance(event, ThoughtEvent):
            return OutboundEvent(
                type="thinking",
                content=self._short_text(event.content),
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
            )
        
        if isinstance(event, ToolCallRequestEvent):
            tool_names = [call.name for call in event.content]
            return OutboundEvent(
                type="tool_call",
                content=f"Calling tools: {', '.join(tool_names)}",
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"tool_names": tool_names},
            )
        
        if isinstance(event, ToolCallExecutionEvent):
            tool_names = [result.name for result in event.content]
            return OutboundEvent(
                type="tool_result",
                content=f"Tool result: {', '.join(tool_names)}",
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"tool_names": tool_names}
            )
        
        if isinstance(event, CodeGenerationEvent):
            return OutboundEvent(
                type="code_generation",
                content=self._short_text(event.content),
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"code_block_count": len(event.code_blocks)}
            )
        
        if isinstance(event, CodeExecutionEvent):
            output = self._short_text(event.result.output)
            return OutboundEvent(
                type="code_execution",
                content=output or "Code executed.",
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"exit_code": event.result.exit_code}
            )

        if isinstance(event, UserInputRequestedEvent):
            return OutboundEvent(
                type="user_input_requested",
                content="Human input requested.",
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
                metadata={"request_id": event.request_id},
            )
        
        if isinstance(event, BaseChatMessage):
            return OutboundEvent(
                type="agent_message",
                content=self._short_text(self._message_to_text(event)),
                session_id=session_id,
                run_id=run_id,
                source=source,
                trace_id=trace_id,
            )
        
        return None
 
    async def _close_client(self, client: Any) -> None:
        close_method = getattr(client, "close", None)
        if not callable(close_method):
            return

        result = close_method()
        if inspect.isawaitable(result):
            await result

    async def run_stream(self, message: InboundMessage) -> AsyncGenerator[OutboundEvent, None]:
        session_id = message.session_id or str(uuid4())
        run_id = str(uuid4())
        session = self._ensure_session(session_id)

        client = self.factory.create_model_client()
        executor = self.factory.create_code_executor()
        
        is_first_turn = session.team_state is None

        yield OutboundEvent(
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

        try:
            async with executor as code_executor:
                team = self.factory.build_team(
                    client=client,
                    code_executor=code_executor,
                )

                if session.team_state is not None:
                    await team.load_state(session.team_state)
                    task = self.factory.build_followup_task(message.text)
                else:
                    task = self.factory.build_initial_task(message.text)
                
                final_text = ""

                async for event in team.run_stream(
                    task=task,
                    output_task_messages=False,
                ):
                    if isinstance(event, TaskResult):
                        if not getattr(event, "messages", None):
                            continue

                        final_chat_message: BaseChatMessage | None = None
                        for item in reversed(event.messages):
                            if isinstance(item, BaseChatMessage):
                                final_chat_message = item
                                break
                        
                        final_text = self._message_to_text(final_chat_message)
                    
                    outbound = self._event_to_outbound(
                        event,
                        session_id=session_id,
                        run_id=run_id,
                        trace_id=message.trace_id,
                    )
                    if outbound is not None:
                        yield outbound
                    
                session.team_state = await team.save_state()

                yield OutboundEvent(
                    type="final_message",
                    content=final_text or "Task completed.",
                    session_id=session_id,
                    run_id=run_id,
                    source="team",
                    trace_id=message.trace_id,
                    metadata={
                        "channel": message.channel,
                        "is_first_turn": is_first_turn,
                    },
                )

        except Exception as exc:
            yield OutboundEvent(
                type="error",
                content=str(exc),
                session_id=session_id,
                run_id=run_id,
                source="runtime",
                trace_id=message.trace_id,
                metadata={
                    "channel": message.channel,
                    "is_first_turn": is_first_turn,
                },
            )
        
        finally:
            await self._close_client(client)
    
    async def run(self, message: InboundMessage) -> list[OutboundEvent]:
        events: list[OutboundEvent] = []
        async for event in self.run_stream(message):
            events.append(event)
        return events