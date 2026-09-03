#!/usr/bin/env python3
"""Executo — web UI for the self-correcting code agent.

Run:
    python app.py
Then open http://127.0.0.1:7860 in your browser.

The agent emits coarse events (see core.agent.stream_executo_events); this
module turns them into a live run panel. Anything that needs to tick smoothly
between events — the elapsed clock, the cooldown countdown — is rendered as a
relative value on a data attribute and animated by assets/app.js.
"""

from __future__ import annotations

import html
import itertools
import json
import math
import time
from pathlib import Path
from urllib.parse import quote

import gradio as gr

from core.agent import DEFAULT_MAX_ATTEMPTS, DEFAULT_MODEL, stream_executo_events
from core.errors import (
    format_failure_summary,
    format_llm_error,
    format_setup_error,
)
from core.rate_limit import RateLimiter

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

FAVICON = (ASSETS / "favicon.svg").resolve()
FAVICON_SVG = FAVICON.read_text(encoding="utf-8")
LOGO_SRC = "data:image/svg+xml," + quote(FAVICON_SVG)

CSS = (ASSETS / "app.css").read_text(encoding="utf-8")
APP_JS = (ASSETS / "app.js").read_text(encoding="utf-8")

APP_HEAD = f"""
<link rel="icon" type="image/svg+xml" href="{LOGO_SRC}">
<link rel="shortcut icon" type="image/svg+xml" href="{LOGO_SRC}">
<link rel="apple-touch-icon" href="{LOGO_SRC}">
<style>html,body,gradio-app{{background:#09090b!important}}</style>
<script>{APP_JS}</script>
"""

# Gradio rewrites <link rel="icon"> during hydration, so re-assert ours on load.
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
TAGLINE = "Self-correcting code agent"
HERO_TITLE = "Turn prompts into tested Python"
HERO_SUBTITLE = (
    "Describe what you want in plain English. Executo writes the code and its "
    "tests, runs them in an isolated Docker sandbox, and keeps correcting "
    "until they pass."
)

EXAMPLES = [
    "Merge a list of overlapping (start, end) intervals",
    "Parse an ISO-8601 duration into total seconds",
    "Validate an IBAN with the mod-97 checksum",
    "LRU cache with O(1) get and put",
]

MAX_LOG_CHARS = 2400
MAX_TASK_CHARS = 280

# Gradio patches HTML in place rather than replacing the node, so the client
# ticker cannot tell "same element" from "same value". Every freshly issued
# timer value carries a new key so app.js knows to re-anchor its clock.
_timer_keys = itertools.count(1)


# --------------------------------------------------------------------------- #
# Static markup
# --------------------------------------------------------------------------- #

BRANDMARK_HTML = f"""
<div class="executo-brandmark">
  <img src="{LOGO_SRC}" alt="{BRAND}" width="24" height="24" />
  <span class="name">{BRAND}</span>
  <span class="tagline">{TAGLINE}</span>
</div>
"""

HERO_HTML = f"""
<div>
  <h1>{HERO_TITLE}</h1>
  <p>{HERO_SUBTITLE}</p>
</div>
"""

HINT_HTML = (
    '<span><kbd>Shift</kbd> + <kbd>Enter</kbd> to run</span>'
)

# 16x16 stroked icons, sized and coloured by CSS.
_SVG_OPEN = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
)
STEP_ICONS = {
    "done": _SVG_OPEN + '<circle cx="8" cy="8" r="6.4" stroke-opacity=".3"/>'
    '<path d="M5.2 8.2 7 10 10.9 6"/></svg>',
    "failed": _SVG_OPEN + '<circle cx="8" cy="8" r="6.4" stroke-opacity=".3"/>'
    '<path d="M6 6l4 4M10 6l-4 4"/></svg>',
    "active": _SVG_OPEN + '<circle cx="8" cy="8" r="6.4" stroke-opacity=".2"/>'
    '<path d="M14.4 8A6.4 6.4 0 0 0 8 1.6"/></svg>',
    "pending": _SVG_OPEN
    + '<circle cx="8" cy="8" r="6.4" stroke-opacity=".3" stroke-dasharray="2 3"/></svg>',
}
RESULT_ICONS = {
    "passed": STEP_ICONS["done"],
    "failed": STEP_ICONS["failed"],
    "error": STEP_ICONS["failed"],
    "blocked": _SVG_OPEN + '<circle cx="8" cy="8" r="6.4" stroke-opacity=".3"/>'
    '<path d="M8 4.8v3.6M8 11.1v.1"/></svg>',
}

BADGE_LABELS = {
    "running": "Running",
    "passed": "Passed",
    "failed": "Failed",
    "error": "Error",
    "blocked": "Blocked",
}


def _fmt_secs(seconds: float) -> str:
    if seconds < 0.05:
        return ""  # instant steps: a "0.0s" stamp is noise, not information
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"


def _fmt_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


# --------------------------------------------------------------------------- #
# Session chip — runs left + live cooldown countdown
# --------------------------------------------------------------------------- #


def chip_html(limiter: RateLimiter) -> str:
    """Render the nav chip. The countdown itself is animated client-side."""
    left = limiter.runs_remaining
    remaining = limiter.cooldown_remaining

    if left <= 0:
        state = "empty"
        timer = '<span class="ex-chip-timer">Session limit reached</span>'
    else:
        state = "cooling" if remaining > 0 else "ready"
        label = f"Ready in {math.ceil(remaining)}s" if remaining > 0 else "Ready"
        timer = (
            '<span class="ex-chip-timer"'
            f' data-ex-countdown="{remaining:.2f}"'
            f' data-ex-key="cd{next(_timer_keys)}"'
            f' data-ex-total="{limiter.cooldown_seconds}"'
            f' data-ex-ready="Ready">{label}</span>'
        )

    return (
        f'<div class="ex-chip" data-state="{state}">'
        '<span class="ex-chip-dot"></span>'
        f'<span class="ex-chip-runs"><b>{left}</b>&nbsp;/&nbsp;{limiter.max_runs} runs</span>'
        '<span class="ex-chip-div"></span>'
        f"{timer}"
        '<span class="ex-chip-bar"><i></i></span>'
        "</div>"
    )


# --------------------------------------------------------------------------- #
# Live run panel
# --------------------------------------------------------------------------- #


class RunView:
    """Accumulates agent events and renders them as the live run panel.

    Steps are opened as `active` and closed by the next event, so whatever is
    on screen always reflects what the agent is doing *right now* rather than
    what it last finished.
    """

    def __init__(self, run_id: int, task: str, max_attempts: int) -> None:
        self.run_id = run_id
        self.task = task
        self.max_attempts = max_attempts
        self.started = time.monotonic()
        self.steps: list[dict] = []
        self.status = "running"
        self.attempt = 0
        self.log = ""
        self.result_title = ""
        self.result_body = ""

    # -- step bookkeeping ---------------------------------------------------

    def _close_active(self, state: str = "done", detail: str = "") -> None:
        for step in reversed(self.steps):
            if step["state"] == "active":
                step["state"] = state
                step["seconds"] = time.monotonic() - step["started"]
                if detail:
                    step["detail"] = detail
                break

    def begin(self, label: str, detail: str = "", tag: str = "") -> None:
        self._close_active()
        self.steps.append(
            {
                "tag": tag,
                "label": label,
                "detail": detail,
                "state": "active",
                "started": time.monotonic(),
                "seconds": None,
            }
        )

    def begin_or_update(self, tag: str, label: str, detail: str = "") -> None:
        """Open a step, or refresh it in place if it is the one already active.

        Streamed LLM events fire many times for a single step; this lets the
        label and the live reasoning line update without stacking new rows.
        """
        if self.steps and self.steps[-1]["state"] == "active" and self.steps[-1].get("tag") == tag:
            self.steps[-1]["label"] = label
            if detail:
                self.steps[-1]["detail"] = detail
            return
        self.begin(label, detail, tag=tag)

    def close(self, state: str = "done", detail: str = "") -> None:
        self._close_active(state, detail)

    def finish(self, status: str, title: str, body: str = "") -> None:
        self._close_active("done" if status == "passed" else "failed")
        self.status = status
        self.result_title = title
        self.result_body = body

    # -- rendering ----------------------------------------------------------

    def _head_html(self) -> str:
        elapsed = time.monotonic() - self.started
        # The key stays fixed for the whole run so the clock ticks smoothly
        # across events instead of being nudged back by each round trip.
        clock = (
            '<span class="ex-run-clock"'
            f' data-ex-elapsed="{elapsed:.2f}"'
            f' data-ex-key="run{self.run_id}"'
            f' data-ex-running="{1 if self.status == "running" else 0}">'
            f"{_fmt_clock(elapsed)}</span>"
        )

        meta = ""
        if self.attempt:
            meta = (
                '<span class="ex-run-meta">Attempt '
                f"{self.attempt} of {self.max_attempts}</span>"
            )

        return (
            '<div class="ex-run-head">'
            f'<span class="ex-badge" data-state="{self.status}"><i></i>'
            f'{BADGE_LABELS[self.status]}</span>'
            f"{meta}"
            '<span class="ex-run-spacer"></span>'
            f"{clock}"
            "</div>"
        )

    def _steps_html(self) -> str:
        if not self.steps:
            return ""
        rows = []
        for step in self.steps:
            stamp = _fmt_secs(step["seconds"]) if step["seconds"] else ""
            timing = f'<span class="ex-step-time">{stamp}</span>' if stamp else ""
            detail = (
                f'<div class="ex-step-detail">{html.escape(step["detail"])}</div>'
                if step["detail"]
                else ""
            )
            rows.append(
                f'<li class="ex-step" data-state="{step["state"]}">'
                f'<span class="ex-step-icon">{STEP_ICONS[step["state"]]}</span>'
                '<span class="ex-step-body">'
                f'<span class="ex-step-label">{html.escape(step["label"])}</span>'
                f"{detail}</span>"
                f"{timing}</li>"
            )
        return f'<ol class="ex-steps ex-scroll">{"".join(rows)}</ol>'

    def _log_html(self) -> str:
        if not self.log:
            return ""
        text = self.log.strip()
        if len(text) > MAX_LOG_CHARS:
            text = text[:MAX_LOG_CHARS] + "\n…"
        # Mid-run the errors are just noise the agent is already working on;
        # once it gives up they are the whole story, so open them.
        opened = " open" if self.status == "failed" else ""
        return (
            f'<details class="ex-log"{opened}><summary>Sandbox output</summary>'
            f"<pre class=\"ex-scroll\">{html.escape(text)}</pre></details>"
        )

    def _result_html(self) -> str:
        if self.status == "running" or not self.result_title:
            return ""
        body = f"<p>{html.escape(self.result_body)}</p>" if self.result_body else ""
        return (
            f'<div class="ex-result" data-state="{self.status}">'
            f'<span class="ex-result-icon">{RESULT_ICONS[self.status]}</span>'
            f"<span><strong>{html.escape(self.result_title)}</strong>{body}</span>"
            "</div>"
        )

    def render(self) -> str:
        task = self.task
        if len(task) > MAX_TASK_CHARS:
            task = task[:MAX_TASK_CHARS] + "…"
        return (
            f'<div class="ex-run ex-fade" data-run-id="{self.run_id}">'
            f"{self._head_html()}"
            '<div class="ex-run-task"><span class="label">Task</span>'
            f"<span>{html.escape(task)}</span></div>"
            f"{self._steps_html()}"
            f"{self._log_html()}"
            f"{self._result_html()}"
            "</div>"
        )


def notice_html(state: str, title: str, body: str, extra: str = "") -> str:
    """A standalone panel for things that never became a run (e.g. rate limits).

    `extra` is trusted markup appended after the body — used for the live
    cooldown countdown, which app.js animates.
    """
    return (
        '<div class="ex-run ex-fade">'
        f'<div class="ex-run-head"><span class="ex-badge" data-state="{state}"><i></i>'
        f'{BADGE_LABELS[state]}</span></div>'
        f'<div class="ex-result" data-state="{state}">'
        f'<span class="ex-result-icon">{RESULT_ICONS[state]}</span>'
        f"<span><strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(body)}{extra}</p></span></div></div>"
    )


def blocked_notice(limiter: RateLimiter) -> str:
    """Explain *why* a run was refused, with a countdown when one applies.

    `RateLimiter.check` returns a markdown string aimed at a chat bubble; this
    renders the same policy in the panel's own voice instead of re-parsing it.
    """
    if limiter.runs_remaining <= 0:
        return notice_html(
            "blocked",
            "Session limit reached",
            f"You have used all {limiter.max_runs} runs for this session. "
            "Refresh the page to start a new one.",
        )

    remaining = limiter.cooldown_remaining
    countdown = (
        ' <span class="ex-chip-timer"'
        f' data-ex-countdown="{remaining:.2f}"'
        f' data-ex-key="cd{next(_timer_keys)}"'
        f' data-ex-total="{limiter.cooldown_seconds}"'
        ' data-ex-ready="Ready now">'
        f"Ready in {math.ceil(remaining)}s</span>."
    )
    return notice_html(
        "blocked",
        "Cooling down",
        f"Executo waits {limiter.cooldown_seconds}s between runs.",
        extra=countdown,
    )


# --------------------------------------------------------------------------- #
# Event -> RunView translation
# --------------------------------------------------------------------------- #


def _sandbox_detail(state: dict) -> str:
    parts = ["AI self-tests " + ("passed" if state.get("self_test_passed") else "failed")]
    if state.get("humaneval_test_code"):
        parts.append(
            "HumanEval " + ("passed" if state.get("humaneval_passed") else "failed")
        )
    if state.get("timed_out"):
        parts.append("timed out")
    return " · ".join(parts)


def _reasoning_tail(state: dict) -> str:
    """The model's latest thought, as a single short line for the step detail."""
    text = (state.get("reasoning") or "").strip()
    if not text:
        return ""
    line = text.splitlines()[-1].strip()
    return (line[:117] + "…") if len(line) > 118 else line


def _write_label(state: dict, *, fixing: bool) -> str:
    """Distinguish the model's think phase from the code-writing phase."""
    verb = "Rewriting the code" if fixing else "Writing the solution and tests"
    if not (state.get("code") or state.get("test_code")):
        return "Thinking through the approach" if not fixing else "Diagnosing the failure"
    return verb


def _apply_event(view: RunView, event: str, state: dict) -> None:
    """Fold one agent event into `view`.

    Steps open as *active* for the work about to start and close on the next
    event, so the panel always shows what the agent is doing right now — the
    slow parts being the streamed LLM call and the Docker run.
    """
    if event in ("generating", "generate"):
        view.begin_or_update(
            "write", _write_label(state, fixing=False), _reasoning_tail(state)
        )
        if event == "generate":
            view.close("done", "solution and tests ready")

    elif event == "executing":
        view.attempt += 1
        view.begin(f"Attempt {view.attempt} · running tests in the sandbox")

    elif event == "execute":
        passed = state.get("passed")
        view.close("done" if passed else "failed", _sandbox_detail(state))
        view.log = "" if passed else (state.get("output") or "")

    elif event in ("fixing", "fix"):
        view.begin_or_update(
            "fix", _write_label(state, fixing=True), _reasoning_tail(state)
        )
        if event == "fix":
            view.close("done", "revised solution ready")

    elif event == "done":
        attempts = state.get("attempts", 0) or 0
        if state.get("passed"):
            view.finish(
                "passed",
                f"Solved in {attempts} attempt{'s' if attempts != 1 else ''}",
                "Every test ran green inside the sandbox.",
            )
        else:
            view.finish(
                "failed",
                f"Not solved after {attempts} attempt{'s' if attempts != 1 else ''}",
                format_failure_summary(state) or "",
            )


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

# Every streaming yield returns this fixed tuple; `gr.update()` means "leave
# this component alone", which keeps the per-event payloads small.
OUTPUT_KEYS = (
    "hero",
    "examples",
    "run_host",
    "code_host",
    "run_html",
    "solution",
    "tests",
    "run_btn",
    "chip",
)


def _outputs(**changes) -> tuple:
    return tuple(changes.get(key, gr.update()) for key in OUTPUT_KEYS)


def build_ui() -> gr.Blocks:
    limiter = RateLimiter()
    run_ids = itertools.count(1)

    def on_run(prompt_text: str, max_attempts: int):
        task = (prompt_text or "").strip()
        if not task:
            gr.Info("Describe what you want Executo to build.")
            yield _outputs()
            return

        allowed, _ = limiter.check()
        if not allowed:
            yield _outputs(
                hero=gr.update(visible=False),
                examples=gr.update(visible=False),
                run_host=gr.update(visible=True),
                run_html=blocked_notice(limiter),
                chip=chip_html(limiter),
            )
            return

        limiter.record()
        view = RunView(next(run_ids), task, int(max_attempts))

        # Collapse the landing content so the run panel lands in view. The code
        # panel opens right away and fills in as the model writes.
        yield _outputs(
            hero=gr.update(visible=False),
            examples=gr.update(visible=False),
            run_host=gr.update(visible=True),
            code_host=gr.update(visible=True),
            run_html=view.render(),
            solution="",
            tests="",
            run_btn=gr.update(value="Running…", interactive=False),
            chip=chip_html(limiter),
        )

        solution = tests = ""
        try:
            for event, state in stream_executo_events(task, max_attempts=int(max_attempts)):
                _apply_event(view, event, state)
                code = state.get("code") or ""
                test_code = state.get("test_code") or ""
                if event == "done":
                    solution, tests = code.strip(), test_code.strip()
                elif event in ("generating", "generate", "fixing", "fix"):
                    # Stream the code into the tabs as it is written.
                    yield _outputs(
                        run_html=view.render(), solution=code, tests=test_code
                    )
                else:
                    yield _outputs(run_html=view.render())
        except RuntimeError as exc:
            view.finish("error", "Setup needed", format_setup_error(str(exc)))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            lower = msg.lower()
            if "429" in msg or "rate_limit" in lower or "resource_exhausted" in lower:
                title = "Rate limited by Groq"
            else:
                title = "Something went wrong"
            view.finish("error", title, format_llm_error(msg))

        yield _outputs(
            run_html=view.render(),
            code_host=gr.update(visible=bool(solution or tests)),
            solution=solution,
            tests=tests,
            run_btn=gr.update(value="Run Executo", interactive=True),
            chip=chip_html(limiter),
        )

    def on_clear():
        return _outputs(
            hero=gr.update(visible=True),
            examples=gr.update(visible=True),
            run_host=gr.update(visible=False),
            code_host=gr.update(visible=False),
            run_html="",
            solution="",
            tests="",
            run_btn=gr.update(value="Run Executo", interactive=True),
            chip=chip_html(limiter),
        ) + ("",)  # also clears the prompt

    with gr.Blocks(title=BRAND, fill_width=True) as demo:
        demo.load(fn=None, js=INIT_FAVICON_JS)

        with gr.Row(elem_classes="executo-nav"):
            gr.HTML(BRANDMARK_HTML, elem_classes="executo-navblock", padding=False)
            chip = gr.HTML(
                chip_html(limiter), elem_classes="executo-navblock", padding=False
            )

        max_attempts = gr.State(DEFAULT_MAX_ATTEMPTS)

        with gr.Column(elem_classes="executo-main"):
            hero = gr.HTML(HERO_HTML, elem_classes="executo-hero", padding=False)

            with gr.Column(elem_classes="executo-composer"):
                prompt = gr.Textbox(
                    placeholder="Describe the Python function you want…",
                    show_label=False,
                    container=False,
                    lines=6,
                    max_lines=20,
                    elem_classes="executo-textarea",
                )
                with gr.Row(elem_classes="executo-composer-foot"):
                    gr.HTML(HINT_HTML, elem_classes="executo-hint", padding=False)
                    clear_btn = gr.Button(
                        "Clear", elem_classes="ex-btn-ghost", scale=0, min_width=0
                    )
                    run_btn = gr.Button(
                        "Run Executo", elem_classes="ex-btn-primary", scale=0, min_width=0
                    )

            with gr.Row(elem_classes="executo-examples") as examples:
                for text in EXAMPLES:
                    gr.Button(
                        text, elem_classes="ex-example", scale=0, min_width=0
                    ).click(lambda value=text: value, outputs=[prompt])

            with gr.Column(visible=False, elem_classes="executo-runhost") as run_host:
                run_html = gr.HTML("", padding=False)

            with gr.Column(visible=False, elem_classes="executo-codehost") as code_host:
                gr.HTML(
                    "<span>Code</span>",
                    elem_classes="executo-sectiontitle",
                    padding=False,
                )
                with gr.Tabs(elem_classes="executo-codetabs"):
                    with gr.Tab("Solution"):
                        solution_code = gr.Code(
                            language="python",
                            label="snippet.py",
                            lines=18,
                            interactive=False,
                        )
                    with gr.Tab("Tests"):
                        test_code = gr.Code(
                            language="python",
                            label="test_snippet.py",
                            lines=18,
                            interactive=False,
                        )

        outputs = [
            hero,
            examples,
            run_host,
            code_host,
            run_html,
            solution_code,
            test_code,
            run_btn,
            chip,
        ]
        stream_kw = {"concurrency_limit": 1, "show_progress": "hidden"}

        run_btn.click(on_run, [prompt, max_attempts], outputs, **stream_kw)
        prompt.submit(on_run, [prompt, max_attempts], outputs, **stream_kw)
        clear_btn.click(on_clear, outputs=outputs + [prompt])

    return demo


def build_theme() -> gr.themes.Base:
    return gr.themes.Base(
        primary_hue="gray",
        secondary_hue="gray",
        neutral_hue="gray",
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
    ).set(
        body_background_fill="#09090b",
        background_fill_primary="#09090b",
        background_fill_secondary="#121215",
        block_background_fill="#121215",
        block_border_color="rgba(255,255,255,0.08)",
        border_color_primary="rgba(255,255,255,0.08)",
        body_text_color="#fafafa",
        body_text_color_subdued="#71717a",
    )


if __name__ == "__main__":
    demo = build_ui()
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        theme=build_theme(),
        css=CSS,
        favicon_path=str(FAVICON),
        allowed_paths=[str(ASSETS)],
        head=APP_HEAD,
    )
