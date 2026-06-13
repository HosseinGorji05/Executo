
#!/usr/bin/env python3


"""
Usage:
Load HumanEval tasks and build unittest wrappers for the sandbox
"""

from __future__ import annotations

import json
from pathlib import Path



DEFAULT_DATASET = Path("data/datasets/HumanEval.jsonl")



def load_task(dataset_path: Path, task_id: str) -> dict:
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["task_id"] == task_id:
                return row
    raise ValueError(f"Task not found: {task_id}")


def iter_tasks(dataset_path: Path, limit: int | None = None) -> list[dict]:
    tasks: list[dict] = []
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            tasks.append(json.loads(line))
            if limit is not None and len(tasks) >= limit:
                break
    return tasks




def build_humaneval_test(entry_point: str, test_body: str) -> str:
    return f"""import unittest
from snippet import {entry_point}

{test_body}

class TestHumanEval(unittest.TestCase):
    def test_task(self):
        check({entry_point})

if __name__ == "__main__":
    unittest.main()
"""