from __future__ import annotations

from mushai.execution.team_runtime import TeamRuntime
from mushai.schemas.inbound import InboundMessage

EXIT_COMMANDS = {"exit", "quit", "q", "выход"}

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

        events = await runtime.run(message)

        if events:
            session_id = events[0].session_id

        for event in events:
            if event.type == "status":
                print(f"[status] {event.content}")
            elif event.type == "message":
                print(f"\n[assistant] {event.content}")
            elif event.type == "error":
                print(f"\n[error] {event.content}")
            else:
                print(f"\n[{event.type}] {event.content}")
