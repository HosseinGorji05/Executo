"""Executo self-correction loop (LangGraph + Groq + Docker).

Flow:
    generate -> execute -> (passed? -> END) | (retries left? -> fix -> execute) | END

Execute runs AI self-tests in Docker. If humaneval_task_id is set, HumanEval
fixed tests run too — both must pass (strict).

Normal: python -m core.agent "your prompt"
HumanEval: python -m core.agent --humaneval HumanEval/0
           python eval_humaneval.py HumanEval/0
Batch:     python eval_humaneval_batch.py --limit 10
Streaming: add --stream to any of the above
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from core import prompts
from core.errors import format_failure_summary, format_llm_error, format_setup_error
from core.sandbox import SandboxResult, docker_available, run_code_with_tests
from core.humaneval import load_task, build_humaneval_test, DEFAULT_DATASET
from pathlib import Path

load_dotenv()

DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
DEFAULT_MAX_ATTEMPTS = 4


class AgentState(TypedDict, total=False):
    task: str
    code: str
    test_code: str
    output: str
    passed: bool
    timed_out: bool
    attempts: int
    max_attempts: int
    model: str
    humaneval_test_code: str
    self_test_passed: bool
    humaneval_passed: bool




_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _python_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in _FENCE_RE.finditer(text)]


def _section_block(text: str, label: str) -> Optional[str]:
    match = re.search(
        rf"#+\s*{label}\b(.*?)(?=\n#+\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    blocks = _python_blocks(match.group(1))
    return blocks[0] if blocks else None


def parse_solution_and_tests(
    text: str, fallback_test: Optional[str] = None
) -> tuple[str, str]:
    """Pull the SOLUTION and TESTS code blocks out of an LLM response.

    Falls back to positional fences if the labels are missing so a slightly
    off-format reply still works.
    """
    solution = _section_block(text, "SOLUTION")
    tests = _section_block(text, "TESTS")

    if solution is None or tests is None:
        blocks = _python_blocks(text)
        if solution is None:
            solution = blocks[0] if blocks else ""
        if tests is None:
            tests = blocks[1] if len(blocks) > 1 else (fallback_test or "")

    return solution, tests


def _get_llm(model: str):
    # Imported lazily so importing this module doesn't require the package
    # (or an API key) until the agent actually runs.
    from langchain_groq import ChatGroq

    return ChatGroq(model=model, temperature=0)


def _generate_node(state: AgentState) -> dict[str, Any]:
    llm = _get_llm(state.get("model", DEFAULT_MODEL))
    response = llm.invoke(
        [
            SystemMessage(content=prompts.GENERATE_SYSTEM),
            HumanMessage(content=prompts.generate_user(state["task"])),
        ]
    )
    code, test_code = parse_solution_and_tests(str(response.content))
    return {"code": code, "test_code": test_code, "attempts": 0}


def _format_execute_output(
    self_result: SandboxResult,
    he_result: SandboxResult | None,
) -> str:
    parts: list[str] = []
    if not self_result.passed:
        parts.append("=== AI self-tests FAILED ===")
        parts.append(self_result.output or "(no output)")
    if he_result is not None and not he_result.passed:
        parts.append("=== HumanEval tests FAILED ===")
        parts.append(he_result.output or "(no output)")
    if not parts:
        return self_result.output or he_result.output if he_result else ""
    return "\n\n".join(parts)


def _execute_node(state: AgentState) -> dict[str, Any]:
    self_result = run_code_with_tests(state["code"], state["test_code"])
    self_test_passed = self_result.passed

    humaneval_test_code = state.get("humaneval_test_code", "")
    he_result: SandboxResult | None = None
    if humaneval_test_code:
        he_result = run_code_with_tests(state["code"], humaneval_test_code)
        humaneval_passed = he_result.passed
    else:
        humaneval_passed = True

    passed = self_test_passed and humaneval_passed
    timed_out = self_result.timed_out or (he_result.timed_out if he_result else False)

    return {
        "output": _format_execute_output(self_result, he_result),
        "passed": passed,
        "self_test_passed": self_test_passed,
        "humaneval_passed": humaneval_passed,
        "timed_out": timed_out,
        "attempts": state.get("attempts", 0) + 1,
    }


def _fix_node(state: AgentState) -> dict[str, Any]:
    llm = _get_llm(state.get("model", DEFAULT_MODEL))
    has_humaneval = bool(state.get("humaneval_test_code"))
    response = llm.invoke(
        [
            SystemMessage(content=prompts.FIX_SYSTEM),
            HumanMessage(
                content=prompts.fix_user(
                    state["task"],
                    state["code"],
                    state["test_code"],
                    state["output"],
                    self_test_passed=state.get("self_test_passed"),
                    humaneval_passed=state.get("humaneval_passed"),
                    has_humaneval=has_humaneval,
                )
            ),
        ]
    )
    code, test_code = parse_solution_and_tests(
        str(response.content), fallback_test=state["test_code"]
    )
    return {"code": code, "test_code": test_code}


def _route_after_execute(state: AgentState) -> str:
    if state.get("passed"):
        return "done"
    if state.get("attempts", 0) >= state.get("max_attempts", DEFAULT_MAX_ATTEMPTS):
        return "done"
    return "fix"


def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("generate", _generate_node)
    graph.add_node("execute", _execute_node)
    graph.add_node("fix", _fix_node)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "execute")
    graph.add_conditional_edges(
        "execute", _route_after_execute, {"fix": "fix", "done": END}
    )
    graph.add_edge("fix", "execute")
    return graph.compile()


def _status_label(passed: bool | None) -> str:
    if passed is None:
        return "N/A"
    return "PASS" if passed else "FAIL"


def _print_stream_event(node: str, update: dict[str, Any], state: AgentState) -> None:
    if node == "generate":
        print("[generate] Writing code and self-tests...")
    elif node == "execute":
        ai = _status_label(update.get("self_test_passed"))
        he = (
            _status_label(update.get("humaneval_passed"))
            if state.get("humaneval_test_code")
            else "skipped"
        )
        overall = _status_label(update.get("passed"))
        attempt = update.get("attempts", state.get("attempts", 0))
        print(f"[execute] Attempt {attempt}: overall={overall} | AI={ai} | HumanEval={he}")
        if not update.get("passed") and update.get("output"):
            preview = update["output"].strip().splitlines()[-3:]
            print("  last errors:")
            for line in preview:
                print(f"    {line}")
    elif node == "fix":
        print(f"[fix] Rewriting code after failed tests (attempt {state.get('attempts', 0)})...")


def print_run_summary(result: AgentState) -> None:
    overall = _status_label(result.get("passed"))
    print("=" * 60)
    print(f"Overall: {overall} after {result.get('attempts')} attempt(s)")
    print(f"AI self-tests: {_status_label(result.get('self_test_passed'))}")
    if result.get("humaneval_test_code"):
        print(f"HumanEval tests: {_status_label(result.get('humaneval_passed'))}")
    failure = format_failure_summary(result)
    if failure:
        print(f"\nNote: {failure}")
    print("=" * 60)
    print("\n--- snippet.py ---\n")
    print(result.get("code", ""))
    print("\n--- test_snippet.py ---\n")
    print(result.get("test_code", ""))
    print("\n--- last sandbox output ---\n")
    print(result.get("output", ""))


def run_executo(
    task: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    model: str = DEFAULT_MODEL,
    humaneval_task_id: str | None = None,
    humaneval_dataset: Path | None = None,
    stream: bool = False,
) -> AgentState:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    if not docker_available():
        raise RuntimeError("Docker is not installed or not in PATH.")

    agent = build_agent()

    humaneval_test_code = ""
    if humaneval_task_id:
        dataset = humaneval_dataset or DEFAULT_DATASET
        if not dataset.exists():
            raise RuntimeError(
                f"HumanEval dataset not found: {dataset}. "
                "Run: python download_coding_datasets.py"
            )
        row = load_task(dataset, humaneval_task_id)
        humaneval_test_code = build_humaneval_test(row["entry_point"], row["test"])
        task = f"Complete the following Python function:\n\n{row['prompt']}"

    initial_state: AgentState = {
        "task": task,
        "max_attempts": max_attempts,
        "model": model,
        "humaneval_test_code": humaneval_test_code,
    }

    if not stream:
        return agent.invoke(initial_state)

    print("Streaming agent progress...\n")
    final_state: AgentState = dict(initial_state)
    for event in agent.stream(initial_state, stream_mode="updates"):
        for node, update in event.items():
            final_state.update(update)
            if stream:
                _print_stream_event(node, update, final_state)
    return final_state


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Executo — natural language to self-correcting Python."
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Natural-language coding task.",
    )
    parser.add_argument(
        "--humaneval",
        metavar="ID",
        help="Run a HumanEval task instead (e.g. HumanEval/0).",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Print live progress as the agent runs.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Max execute attempts (default: {DEFAULT_MAX_ATTEMPTS}).",
    )
    return parser


def _main() -> int:
    import sys

    parser = _build_cli_parser()
    args = parser.parse_args()

    task = " ".join(args.task).strip()
    if not task and not args.humaneval:
        task = "Write a function add(a, b) that returns the sum of two numbers."

    if args.humaneval:
        print(f"HumanEval task: {args.humaneval}\n")
    elif task:
        print(f"Task: {task}\n")

    try:
        result = run_executo(
            task,
            max_attempts=args.max_attempts,
            humaneval_task_id=args.humaneval,
            stream=args.stream,
        )
    except RuntimeError as exc:
        print(format_setup_error(str(exc)), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(format_llm_error(str(exc)), file=sys.stderr)
        return 1

    print_run_summary(result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
