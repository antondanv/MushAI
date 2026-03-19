from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mushai.execution.team_factory import MagneticTeamFactory
from mushai.execution.team_runtime import TeamRuntime
from mushai.schemas.inbound import InboundMessage


class FakeClient:
    async def close(self) -> None:
        return None


class FakeExecutor:
    async def __aenter__(self) -> "FakeExecutor":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakeTeam:
    def __init__(self) -> None:
        self.loaded_state: dict[str, Any] | None = None
        self.history: list[str] = []

    async def load_state(self, state: dict[str, Any]) -> None:
        self.loaded_state = state
        self.history = list(state.get("history", []))

    async def save_state(self) -> dict[str, Any]:
        return {"history": list(self.history)}

    async def run_stream(self, task: str, output_task_messages: bool = False):
        self.history.append(task)
        joined = " | ".join(self.history)
        yield TextMessage(content=f"history={joined}", source="team")
        yield TaskResult(
            messages=[TextMessage(content=f"final={joined}", source="team")]
        )


class FakeFactory(MagneticTeamFactory):
    def __init__(self) -> None:
        self.teams: list[FakeTeam] = []

    def create_model_client(self) -> FakeClient:
        return FakeClient()

    def create_code_executor(self) -> FakeExecutor:
        return FakeExecutor()

    def build_initial_task(self, user_text: str) -> str:
        return f"initial::{user_text}"

    def build_followup_task(self, user_text: str) -> str:
        return f"followup::{user_text}"

    def build_team(self, client: Any, code_executor: Any, input_func: Any = None) -> FakeTeam:
        team = FakeTeam()
        self.teams.append(team)
        return team


class TeamRuntimeStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_followup_turn_uses_loaded_team_state(self) -> None:
        factory = FakeFactory()
        runtime = TeamRuntime(factory=factory)

        first_events = [
            event
            async for event in runtime.run_stream(
                InboundMessage(text="first", session_id="session-1")
            )
        ]

        self.assertEqual(first_events[-1].type, "final_message")
        self.assertEqual(first_events[-1].content, "final=initial::first")
        self.assertIsNone(factory.teams[0].loaded_state)
        self.assertEqual(
            runtime._sessions["session-1"].team_state,
            {"history": ["initial::first"]},
        )

        second_events = [
            event
            async for event in runtime.run_stream(
                InboundMessage(text="second", session_id="session-1")
            )
        ]

        self.assertEqual(factory.teams[1].loaded_state, {"history": ["initial::first"]})
        self.assertEqual(
            factory.teams[1].history,
            ["initial::first", "followup::second"],
        )
        self.assertEqual(second_events[-1].type, "final_message")
        self.assertEqual(
            second_events[-1].content,
            "final=initial::first | followup::second",
        )


if __name__ == "__main__":
    unittest.main()
