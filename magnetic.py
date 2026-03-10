import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import yaml
from autogen_agentchat.agents import ApprovalResponse, CodeExecutorAgent, UserProxyAgent
from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.agents.file_surfer import FileSurfer
from autogen_ext.agents.magentic_one import MagenticOneCoderAgent
from autogen_ext.agents.web_surfer import MultimodalWebSurfer
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from autogen_ext.models.openai import OpenAIChatCompletionClient
import warnings
warnings.filterwarnings("ignore", module="pydantic")

# === Setup (same style as chief.py) ===
load_dotenv(dotenv_path="config/.env", override=True)

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
CODE_EXECUTOR_MODE = os.getenv("CODE_EXECUTOR_MODE", "docker").strip().lower()
CODE_EXECUTOR_IMAGE = os.getenv("CODE_EXECUTOR_IMAGE", "python:3.12-slim")
MAGNETIC_PROMPTS_FILE = os.getenv("MAGNETIC_PROMPTS_FILE", "config/prompts/magnetic_one.yml")

DEFAULT_PROMPT_RULES = [
    "STRICT AUTONOMY: Do NOT ask the user or other agents for preferences, permissions, credentials, or to choose between options (e.g., do NOT offer 'Option A vs Option B'). Make a reasonable default choice and execute it immediately.",
    "NO CLARIFICATION LOOPS: If an agent requires a specific API key or URL that is not available, immediately pivot to a free, publicly accessible alternative (e.g., search via DuckDuckGo, open a public news/finance site, use a free unauthenticated endpoint) without asking for input.",
    "WEBSURFER RULES: Actively search for the information or navigate directly to trusted public websites. Extract the data and report back. Do not wait for exact URLs to be provided.",
    "CAPTCHA/BLOCK FALLBACK: If WebSurfer hits a CAPTCHA or gets blocked, stop browsing immediately. Switch to Coder. Coder must write a short Python script using libraries like 'requests', 'urllib', or specialized packages (e.g., 'yfinance' for financial data) to fetch the answer, and ComputerTerminal must execute it.",
    "DEPENDENCY MANAGEMENT: If you need a third-party Python library, first execute a `sh` code block with `pip install <package_name>`, then run Python code that imports it. If ModuleNotFoundError appears, install the missing package immediately and retry.",
    "WORKDIR AWARENESS: Before creating/modifying files, run `pwd` and inspect the directory (`ls -la`) so you know the exact current working directory.",
    "FILE WORKFLOW: You are allowed to inspect, create, and update files. Use FileSurfer and terminal commands (`ls`, `find`, `cat`) to inspect directories/files, and use shell or Python (`Path(...).write_text`) to create/save files.",
    "FILE VERIFICATION: After creating/updating any file, verify it exists with shell checks (for example `test -f <file>` and `ls -l <file>`) and show a short preview (`head` or `cat`). If verification fails, fix and re-verify before claiming success.",
    "SAVE RESULTS: If the task requires artifacts (scripts, reports, data files), save them with explicit filenames in the current working directory and include verified paths in the final answer.",
    "KEEP IT SHORT: Terminate the task and provide the final concise answer to the user as soon as the data is successfully retrieved.",
    "LOCALIZATION: If the user writes in their own language, not English, then you also do everything and respond in their language.",
]


def _load_prompt_rules() -> list[str]:
    path = Path(MAGNETIC_PROMPTS_FILE)
    if not path.exists():
        return DEFAULT_PROMPT_RULES

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_PROMPT_RULES

    rules = data.get("prompt_rules")
    if not isinstance(rules, list):
        return DEFAULT_PROMPT_RULES

    cleaned_rules = [str(rule).strip() for rule in rules if str(rule).strip()]
    return cleaned_rules or DEFAULT_PROMPT_RULES


PROMPT_RULES = _load_prompt_rules()


def read_task() -> str:
    print("Enter task for Magentic-One and press Enter:")
    task = input("> ").strip()
    if not task:
        raise RuntimeError("Task is empty")
    return task


def approval_func(_request):
    return ApprovalResponse(approved=True, reason="Always approved by script")


def build_task(task: str) -> str:
    numbered_rules = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(PROMPT_RULES, start=1))
    return f"Task: {task}\n\nCRITICAL EXECUTION CONSTRAINTS (MUST FOLLOW):\n{numbered_rules}\n"

def custom_input_func(prompt: str = "") -> str:
    print("🟢 [ОЖИДАНИЕ ВВОДА]: Агентам нужна ваша помощь или уточнение!")
    return input("Ваш ответ > ")

def build_team(client, code_executor, input_func=None):
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

    user_input = input_func or custom_input_func
    participants = [file_surfer, web_surfer, coder, terminal, UserProxyAgent("User", input_func=user_input)]

    return MagenticOneGroupChat(
        participants,
        model_client=client,
        max_turns=12,
        max_stalls=2,
    )


def make_code_executor(work_dir: Path):
    if CODE_EXECUTOR_MODE == "local":
        return LocalCommandLineCodeExecutor(work_dir=work_dir)

    if CODE_EXECUTOR_MODE != "docker":
        raise RuntimeError("CODE_EXECUTOR_MODE must be 'docker' or 'local'")

    try:
        from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
    except Exception as exc:
        raise RuntimeError(
            "Docker executor is unavailable. Install dependency `docker` and ensure Docker Engine is running."
        ) from exc

    return DockerCommandLineCodeExecutor(
        image=CODE_EXECUTOR_IMAGE,
        work_dir=work_dir,
        bind_dir=work_dir,
        timeout=90,
    )


async def run_once(client, task: str) -> None:
    work_dir = Path(".magentic_workspace").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    executor = make_code_executor(work_dir=work_dir)
    
    async with executor as code_executor:
        team = build_team(client=client, code_executor=code_executor)
        
        print("\n--- Начало выполнения задачи ---")
        
        async for message in team.run_stream(task=task):
            # 1. ЛОВИМ ФИНАЛЬНЫЙ ОТВЕТ
            if type(message).__name__ == "TaskResult":
                print("\n" + "="*50)
                print("🎯 ФИНАЛЬНЫЙ ОТВЕТ СИСТЕМЫ:")
                # Достаем последнее содержательное сообщение из списка
                if message.messages:
                    final_text = message.messages[-1].content
                    if isinstance(final_text, list):
                        final_text = " ".join([str(item) for item in final_text if isinstance(item, str)])
                    print(final_text)
                print("="*50 + "\n")
                continue

            # 2. ОБРАБАТЫВАЕМ ПРОМЕЖУТОЧНЫЕ ШАГИ (краткий лог)
            if not hasattr(message, 'source'):
                continue
                
            source = message.source
            text_content = ""
            
            if hasattr(message, 'content'):
                if isinstance(message.content, str):
                    text_content = message.content
                elif isinstance(message.content, list):
                    text_content = " ".join([str(item) for item in message.content if isinstance(item, str)])
            
            if text_content:
                clean_text = " ".join(text_content.split())
                # Оставляем только первые 100 символов для компактности
                if len(clean_text) > 100:
                    clean_text = clean_text[:100] + "..."
                
                print(f"🔹 [{source}]: {clean_text}")


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
