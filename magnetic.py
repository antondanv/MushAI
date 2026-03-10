import asyncio
import os
import sys
from pathlib import Path

# Make ffmpeg visible before autogen imports (pydub checks during import time).
TOOLS_DIR = (Path(__file__).resolve().parent / ".tools").resolve()
if (TOOLS_DIR / "ffmpeg.exe").exists():
    os.environ["PATH"] = f"{TOOLS_DIR}{os.pathsep}{os.environ.get('PATH', '')}"

# Windows: selector event loop avoids noisy subprocess transport destructor errors.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from autogen_agentchat.agents import ApprovalResponse, CodeExecutorAgent, UserProxyAgent
from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.agents.file_surfer import FileSurfer
from autogen_ext.agents.magentic_one import MagenticOneCoderAgent
from autogen_ext.agents.web_surfer import MultimodalWebSurfer
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from autogen_ext.models.openai import OpenAIChatCompletionClient

# === Setup (same style as chief.py) ===
load_dotenv(dotenv_path="config/.env", override=True)

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")


def read_task() -> str:
    print("Enter task for Magentic-One and press Enter:")
    task = input("> ").strip()
    if not task:
        raise RuntimeError("Task is empty")
    return task


def approval_func(_request):
    return ApprovalResponse(approved=True, reason="Always approved by script")


def build_task(task: str) -> str:
    return (
        f"Task: {task}\n\n"
        "CRITICAL EXECUTION CONSTRAINTS (MUST FOLLOW):\n"
        "1. STRICT AUTONOMY: Do NOT ask the user or other agents for preferences, permissions, credentials, or to choose between options (e.g., do NOT offer 'Option A vs Option B'). Make a reasonable default choice and execute it immediately.\n"
        "2. NO CLARIFICATION LOOPS: If an agent requires a specific API key or URL that is not available, immediately pivot to a free, publicly accessible alternative (e.g., search via DuckDuckGo, open a public news/finance site, use a free unauthenticated endpoint) without asking for input.\n"
        "3. WEBSURFER RULES: Actively search for the information or navigate directly to trusted public websites. Extract the data and report back. Do not wait for exact URLs to be provided.\n"
        "4. CAPTCHA/BLOCK FALLBACK: If WebSurfer hits a CAPTCHA or gets blocked, stop browsing immediately. Switch to Coder. Coder must write a short Python script using libraries like 'requests', 'urllib', or specialized packages (e.g., 'yfinance' for financial data) to fetch the answer, and ComputerTerminal must execute it.\n"
        "5. KEEP IT SHORT: Terminate the task and provide the final concise answer to the user as soon as the data is successfully retrieved.\n"
    )


def build_team(client, code_executor):
    file_surfer = FileSurfer("FileSurfer", model_client=client)
    web_surfer = MultimodalWebSurfer(
        "WebSurfer",
        model_client=client,
        start_page="https://duckduckgo.com/",
        headless=True,
    )
    coder = MagenticOneCoderAgent("Coder", model_client=client)
    terminal = CodeExecutorAgent(
        "ComputerTerminal",
        code_executor=code_executor,
        approval_func=approval_func,
    )

    participants = [file_surfer, web_surfer, coder, terminal, UserProxyAgent("User", input_func=input)]

    return MagenticOneGroupChat(
        participants,
        model_client=client,
        max_turns=12,
        max_stalls=2,
    )


async def run_once(client, task: str) -> None:
    work_dir = Path(".magentic_workspace").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    async with LocalCommandLineCodeExecutor(work_dir=work_dir) as code_executor:
        team = build_team(client=client, code_executor=code_executor)
        await Console(team.run_stream(task=task))


async def main() -> None:
    client = OpenAIChatCompletionClient(
        model=MODEL_NAME,
        base_url=MODEL_BASE_URL,
        max_retries=5,
    )

    task = build_task(read_task())
    await run_once(client=client, task=task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")