#!/usr/bin/env python3
"""Executo — minimalist web UI for the self-correcting code agent.

Run:
    python app.py
Then open http://127.0.0.1:7860 in your browser.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from urllib.parse import quote

import gradio as gr

from core.agent import DEFAULT_MAX_ATTEMPTS, stream_executo_events
from core.errors import (
    format_failure_summary,
    format_llm_error,
    format_setup_error,
)
from core.rate_limit import RateLimiter

ROOT = Path(__file__).resolve().parent
FAVICON = (ROOT / "assets" / "favicon.svg").resolve()
FAVICON_SVG = FAVICON.read_text(encoding="utf-8")
LOGO_SRC = "data:image/svg+xml," + quote(FAVICON_SVG)

APP_HEAD = f"""
<link rel="icon" type="image/svg+xml" href="{LOGO_SRC}">
<link rel="shortcut icon" type="image/svg+xml" href="{LOGO_SRC}">
<link rel="apple-touch-icon" href="{LOGO_SRC}">
<style>html,body,gradio-app{{background:#0a0a0a!important}}</style>
"""

INIT_FAVICON_JS = f"""
() => {{
    const href = {json.dumps(LOGO_SRC)};
    document.querySelectorAll("link[rel*='icon']").forEach(el => el.remove());
    for (const rel of ["icon", "shortcut icon", "apple-touch-icon"]) {{
        const link = document.createElement("link");
        link.rel = rel;
        link.type = "image/svg+xml";
        link.href = href;
        document.head.appendChild(link);
    }}
}}
"""

BRAND = "Executo"
NAV_TAGLINE = "Self-correcting code agent"
HERO_TITLE = "Turn prompts into tested Python"
HERO_SUBTITLE = (
    "Describe what you want in plain English. Executo writes the code and tests, "
    "runs them in an isolated Docker sandbox, and keeps correcting until they pass."
)

NAV_HTML = f"""
<div class="executo-nav">
  <div class="executo-nav-left">
    <img class="executo-logo" src="{LOGO_SRC}" alt="{BRAND}" width="26" height="26" />
    <span class="executo-brand">{BRAND}</span>
    <span class="executo-sub">{NAV_TAGLINE}</span>
  </div>
</div>
"""

HERO_HTML = f"""
<div class="executo-hero">
  <h1>{HERO_TITLE}</h1>
  <p>{HERO_SUBTITLE}</p>
</div>
"""

CSS = """
:root { color-scheme: dark; }

html, body, gradio-app, #root,
.gradio-container, .app, .main, .wrap, .contain {
    background: #0a0a0a !important;
}
.gradio-container {
    max-width: 100% !important;
    padding: 0 !important;
}
footer { display: none !important; }

/* ── Top navigation bar ── */
.executo-navhost {
    padding: 0 !important;
    margin: 0 !important;
    background: transparent !important;
    border: none !important;
}
.executo-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 22px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.executo-nav-left { display: flex; align-items: center; }
.executo-logo {
    width: 26px;
    height: 26px;
    display: block;
    border-radius: 7px;
    flex-shrink: 0;
}
.executo-brand { color: #fff; font-weight: 600; font-size: 15px; margin-left: 10px; }
.executo-sub { color: #6b6b75; font-size: 13.5px; margin-left: 16px; }

/* ── Centered content wrapper ── */
.executo-main {
    max-width: 720px !important;
    margin: 0 auto !important;
    padding: 60px 24px 48px !important;
}

/* ── Hero ── */
.executo-herohost {
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
}
.executo-hero { text-align: center; margin-bottom: 26px; }
.executo-hero h1 {
    color: #ffffff;
    font-size: 30px;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0 0 12px;
}
.executo-hero p {
    color: #8b8b94;
    font-size: 14.5px;
    line-height: 1.6;
    max-width: 460px;
    margin: 0 auto;
}

/* ── Input card ── */
.executo-card {
    background: #161618 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 16px !important;
    padding: 14px !important;
}
.executo-card .block,
.executo-card .form {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* Tabs as pill segmented control */
.executo-tabs,
.executo-tabs .tab-wrapper,
.executo-tabs .tab-container {
    border: none !important;
    box-shadow: none !important;
    gap: 4px !important;
}
.executo-tabs .tab-wrapper button {
    border: none !important;
    background: transparent !important;
    color: #7c7c85 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
.executo-tabs .tab-wrapper button:hover { color: #c4c4cc !important; }
.executo-tabs .tab-wrapper button.selected {
    background: #ffffff !important;
    color: #111 !important;
    font-weight: 600 !important;
}
.executo-tabs .tabitem,
.executo-tabs .tabitem.svelte-11gaq1 {
    border: none !important;
    background: transparent !important;
    padding: 12px 2px 0 !important;
}

/* Code textarea */
.executo-textarea textarea {
    background: transparent !important;
    color: #d4d4d8 !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
    font-size: 13px !important;
    line-height: 1.55 !important;
    min-height: 185px !important;
    border: none !important;
    box-shadow: none !important;
    padding: 4px 6px !important;
    resize: none !important;
}
.executo-textarea textarea::placeholder { color: #5c5c66 !important; }

.executo-url textarea,
.executo-url input {
    background: rgba(255,255,255,0.03) !important;
    color: #d4d4d8 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    font-size: 13px !important;
}

/* Card footer row */
.executo-cardfoot {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    margin-top: 6px !important;
    flex-wrap: nowrap !important;
}
.executo-foothost {
    flex: 1 1 auto !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    min-width: 0 !important;
}
.executo-foothint { color: #6b6b75; font-size: 12.5px; }

button.executo-ghost {
    background: transparent !important;
    color: #c4c4cc !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 13px !important;
    padding: 7px 16px !important;
    border-radius: 999px !important;
    min-width: max-content !important;
    width: auto !important;
    white-space: nowrap !important;
}
button.executo-ghost:hover { background: rgba(255,255,255,0.06) !important; }
button.executo-primary {
    background: #ffffff !important;
    color: #111 !important;
    border: none !important;
    box-shadow: none !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 8px 18px !important;
    border-radius: 999px !important;
    min-width: max-content !important;
    width: auto !important;
    white-space: nowrap !important;
}
button.executo-primary:hover { background: #e6e6e6 !important; }

/* Rate-limit status line */
.executo-tip {
    text-align: center;
    color: #5c5c66 !important;
    font-size: 11.5px !important;
    margin-top: 14px !important;
}

/* ── Results area ── */
.executo-results { margin-top: 22px !important; }
.executo-chat,
.executo-chat > .wrap,
.executo-chat > div.block {
    background: #161618 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important;
    color: #e2e8f0 !important;
}
.executo-chat .bubble-wrap,
.executo-chat [class*="bubble-wrap"] {
    background: #1a1a1e !important;
    color: #b4b4bc !important;
}
.executo-chat .prose,
.executo-chat .markdown,
.executo-chat [class*="message"] p,
.executo-chat [class*="message"] span,
.executo-chat [class*="message"] li,
.executo-chat [class*="message"] div {
    color: #e2e8f0 !important;
    background: transparent !important;
}
.executo-chat h1, .executo-chat h2, .executo-chat h3,
.executo-chat h4, .executo-chat strong, .executo-chat b {
    color: #ffffff !important;
}
.executo-chat code {
    background: #0e0e10 !important;
    color: #e2e8f0 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    padding: 1px 5px !important;
    border-radius: 4px !important;
}
.executo-chat pre {
    background: #0e0e10 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}
.executo-results h3, .executo-results .markdown-text { color: #8b8b94 !important; }
.executo-results .tab-wrapper button { background: transparent !important; color: #7c7c85 !important; }
.executo-results .tab-wrapper button.selected { color: #fff !important; }
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


def build_ui() -> gr.Blocks:
    limiter = RateLimiter()

    def chat(message: str, history: list, max_attempts: int):
        """Run the agent on `message`, streaming updates into the chat."""
        if not message or not message.strip():
            yield history, "", "", ""
            return

        ok, rate_msg = limiter.check()
        if not ok:
            history = copy.deepcopy(history or [])
            history.append({"role": "user", "content": message.strip()[:400]})
            history.append({"role": "assistant", "content": rate_msg})
            yield history, "", "", message.strip()
            return

        limiter.record()

        history = copy.deepcopy(history or [])
        history.append({"role": "user", "content": message.strip()[:400]})
        history.append({"role": "assistant", "content": "⏳ Starting…"})

        try:
            for text, solution, tests in _stream_response(message, max_attempts):
                yield _assistant_history(history, text), solution, tests, message.strip()
        except RuntimeError as exc:
            yield (
                _assistant_history(history, f"⚠️ **Setup needed**\n\n{format_setup_error(str(exc))}"),
                "",
                "",
                message.strip(),
            )
        except Exception as exc:  # noqa: BLE001
            yield (
                _assistant_history(history, f"⚠️ **Something went wrong**\n\n{format_llm_error(str(exc))}"),
                "",
                "",
                message.strip(),
            )

    def on_run(prompt, history, max_attempts):
        if not prompt or not prompt.strip():
            gr.Info("Describe what you want Executo to build.")
            yield history, "", "", ""
            return
        yield from chat(prompt, history, max_attempts)

    def tip_text() -> str:
        return f"*{limiter.status_line()}*"

    def reveal():
        return gr.update(visible=True)

    def on_clear():
        return (
            "",            # prompt
            [],            # chatbot
            "",            # solution_code
            "",            # test_code
            "",            # last_prompt
            gr.update(visible=False),  # results_group
        )

    with gr.Blocks(title=BRAND) as demo:
        demo.load(fn=None, js=INIT_FAVICON_JS)
        gr.HTML(NAV_HTML, elem_classes="executo-navhost")

        max_attempts = gr.State(DEFAULT_MAX_ATTEMPTS)
        last_prompt = gr.State("")

        with gr.Column(elem_classes="executo-main"):
            gr.HTML(HERO_HTML, elem_classes="executo-herohost")

            with gr.Column(elem_classes="executo-card"):
                prompt = gr.Textbox(
                    placeholder="Describe the Python function you want…",
                    show_label=False,
                    container=False,
                    lines=9,
                    max_lines=22,
                    elem_classes="executo-textarea",
                )

                with gr.Row(elem_classes="executo-cardfoot"):
                    gr.HTML(
                        '<span class="executo-foothint">Plain English</span>',
                        elem_classes="executo-foothost",
                    )
                    clear_btn = gr.Button("Clear", elem_classes="executo-ghost", scale=0)
                    run_btn = gr.Button("Run Executo", elem_classes="executo-primary", scale=0)

            rate_tip = gr.Markdown(tip_text(), elem_classes="executo-tip")

            with gr.Column(visible=False, elem_classes="executo-results") as results_group:
                chatbot = gr.Chatbot(
                    height=420,
                    show_label=False,
                    elem_classes="executo-chat",
                    sanitize_html=False,
                    placeholder="Agent progress will appear here…",
                )
                gr.Markdown("### Generated code")
                with gr.Tabs():
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

        run_inputs = [prompt, chatbot, max_attempts]
        run_outputs = [chatbot, solution_code, test_code, last_prompt]
        stream_kw = {"concurrency_limit": 1, "show_progress": "hidden"}

        run_btn.click(reveal, outputs=[results_group]).then(
            on_run, inputs=run_inputs, outputs=run_outputs, **stream_kw
        ).then(tip_text, outputs=[rate_tip])

        prompt.submit(reveal, outputs=[results_group]).then(
            on_run, inputs=run_inputs, outputs=run_outputs, **stream_kw
        ).then(tip_text, outputs=[rate_tip])

        clear_btn.click(
            on_clear,
            outputs=[
                prompt,
                chatbot,
                solution_code,
                test_code,
                last_prompt,
                results_group,
            ],
        )

    return demo


if __name__ == "__main__":
    theme = (
        gr.themes.Base(
            primary_hue="gray",
            secondary_hue="gray",
            neutral_hue="gray",
            font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        )
        .set(
            body_background_fill="#0a0a0a",
            background_fill_primary="#0a0a0a",
            background_fill_secondary="#161618",
            block_background_fill="#161618",
            block_border_color="rgba(255,255,255,0.07)",
            body_text_color="#e2e8f0",
        )
    )
    demo = build_ui()
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        theme=theme,
        css=CSS,
        favicon_path=str(FAVICON),
        allowed_paths=[str(ROOT / "assets")],
        head=APP_HEAD,
    )
