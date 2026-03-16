from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]

ENV_CANDIDATES = (
    ROOT_DIR / "config" / ".env",
    ROOT_DIR / ".env"
)


def _load_env_files() -> None:
    for env_path in ENV_CANDIDATES:
        if env_path.exists():
            load_dotenv(override=False)

def _first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]

def _resolve_path(raw_value: str, *, base_dir: Path = ROOT_DIR) -> Path:
    raw_path = Path(raw_value)
    if raw_path.is_absolute():
        return raw_path
    return (base_dir / raw_path).resolve()

def _default_prompts_file() -> Path:
    return _first_existing_path(
        ROOT_DIR / "config" / "prompts" / "system" / "magnetic_one.yml",
        ROOT_DIR / "config" / "prompts" / "magnetic_one.yml"
    )


_load_env_files()


@dataclass(frozen=True, slots=True)
class Settings:
    project_name: str
    root_dir: Path
    openai_api_key: str | None
    model_name: str
    model_base_url: str
    magnetic_prompts_file: Path
    code_executor_mode: str
    code_executor_image: str
    workspace_dir: Path
    team_max_turns: int
    hil_mode: bool
    hil_timeout_seconds: int


    @classmethod
    def from_env(cls) -> "Settings":
        prompts_value = os.getenv("MAGNETIC_PROMPTS_FILE")
        prompts_file = (
            _resolve_path(prompts_value)
            if prompts_value
            else _default_prompts_file.resolve()
        )

        workspace_value = os.getenv("WORKSPACE_DIR", ".magnetic_workspace")
        workspace_dir = _resolve_path(workspace_value)

        return cls(
            project_name=os.getenv("PROJECT_NAME", "MushAI"),
            root_dir=ROOT_DIR,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_name=os.getenv("MODEL_NAME", "gpt-5"),
            model_base_url=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"),
            magnetic_prompts_file=prompts_file,
            code_executor_mode=os.getenv("CODE_EXECUTOR_MODE", "docker").strip().lower(),
            code_executor_image=os.getenv("CODE_EXECUTOR_IMAGE", "autogen-custom-python"),
            workspace_dir=workspace_dir,
            team_max_turns=int(os.getenv("TEAM_MAX_TURNS", "12")),
            team_max_stalls=int(os.getenv("TEAM_MAX_STALLS", "2")),
            code_execution_timeout_seconds=int(
                os.getenv("CODE_EXECUTION_TIMEOUT_SECONDS", "90")
            ),
            hil_mode=os.getenv("HIL_MODE", "false").strip().lower() in {"1", "true", "yes", "on"},
            hil_timeout_seconds=int(os.getenv("HIL_TIMEOUT_SECONDS", "300")),

        )
    
    @property
    def use_docker_executor(self) -> bool:
        return self.code_executor_mode == "docker"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()