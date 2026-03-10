import asyncio
import os
from pathlib import Path
import yaml

from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient

from langchain_community.utilities import GoogleSerperAPIWrapper
from modules.telegram_bot import TelegramBot

from creator import Creator

# from tool_registry import render_tool_catalog_text

# === Setup ===
load_dotenv(dotenv_path="config/.env", override=True)

def load_config(path: str = "config/prompts/chief_agents.yml") -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

base_url = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
telegram_bot = TelegramBot()
pmt_cfg = load_config(os.getenv("PROMPTS_FILE", "config/prompts/chief_agents.yml"))

# === Tools ===
async def web_search(query: str, num_results: int = 5) -> str:
    """Find information on the web"""
    search = GoogleSerperAPIWrapper(k=max(1, min(int(num_results), 10)))
    return search.run(query)

async def send_telegram_message(text: str) -> str:
    """Send message in Telegram (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are already set in .env)"""
    return await telegram_bot.send_telegram_message(text)

tool_registry = {
    "web_search": web_search,
    "send_telegram_message": send_telegram_message,
}

# === Setup Agents ===

# model_client = OpenAIChatCompletionClient(
#     model="gpt-5-nano",
#     base_url=base_url,
# )

a_cfg = pmt_cfg["agents"]["assistant"]
agent = AssistantAgent(
    name="assistant",
    model_client=OpenAIChatCompletionClient(model=a_cfg["model"], temperature=a_cfg["params"]["temperature"], base_url=base_url),
    tools=[tool_registry[t] for t in a_cfg.get("tools", [])],
    system_message=a_cfg["system_message"],
    reflect_on_tool_use=True,
    )
# c_cfg = pmt_cfg["agents"]["critic"]
# critic_agent = AssistantAgent(
#     name="critic",
#     model_client=OpenAIChatCompletionClient(model=c_cfg["model"], temperature=c_cfg["params"]["temperature"], base_url=base_url),
#     system_message=c_cfg["system_message"],
# )

user_proxy = UserProxyAgent(
    name="user_proxy",
    input_func=input
)

# === Run Function ===

async def main() -> None:
    result = await agent.run(task="Отправь текущий курс доллара к рублю в телеграмм")
    print(result.messages[-1].content)

async def assistant_run_stream() -> None:
    # Option 1: read each message from the stream (as shown in the previous example).
    # async for message in agent.run_stream(task="Find information on AutoGen"):
    #     print(message)
    text_termination = TextMentionTermination("APPROVE")
    team = RoundRobinGroupChat([agent], termination_condition=text_termination)
    # Option 2: use Console to print all messages as they appear.
    response = await Console(
        team.run_stream(task="" \
        "Отправь мне в телеграмм отдельными сообщениями теущий курс доллара, юаня и евро к рублю"),
        output_stats=True,  # Enable stats printing.
    )

    print("\n\n === Final response ===")
    print(response.messages[-1].content)

async def run_team() -> None:
    text_termination = TextMentionTermination("APPROVE")

    # Create a team with the primary and critic agents.
    team = RoundRobinGroupChat([agent, user_proxy], termination_condition=text_termination)
    result = await team.run(task="Отправь мне в телеграмм отдельными сообщениями теущий курс доллара, юаня и евро к рублю", max_iterations=3)
    print(result)
    print(result.messages[-1].content)


# === Run ===
if __name__ == "__main__":
    # asyncio.run(main())
    asyncio.run(assistant_run_stream())
    # asyncio.run(run_team())
