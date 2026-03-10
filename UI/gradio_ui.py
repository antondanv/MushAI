from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import time
from typing import Any

import gradio as gr
from autogen_core import CancellationToken

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
STOP_SENTINEL = "__STOP__"


def _new_session_state() -> dict[str, Any]:
    return {
        "running": False,
        "awaiting_input": False,
        "events": None,
        "input_queue": None,
        "stop_event": None,
        "progress": [],
    }


def _ensure_session_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return _new_session_state()
    merged = _new_session_state()
    merged.update(state)
    return merged


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
        content = _content_to_text(item.get("content", "")).strip()
        if not content:
            continue
        if role == "assistant" and ("<thinking>" in content or content.startswith("Думаю...")):
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    return "\n".join(lines)


def _worker_run_magentic(
    user_text: str,
    context: str,
    events_q: Queue[tuple[str, Any]],
    input_q: Queue[str],
    stop_event: threading.Event,
) -> None:
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

        def ui_input_func(prompt: str = "") -> str:
            events_q.put(("input_request", prompt))
            while True:
                if stop_event.is_set():
                    raise RuntimeError("Остановлено пользователем.")
                try:
                    value = input_q.get(timeout=0.2)
                except Empty:
                    continue
                if value == STOP_SENTINEL:
                    raise RuntimeError("Остановлено пользователем.")
                return value

        final_text = ""
        progress_lines: list[str] = []
        cancellation = CancellationToken()

        async with executor as code_executor:
            team = build_team(client=client, code_executor=code_executor, input_func=ui_input_func)
            async for event in team.run_stream(task=full_task, cancellation_token=cancellation):
                if stop_event.is_set():
                    cancellation.cancel()
                    raise RuntimeError("Остановлено пользователем.")

                line = _format_event(event)
                if line is not None and (not progress_lines or progress_lines[-1] != line):
                    progress_lines.append(line)
                    events_q.put(("progress", list(progress_lines)))

                if type(event).__name__ != "TaskResult":
                    continue
                if not getattr(event, "messages", None):
                    continue
                final_text = _content_to_text(event.messages[-1].content).strip()

        events_q.put(("done", (final_text, list(progress_lines))))

    try:
        import asyncio

        asyncio.run(_run())
    except Exception as exc:
        msg = str(exc)
        if "Остановлено пользователем" in msg:
            events_q.put(("stopped", None))
        else:
            events_q.put(("error", msg))
    finally:
        events_q.put(("end", None))


def _close_session(state: dict[str, Any]) -> dict[str, Any]:
    state["running"] = False
    state["awaiting_input"] = False
    state["events"] = None
    state["input_queue"] = None
    state["stop_event"] = None
    state["progress"] = []
    return state


def _stream_events(history: list[dict[str, str]], state: dict[str, Any]):
    events_q: Queue[tuple[str, Any]] | None = state.get("events")
    if events_q is None:
        yield history, "", state
        return

    last_emit = time.time()
    while True:
        try:
            kind, payload = events_q.get(timeout=1.0)
        except Empty:
            if time.time() - last_emit > 5:
                yield history, "", state
                last_emit = time.time()
            continue

        if kind == "progress":
            progress_lines = payload
            state["progress"] = progress_lines
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = _render_thinking_block(progress_lines)
            yield history, "", state
            last_emit = time.time()
            continue

        if kind == "input_request":
            state["awaiting_input"] = True
            prompt = (payload or "Нужно уточнение").strip()
            thinking = _render_thinking_block(state.get("progress", []))
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = (
                    f"{thinking}\n\n"
                    f"Нужно уточнение от пользователя:\n{prompt}\n\n"
                    "Напишите ответ в поле ниже и отправьте сообщение."
                )
            yield history, "", state
            return

        if kind == "done":
            final_text, progress_lines = payload
            thinking = _render_thinking_block(progress_lines)
            answer = final_text or "Не удалось получить финальный ответ."
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = f"{thinking}\n\n{answer}"
            state = _close_session(state)
            yield history, "", state
            return

        if kind == "stopped":
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = "Генерация остановлена пользователем."
            state = _close_session(state)
            yield history, "", state
            return

        if kind == "error":
            if history and history[-1].get("role") == "assistant":
                history[-1]["content"] = f"Ошибка: {payload}"
            state = _close_session(state)
            yield history, "", state
            return

        if kind == "end":
            if state.get("running"):
                state = _close_session(state)
                yield history, "", state
            return


def chat_with_magentic(message: str, history: list[dict[str, str]], session_state: dict[str, Any]):
    state = _ensure_session_state(session_state)
    history = history or []
    user_text = (message or "").strip()

    if not user_text:
        yield history, "", state
        return

    if state.get("running") and state.get("awaiting_input"):
        history = history + [{"role": "user", "content": user_text}]
        input_q: Queue[str] | None = state.get("input_queue")
        if input_q is not None:
            input_q.put(user_text)
        state["awaiting_input"] = False
        yield history, "", state
        yield from _stream_events(history, state)
        return

    if state.get("running") and not state.get("awaiting_input"):
        history = history + [
            {
                "role": "assistant",
                "content": "Сейчас уже выполняется предыдущая задача. Нажмите Stop или дождитесь завершения.",
            }
        ]
        yield history, "", state
        return

    context = _history_context(history)
    history = history + [{"role": "user", "content": user_text}]
    history = history + [{"role": "assistant", "content": _render_thinking_block([])}]

    events_q: Queue[tuple[str, Any]] = Queue()
    input_q: Queue[str] = Queue()
    stop_event = threading.Event()

    state["running"] = True
    state["awaiting_input"] = False
    state["events"] = events_q
    state["input_queue"] = input_q
    state["stop_event"] = stop_event
    state["progress"] = []

    worker = threading.Thread(
        target=_worker_run_magentic,
        args=(user_text, context, events_q, input_q, stop_event),
        daemon=True,
    )
    worker.start()

    yield history, "", state
    yield from _stream_events(history, state)


def stop_generation(history: list[dict[str, str]], session_state: dict[str, Any]):
    state = _ensure_session_state(session_state)
    history = history or []

    if not state.get("running"):
        return history, state

    stop_event: threading.Event | None = state.get("stop_event")
    if stop_event is not None:
        stop_event.set()

    input_q: Queue[str] | None = state.get("input_queue")
    if input_q is not None:
        input_q.put(STOP_SENTINEL)

    if history and history[-1].get("role") == "assistant":
        history[-1]["content"] = "Останавливаю генерацию..."
    else:
        history = history + [{"role": "assistant", "content": "Останавливаю генерацию..."}]

    return history, state


def clear_chat():
    return "", [], _new_session_state()


with gr.Blocks(title="Magentic-One Chat") as demo:
    gr.Markdown("## Magentic-One Chat")
    chatbot = gr.Chatbot(
        height=620,
        layout="bubble",
        buttons=["copy", "copy_all"],
        reasoning_tags=[("<thinking>", "</thinking>")],
    )
    session_state = gr.State(_new_session_state())

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Напишите сообщение...",
            lines=1,
            scale=8,
            container=False,
        )
        send_btn = gr.Button("Отправить", variant="primary", scale=1)
        stop_btn = gr.Button("Stop", variant="stop", scale=1)

    clear_btn = gr.Button("Очистить")

    msg.submit(chat_with_magentic, inputs=[msg, chatbot, session_state], outputs=[chatbot, msg, session_state])
    send_btn.click(chat_with_magentic, inputs=[msg, chatbot, session_state], outputs=[chatbot, msg, session_state])
    stop_btn.click(stop_generation, inputs=[chatbot, session_state], outputs=[chatbot, session_state])
    clear_btn.click(clear_chat, outputs=[msg, chatbot, session_state])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        show_error=True,
        inbrowser=False,
        server_name="127.0.0.1",
        server_port=7860,
        strict_cors=False,
    )
