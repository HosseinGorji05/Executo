"""Tests for core.humaneval."""

from __future__ import annotations

import unittest
from pathlib import Path

from core.humaneval import build_humaneval_test, iter_tasks, load_task

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "humaneval_sample.jsonl"


class TestHumanEvalHelpers(unittest.TestCase):
    def test_load_task_returns_matching_row(self) -> None:
        row = load_task(FIXTURE, "HumanEval/0")
        self.assertEqual(row["entry_point"], "add")
        self.assertIn("def add", row["prompt"])

    def test_load_task_raises_for_missing_id(self) -> None:
        with self.assertRaises(ValueError):
            load_task(FIXTURE, "HumanEval/999")

    def test_iter_tasks_respects_limit(self) -> None:
        tasks = iter_tasks(FIXTURE, limit=1)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "HumanEval/0")

    def test_build_humaneval_test_wraps_entry_point(self) -> None:
        test_code = build_humaneval_test(
            "add",
            "def check(candidate):\n    assert candidate(1, 2) == 3",
        )
        self.assertIn("from snippet import add", test_code)
        self.assertIn("class TestHumanEval", test_code)
        self.assertIn("check(add)", test_code)


if __name__ == "__main__":
    unittest.main()
