from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import time
from typing import Any

import gradio as gr

# Ensure project root is importable when launched as `python UI/gradio_ui.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from magnetic import (  # noqa: E402
    MODEL_BASE_URL,
    MODEL_NAME,
    OpenAIChatCompletionClient,
    build_task,
    build_team,
    make_code_executor,
)


MAX_LIVE_STEPS = 28


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            else:
                as_text = getattr(item, "text", None)
                if isinstance(as_text, str):
                    parts.append(as_text)
        return " ".join(parts).strip()
    return str(content) if content is not None else ""


def _short_text(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _format_event(event: Any) -> str | None:
    event_type = type(event).__name__
    source = getattr(event, "source", "?")

    if event_type == "ModelClientStreamingChunkEvent":
        return None

    if event_type == "SelectSpeakerEvent":
        speakers = getattr(event, "content", []) or []
        return f"➡️ {source} выбрал следующего: {', '.join(speakers)}"

    if event_type == "HandoffMessage":
        target = getattr(event, "target", "?")
        content = _short_text(_content_to_text(getattr(event, "content", "")), 110)
        return f"↪️ {source} -> {target}: {content}"

    if event_type == "ToolCallRequestEvent":
        calls = getattr(event, "content", []) or []
        names = [getattr(call, "name", "tool") for call in calls]
        return f"🛠️ {source} вызывает tool: {', '.join(names)}"

    if event_type == "ToolCallExecutionEvent":
        results = getattr(event, "content", []) or []
        names = [getattr(result, "name", "tool") for result in results]
        return f"✅ {source} получил результат tool: {', '.join(names)}"

    if event_type == "CodeGenerationEvent":
        blocks = getattr(event, "code_blocks", []) or []
        return f"🧠 {source} сгенерировал код ({len(blocks)} блока/ов)"

    if event_type == "CodeExecutionEvent":
        result = getattr(event, "result", None)
        exit_code = getattr(result, "exit_code", None)
        return f"▶️ {source} выполнил код (exit={exit_code})"

    if event_type == "ThoughtEvent":
        content = _short_text(_content_to_text(getattr(event, "content", "")), 100)
        return f"🤔 {source}: {content}" if content else f"🤔 {source} думает"

    if event_type in {"TextMessage", "ToolCallSummaryMessage"}:
        content = _short_text(_content_to_text(getattr(event, "content", "")))
        return f"💬 {source}: {content}" if content else None

    if event_type == "UserInputRequestedEvent":
        return f"❓ {source} запрашивает ввод пользователя"

    content = _short_text(_content_to_text(getattr(event, "content", "")))
    return f"ℹ️ {source} [{event_type}]: {content}" if content else f"ℹ️ {source} [{event_type}]"


def _trim_progress_steps(steps: list[str]) -> list[str]:
    # Hide first/last orchestration states as requested (technical noise).
    if len(steps) <= 2:
        return []
    return steps[1:-1]


def _render_thinking_block(progress_steps: list[str]) -> str:
    visible_steps = _trim_progress_steps(progress_steps)
    if not visible_steps:
        body = "Собираю контекст..."
    else:
        body = "\n".join(f"- {line}" for line in visible_steps[-MAX_LIVE_STEPS:])
    return f"<thinking>\n{body}\n</thinking>"


def _history_context(history: list[dict[str, str]], limit: int = 8) -> str:
    if not history:
        return ""
    recent = history[-limit:]
    lines: list[str] = []
    for item in recent:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "")
        content = _content_to_text(item.get("content", ""))
        content = content.strip()
        if not content:
            continue
        if role == "assistant" and content.startswith("Думаю..."):
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    return "\n".join(lines)


def _worker_run_magentic(user_text: str, context: str, q: Queue[tuple[str, Any]]) -> None:
    async def _run() -> None:
        client = OpenAIChatCompletionClient(
            model=MODEL_NAME,
            base_url=MODEL_BASE_URL,
            max_retries=5,
        )

        work_dir = Path(".magentic_workspace").resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        executor = make_code_executor(work_dir=work_dir)
        if context:
            full_task = build_task(
                "Контекст диалога:\n"
                f"{context}\n\n"
                "Текущее сообщение пользователя:\n"
                f"{user_text}"
            )
        else:
            full_task = build_task(user_text)

        final_text = ""
        progress_lines: list[str] = []
        async with executor as code_executor:
            team = build_team(client=client, code_executor=code_executor)
            async for event in team.run_stream(task=full_task):
                line = _format_event(event)
                if line is not None and (not progress_lines or progress_lines[-1] != line):
                    progress_lines.append(line)
                    q.put(("progress", list(progress_lines)))

                if type(event).__name__ != "TaskResult":
                    continue
                if not getattr(event, "messages", None):
                    continue
                final_text = _content_to_text(event.messages[-1].content).strip()

        q.put(("done", (final_text, list(progress_lines))))

    try:
        import asyncio

        asyncio.run(_run())
    except Exception as exc:
        q.put(("error", str(exc)))
    finally:
        q.put(("end", None))


def chat_with_magentic(message: str, history: list[dict[str, str]]):
    history = history or []
    user_text = (message or "").strip()
    if not user_text:
        yield history, ""
        return

    context = _history_context(history)
    history = history + [{"role": "user", "content": user_text}]
    history = history + [{"role": "assistant", "content": _render_thinking_block([])}]
    yield history, ""

    q: Queue[tuple[str, Any]] = Queue()
    worker = threading.Thread(
        target=_worker_run_magentic,
        args=(user_text, context, q),
        daemon=True,
    )
    worker.start()

    last_emit = time.time()
    while True:
        try:
            kind, payload = q.get(timeout=1.0)
        except Empty:
            # Heartbeat to keep the frontend connection alive on long steps.
            if time.time() - last_emit > 5:
                yield history, ""
                last_emit = time.time()
            continue

        if kind == "progress":
            progress_lines = payload
            history[-1]["content"] = _render_thinking_block(progress_lines)
            yield history, ""
            last_emit = time.time()
            continue

        if kind == "done":
            final_text, progress_lines = payload
            thinking = _render_thinking_block(progress_lines)
            answer = final_text or "Не удалось получить финальный ответ."
            history[-1]["content"] = f"{thinking}\n\n{answer}"
            yield history, ""
            last_emit = time.time()
            continue

        if kind == "error":
            history[-1]["content"] = f"Ошибка: {payload}"
            yield history, ""
            last_emit = time.time()
            continue

        if kind == "end":
            break


with gr.Blocks(title="Magentic-One Chat") as demo:
    gr.Markdown("## Magentic-One Chat")
    chatbot = gr.Chatbot(
        height=620,
        layout="bubble",
        buttons=["copy", "copy_all"],
        reasoning_tags=[("<thinking>", "</thinking>")],
    )

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Напишите сообщение...",
            lines=1,
            scale=8,
            container=False,
        )
        send_btn = gr.Button("Отправить", variant="primary", scale=1)

    clear_btn = gr.ClearButton([chatbot, msg], value="Очистить")

    msg.submit(chat_with_magentic, inputs=[msg, chatbot], outputs=[chatbot, msg])
    send_btn.click(chat_with_magentic, inputs=[msg, chatbot], outputs=[chatbot, msg])
    clear_btn.click(lambda: ("", []), outputs=[msg, chatbot])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        show_error=True,
        inbrowser=False,
        server_name="127.0.0.1",
        server_port=7860,
        strict_cors=False,
    )
