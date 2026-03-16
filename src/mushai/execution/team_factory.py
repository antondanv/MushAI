from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml
from autogen_agentchat.agents import ApprovalResponse, CodeExecutorAgent, UserProxyAgent
from autogen_agentchat.teams import MagenticOneGroupChat
from autogen_ext.agents.file_surfer import FileSurfer
from autogen_ext.agents.magentic_one import MagenticOneCoderAgent
from autogen_ext.agents.web_surfer import MultimodalWebSurfer
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from autogen_ext.models.openai import OpenAIChatCompletionClient

from mushai.settings.config import Settings, get_settings

DEFAULT_PROMPT_RULES = [
    "STRICT AUTONOMY: Do not ask the user to choose between options if a reasonable default exists. Make the best practical choice and proceed.",
    "NO CLARIFICATION LOOPS: If some non-critical detail is missing, continue with a sensible assumption instead of stalling.",
    "WORKDIR AWARENESS: Before creating or modifying files, inspect the current working directory and understand where artifacts will be saved.",
    "FILE WORKFLOW: You may inspect, create, and update files using file tools and terminal commands when needed.",
    "FILE VERIFICATION: After creating or updating files, verify the result before claiming success.",
    "SAVE RESULTS: If the task produces artifacts, save them with explicit filenames and mention the verified paths in the final answer.",
    "DEPENDENCY MANAGEMENT: If a third-party library is required, install it first and then retry execution.",
    "KEEP IT SHORT: Finish the task once the useful result is ready and return a concise final answer.",
    "LOCALIZATION: If the user writes in a non-English language, respond in that language.",
]


class MagneticTeamFactory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def load_prompt_rules(self) -> list(str):
        prompts_file = self.settings.magnetic_prompts_file
        if not prompts_file.exists():
            return DEFAULT_PROMPT_RULES
        
        try:
            payload = yaml.safe_load(prompts_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return DEFAULT_PROMPT_RULES
        
        prompt_rules = payload.get("prompt_rules")
        if not isinstance(prompt_rules, list):
            return DEFAULT_PROMPT_RULES

        cleaned_rules = [str(rule).strip for rule in prompt_rules if str(rule).strip()]

        return cleaned_rules or DEFAULT_PROMPT_RULES
    
    def build_inital_task(self, user_text: str) -> str:
        rules = self.load_prompt_rules()
        numbered_rules = "\n".join(
            f"{index}, {rule}" for index, rule in enumerate(rules, start=1)
        )
        return (
            f"Task: {user_text}\n\n"
            "CRITICAL EXCECUTION CONSTRAINS:\n"
            f"{numbered_rules}\n"
        )
    
    def buid_followup_task(self, user_text: str) -> str:
        return user_text.strip()
    
    def create_model_client(self) -> OpenAIChatCompletionClient:
        client_kwargs = dict[str, Any] = {
            "model": self.settings.model_name,
            "base_url": self.settings.model_base_url,
            "max_retries": 5,
        }

        if self.settings.openai_api_key:
            client_kwargs["api_key"] = self.settings.openai_api_key
        
        return OpenAIChatCompletionClient(**client_kwargs)
    
    def create_code_executor(self):
        work_dir = self.settings.workspace_dir
        work_dir.mkdir(parents=True, exist_ok=True)

        if self.settings.code_executor_mode == "local":
            return LocalCommandLineCodeExecutor(work_dir)
        
        if self.settings.code_executor_image != "docker":
            raise RuntimeError("CODE_EXECUTOR_MODE must be either 'docker' or 'local'.")
        
        try:
            from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
        except Exception as exc:
            raise RuntimeError(
                "Docker executor is unavailable. Install the docker dependency and ensure Docker Engine is running."
            ) from exc
        
        return DockerCommandLineCodeExecutor(
            image=self.settings.code_executor_image,
            work_dir=work_dir,
            bind_dir=work_dir,
            timeout=self.settings.code_execution_timeout_seconds,
        )
    
    def approval_func(self, request: Any) -> ApprovalResponse:
        if not self.settings.hil_mode:
            return ApprovalResponse(
                approved=True,
                 reason="Approved automatically because HIL mode is disabled.", 
            )
        
        print("\n=== Human Approval Required ===")
        print(f"Reason: {getattr(request, 'reason', 'Code execution request')}")
        print(f"Code:\n{getattr(request, 'code', '')}")
        answer = input("Approve execution? [y/N]: ").strip().lower()

        approved = answer in {"y", "yes"}
        return ApprovalResponse(
            approved=approved,
            reason="Approved by human." if approved else "Rejected by human.",
        )
    
    def defualt_input_func(self, prompt: str = "") -> str:
        if not self.settings.hil_mode:
            raise RuntimeError("User input was requested, but HIL mode is disabled.")
        return input(prompt or "Your answer > ")
    
    def build_team(self, client: OpenAIChatCompletionClient, code_executor: Any, input_func: Callable[[str], str] | None = None) -> MagenticOneGroupChat:
        file_surfer = FileSurfer(
            "FileSurfer",
            model_client=client,
            base_path=str(self.settings.root_dir)
        )

        web_surfer = MultimodalWebSurfer(
            "WebSurfer",
            model_client=client,
            start_page="https://duckduckgo.com/",
            headless=True
        )
        
        coder = MagenticOneCoderAgent(
            "Coder",
            model_client=client
        )

        terminal = CodeExecutorAgent(
            "ComputerTerminal",
            code_executor=code_executor,
            approval_func=self.approval_func
        )

        participants = [file_surfer, web_surfer, coder, terminal]

        if self.settings.hil_mode:
            participants.append(
                UserProxyAgent(
                    "User",
                    input_func=input_func or self.defualt_input_func
                )
            )

        return MagenticOneGroupChat(
            participants,
            model_client=client,
            max_turns=self.settings.team_max_turns,
            max_stalls=self.settings.team_max_stalls
        )