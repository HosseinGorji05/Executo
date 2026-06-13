#!/usr/bin/env python3
"""Run Executo on a HumanEval task (AI + HumanEval tests in one loop).

Usage:
  python eval_humaneval.py
  python eval_humaneval.py HumanEval/0
  python eval_humaneval.py HumanEval/0 --stream
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.agent import print_run_summary, run_executo
from core.errors import format_setup_error
from core.humaneval import DEFAULT_DATASET, load_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Executo against a HumanEval task."
    )
    parser.add_argument(
        "task_id",
        nargs="?",
        default="HumanEval/0",
        help="HumanEval task id (default: HumanEval/0).",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Path to HumanEval.jsonl (default: {DEFAULT_DATASET}).",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Show live agent progress.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=4,
        help="Max execute attempts (default: 4).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        print("Run: python download_coding_datasets.py", file=sys.stderr)
        return 2

    task = load_task(args.dataset, args.task_id)
    print(f"HumanEval task: {task['task_id']}")
    print(f"Function: {task['entry_point']}\n")

    try:
        result = run_executo(
            "",
            humaneval_task_id=args.task_id,
            humaneval_dataset=args.dataset,
            max_attempts=args.max_attempts,
            stream=args.stream,
        )
    except RuntimeError as exc:
        print(format_setup_error(str(exc)), file=sys.stderr)
        return 2

    if not result.get("code"):
        print("Agent returned no code.", file=sys.stderr)
        return 1

    print_run_summary(result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
