#!/usr/bin/env python3
"""Executo — ChatGPT-style web UI for the self-correcting code agent.

Run:
    python app.py
Then open http://127.0.0.1:7860 in your browser.
"""

from __future__ import annotations

import copy

import gradio as gr

from core.agent import DEFAULT_MAX_ATTEMPTS, stream_executo_events
from core.errors import (
    format_failure_summary,
    format_llm_error,
    format_setup_error,
)

TITLE = "Executo"
TAGLINE = (
    "Describe what you want in plain English. Executo writes Python, "
    "tests it in a sandbox, and fixes itself until it passes."
)

EXAMPLES = [
    "Write a function that checks if a string is a palindrome, ignoring spaces and case.",
    "Write a function that returns the nth Fibonacci number.",
    "Write a function that merges two sorted lists into one sorted list.",
    "Write a function that counts the vowels in a sentence.",
    "Write a function that converts a Roman numeral string to an integer.",
]

CSS = """
:root {
    --executo-page-bg: #0a0a0f;
    --executo-chat-bg: #14141f;
    --executo-chat-surface: #1a1a28;
    --executo-chat-user: #1e1b4b;
    --executo-chat-text: #e2e8f0;
    --executo-chat-heading: #f8fafc;
    --executo-chat-muted: #94a3b8;
    --executo-chat-border: #2a2a3a;
    color-scheme: dark;
}

html, body, gradio-app, #root,
.gradio-container, .app, .main, .wrap, .contain {
    background: var(--executo-page-bg) !important;
    background-color: var(--executo-page-bg) !important;
}

.gradio-container {
    max-width: 920px !important;
    margin: 0 auto !important;
}

#executo-header {
    text-align: center;
    padding: 24px 16px 12px;
}
#executo-header h1 {
    font-size: 2.25rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #6366f1, #8b5cf6, #ec4899);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 6px;
}
#executo-header p {
    color: #94a3b8;
    font-size: 0.95rem;
    max-width: 560px;
    margin: 0 auto;
    line-height: 1.55;
}

/* Chat */
.executo-chat,
.executo-chat > .wrap,
.executo-chat > div.block {
    background: var(--executo-chat-bg) !important;
    border: 1px solid var(--executo-chat-border) !important;
    border-radius: 16px !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35) !important;
    color: var(--executo-chat-text) !important;
}
.executo-chat .bubble-wrap,
.executo-chat [class*="bubble-wrap"],
.executo-chat .component-wrap,
.executo-chat .scroll-hide {
    background: var(--executo-chat-surface) !important;
    color: var(--executo-chat-muted) !important;
}
.executo-chat .prose,
.executo-chat .markdown,
.executo-chat [class*="message"] p,
.executo-chat [class*="message"] span,
.executo-chat [class*="message"] li,
.executo-chat [class*="message"] div,
.executo-chat [class*="placeholder"] {
    color: var(--executo-chat-text) !important;
    background: transparent !important;
}
.executo-chat h1, .executo-chat h2, .executo-chat h3,
.executo-chat h4, .executo-chat strong, .executo-chat b {
    color: var(--executo-chat-heading) !important;
}
.executo-chat .user .bubble-wrap,
.executo-chat [class*="user"] .bubble-wrap {
    background: var(--executo-chat-user) !important;
}
.executo-chat .bot .bubble-wrap,
.executo-chat [class*="bot"] .bubble-wrap {
    background: var(--executo-chat-surface) !important;
}
.executo-chat code {
    background: #0e0e16 !important;
    color: #e2e8f0 !important;
    border: 1px solid var(--executo-chat-border) !important;
    padding: 1px 5px !important;
    border-radius: 4px !important;
}
.executo-chat pre {
    background: #0e0e16 !important;
    border: 1px solid var(--executo-chat-border) !important;
    border-radius: 8px !important;
}

.executo-code-panel { margin-top: 12px; }
.executo-tip {
    text-align: center;
    color: #94a3b8;
    font-size: 0.85rem;
    margin-top: 10px;
}
footer { display: none !important; }

textarea, input[type="text"] {
    background: #14141f !important;
    color: #e2e8f0 !important;
    border-color: #2a2a3a !important;
}
button.secondary {
    background: #1a1a28 !important;
    color: #cbd5e1 !important;
    border-color: #2e2e42 !important;
}
details, .accordion, summary {
    background: #14141f !important;
    border-color: #2a2a3a !important;
    color: #cbd5e1 !important;
}
h3, .markdown-text, .executo-tip {
    color: #94a3b8 !important;
}
.tab-nav button {
    background: #14141f !important;
    color: #94a3b8 !important;
}
.tab-nav button.selected {
    background: #1e1e2e !important;
    color: #a5b4fc !important;
}
"""


def _render(steps: list[str], final: dict | None = None) -> str:
    md = "\n\n".join(steps) if steps else "..."

    if final is None:
        return md

    passed = final.get("passed")
    attempts = final.get("attempts", 0) or 0

    md += "\n\n---\n\n"
    if passed:
        md += f"### ✅ Solved in {attempts} attempt(s)\nAll tests passed in the sandbox.\n"
    else:
        md += f"### ⚠️ Not fully solved after {attempts} attempt(s)\n"
        note = format_failure_summary(final)
        if note:
            md += f"\n{note}\n"

    md += "\n*See the **Solution** and **Tests** tabs below for the full code.*"
    return md


def _append_execute_step(steps: list[str], state: dict) -> None:
    attempt = state.get("attempts", 0)
    ai_ok = state.get("self_test_passed")
    he_ok = state.get("humaneval_passed", True)
    badge = "✅ passed" if ai_ok and he_ok else "❌ failed"
    steps.append(f"🧪 Attempt {attempt}: tests {badge}")

    if not ai_ok or not he_ok:
        output = (state.get("output") or "").strip()
        if output:
            preview = output if len(output) <= 1200 else output[:1200] + "\n…"
            steps.append(f"```\n{preview}\n```")


def _stream_response(message: str, max_attempts: int):
    """Yield (chat_text, solution_code, test_code) as the agent runs."""
    steps: list[str] = []
    solution = ""
    tests = ""

    events = stream_executo_events(message.strip(), max_attempts=int(max_attempts))
    for event, state in events:
        if event == "start":
            steps = ["🧠 Understanding your request…"]
            yield _render(steps), solution, tests
        elif event == "generating":
            steps.append("✍️ Generating code with the LLM…")
            yield _render(steps), solution, tests
        elif event == "generate":
            steps.append("📦 Code ready — running tests in Docker…")
            yield _render(steps), solution, tests
        elif event == "execute":
            _append_execute_step(steps, state)
            yield _render(steps), solution, tests
        elif event == "fix":
            steps.append("🔧 Tests failed — reading errors and fixing the code…")
            yield _render(steps), solution, tests
        elif event == "done":
            solution = (state.get("code") or "").strip()
            tests = (state.get("test_code") or "").strip()
            yield _render(steps, final=state), solution, tests


def _assistant_history(history: list, text: str) -> list:
    """Return a fresh history list so Gradio detects each streaming update."""
    base = copy.deepcopy(history)
    if base and base[-1].get("role") == "assistant":
        base[-1] = {"role": "assistant", "content": text}
    else:
        base.append({"role": "assistant", "content": text})
    return base


def chat(message: str, history: list, max_attempts: int):
    """Handle a new user message with streaming updates."""
    if not message or not message.strip():
        yield history, "", "", "", ""
        return

    history = copy.deepcopy(history or [])
    history.append({"role": "user", "content": message.strip()})
    history.append({"role": "assistant", "content": "⏳ Starting…"})

    try:
        for text, solution, tests in _stream_response(message, max_attempts):
            yield _assistant_history(history, text), "", solution, tests, message.strip()
    except RuntimeError as exc:
        yield (
            _assistant_history(history, f"⚠️ **Setup needed**\n\n{format_setup_error(str(exc))}"),
            "",
            "",
            "",
            message.strip(),
        )
    except Exception as exc:  # noqa: BLE001
        yield (
            _assistant_history(history, f"⚠️ **Something went wrong**\n\n{format_llm_error(str(exc))}"),
            "",
            "",
            "",
            message.strip(),
        )


def run_again(history: list, max_attempts: int, last_prompt: str):
    """Re-run the last prompt."""
    if not last_prompt:
        gr.Info("No previous prompt to run again.")
        yield history, "", "", "", last_prompt
        return
    yield from chat(last_prompt, history, max_attempts)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title=TITLE, fill_height=True) as demo:
        gr.HTML(
            f"""
            <div id="executo-header">
                <h1>⚡ {TITLE}</h1>
                <p>{TAGLINE}</p>
            </div>
            """
        )

        last_prompt = gr.State("")

        chatbot = gr.Chatbot(
            height=420,
            show_label=False,
            elem_classes="executo-chat",
            sanitize_html=False,
            placeholder="Ask Executo to write a Python function…",
        )

        with gr.Row():
            msg = gr.Textbox(
                placeholder="Describe the Python function you want…",
                show_label=False,
                scale=8,
                container=False,
            )
            send = gr.Button("Send", variant="primary", scale=1, min_width=80)

        with gr.Row():
            run_again_btn = gr.Button("↻ Run again", scale=1)
            clear = gr.Button("Clear chat", scale=1)

        with gr.Accordion("💡 Example prompts", open=False):
            gr.Examples(
                examples=[[e] for e in EXAMPLES],
                inputs=msg,
                label="",
            )

        with gr.Accordion("⚙️ Settings", open=False):
            max_attempts = gr.Slider(
                minimum=1,
                maximum=8,
                value=DEFAULT_MAX_ATTEMPTS,
                step=1,
                label="Max self-correction attempts",
            )

        gr.Markdown("### Generated code")
        with gr.Tabs(elem_classes="executo-code-panel"):
            with gr.Tab("Solution"):
                solution_code = gr.Code(
                    language="python",
                    label="snippet.py",
                    lines=16,
                    interactive=False,
                )
            with gr.Tab("Tests"):
                test_code = gr.Code(
                    language="python",
                    label="test_snippet.py",
                    lines=16,
                    interactive=False,
                )

        gr.HTML(
            '<p class="executo-tip">Code runs in an isolated Docker sandbox. '
            "Always review before using in production.</p>"
        )

        stream_kw = {"concurrency_limit": 1, "show_progress": "hidden"}

        send.click(
            chat,
            inputs=[msg, chatbot, max_attempts],
            outputs=[chatbot, msg, solution_code, test_code, last_prompt],
            **stream_kw,
        )
        msg.submit(
            chat,
            inputs=[msg, chatbot, max_attempts],
            outputs=[chatbot, msg, solution_code, test_code, last_prompt],
            **stream_kw,
        )
        run_again_btn.click(
            run_again,
            inputs=[chatbot, max_attempts, last_prompt],
            outputs=[chatbot, msg, solution_code, test_code, last_prompt],
            **stream_kw,
        )
        clear.click(
            lambda: ([], "", "", "", ""),
            outputs=[chatbot, msg, solution_code, test_code, last_prompt],
        )

    return demo


if __name__ == "__main__":
    theme = (
        gr.themes.Base(
            primary_hue="violet",
            secondary_hue="purple",
            neutral_hue="gray",
            font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        )
        .set(
            body_background_fill="#0a0a0f",
            background_fill_primary="#0a0a0f",
            background_fill_secondary="#14141f",
            block_background_fill="#14141f",
            block_border_color="#2a2a3a",
            body_text_color="#e2e8f0",
        )
    )
    demo = build_ui()
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        theme=theme,
        css=CSS,
        head='<style>html,body,gradio-app{background:#0a0a0f!important}</style>',
    )
