#!/usr/bin/env python3
"""Run Executo on multiple HumanEval tasks and report pass rate.

Usage:
  python eval_humaneval_batch.py
  python eval_humaneval_batch.py --limit 10
  python eval_humaneval_batch.py --limit 20 --stream
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from core.agent import run_executo
from core.errors import format_setup_error
from core.humaneval import DEFAULT_DATASET, iter_tasks


def _status(passed: bool | None) -> str:
    return "PASS" if passed else "FAIL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-evaluate Executo on HumanEval tasks."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of tasks to run (default: 10).",
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
        help="Show live agent progress for each task.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=4,
        help="Max execute attempts per task (default: 4).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        print("Run: python download_coding_datasets.py", file=sys.stderr)
        return 2

    tasks = iter_tasks(args.dataset, limit=args.limit)
    if not tasks:
        print("No tasks found in dataset.", file=sys.stderr)
        return 2

    print(f"Running {len(tasks)} HumanEval task(s)...\n")
    passed = 0
    rows: list[tuple[str, bool, int]] = []

    for index, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        print(f"--- [{index}/{len(tasks)}] {task_id} ({task['entry_point']}) ---")
        try:
            result = run_executo(
                "",
                humaneval_task_id=task_id,
                humaneval_dataset=args.dataset,
                max_attempts=args.max_attempts,
                stream=args.stream,
            )
        except RuntimeError as exc:
            print(format_setup_error(str(exc)), file=sys.stderr)
            return 2

        ok = bool(result.get("passed"))
        attempts = int(result.get("attempts") or 0)
        if ok:
            passed += 1
        rows.append((task_id, ok, attempts))
        print(
            f"  -> {_status(ok)} in {attempts} attempt(s) | "
            f"AI={_status(result.get('self_test_passed'))} | "
            f"HE={_status(result.get('humaneval_passed'))}\n"
        )
        time.sleep(0.5)

    rate = (passed / len(tasks)) * 100
    print("=" * 60)
    print(f"BATCH RESULT: {passed}/{len(tasks)} passed ({rate:.0f}%)")
    print("=" * 60)
    for task_id, ok, attempts in rows:
        print(f"  {task_id}: {_status(ok)} ({attempts} attempts)")

    return 0 if passed == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
