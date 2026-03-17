from __future__ import annotations

from mushai.execution.team_runtime import TeamRuntime
from mushai.schemas.inbound import InboundMessage
from mushai.schemas.outbound import OutboundEvent

EXIT_COMMANDS = {"exit", "quit", "q", "выход"}

def _render_event(event: OutboundEvent) -> str:
    if event.type == "status":
        return f"[status] {event.content}"
    
    if event.type == "agent_selected":
        return f"[selected] {event.content}"
    
    if event.type == "thinking":
        return f"[thinking] {event.source}: {event.content}"
    
    if event.type == "agent_message":
        return f"[agent:{event.source}] {event.content}"
    
    if event.type == "tool_call":
        return f"[tool_call] {event.source}: {event.content}"
    
    if event.type == "tool_result":
        return f"[tool_result] {event.source}: {event.content}"
    
    if event.type == "code_generation":
        return f"[code_generation] {event.source}: {event.content}"
    
    if event.type == "code_execution":
        exit_code = event.metadata.get("exit_code")
        suffix = f" (exit={exit_code})" if exit_code is not None else ""
        return f"[code_execution] {event.source}{suffix}: {event.content}"

    if event.type == "user_input_requested":
        return f"[hil] {event.content}"
    
    if event.type == "final_message":
        return f"\n[assistant] {event.content}"
    
    if event.type == "error":
        return f"\n[error] {event.content}"
    
    return f"[{event.type}] {event.source}: {event.content}"

async def run_cli() -> None:
    runtime = TeamRuntime()
    session_id: str | None = None

    print("=" * 50)
    print("MushAI CLI is ready")
    print("Type 'exit' to quit")
    print("=" * 50)

    while True:
        try:
            user_text = input("\nYour task > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            break

        if not user_text:
            continue

        if user_text.lower() in EXIT_COMMANDS:
            print("Shutting down...")
            break

        message = InboundMessage(
            text=user_text,
            channel="cli",
            session_id=session_id,
        )

        async for event in runtime.run_stream(message):
            if session_id is None:
                session_id = event.session_id
            print(_render_event(event))
