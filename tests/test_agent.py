"""Tests for core.agent parsing and routing helpers."""

from __future__ import annotations

import unittest

from core.agent import (
    DEFAULT_MAX_ATTEMPTS,
    _format_execute_output,
    _route_after_execute,
    build_agent,
    parse_solution_and_tests,
)
from core.sandbox import SandboxResult


SAMPLE_LLM_RESPONSE = """### SOLUTION
```python
def add(a, b):
    return a + b
```

### TESTS
```python
import unittest
from snippet import add

class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
```
"""


class TestParseSolutionAndTests(unittest.TestCase):
    def test_parses_labeled_sections(self) -> None:
        solution, tests = parse_solution_and_tests(SAMPLE_LLM_RESPONSE)
        self.assertIn("def add", solution)
        self.assertIn("from snippet import add", tests)

    def test_falls_back_to_positional_fences(self) -> None:
        text = """```python
def mul(a, b):
    return a * b
```
```python
import unittest
from snippet import mul
```
"""
        solution, tests = parse_solution_and_tests(text)
        self.assertIn("def mul", solution)
        self.assertIn("from snippet import mul", tests)

    def test_uses_fallback_test_when_only_one_block(self) -> None:
        text = "```python\ndef x(): pass\n```"
        fallback = "import unittest"
        _, tests = parse_solution_and_tests(text, fallback_test=fallback)
        self.assertEqual(tests, fallback)


class TestRouteAfterExecute(unittest.TestCase):
    def test_done_when_passed(self) -> None:
        self.assertEqual(_route_after_execute({"passed": True, "attempts": 1}), "done")

    def test_fix_when_failed_with_retries_left(self) -> None:
        state = {"passed": False, "attempts": 1, "max_attempts": DEFAULT_MAX_ATTEMPTS}
        self.assertEqual(_route_after_execute(state), "fix")

    def test_done_when_max_attempts_reached(self) -> None:
        state = {"passed": False, "attempts": 4, "max_attempts": 4}
        self.assertEqual(_route_after_execute(state), "done")


class TestFormatExecuteOutput(unittest.TestCase):
    def test_empty_when_both_pass(self) -> None:
        self_result = SandboxResult(passed=True, returncode=0, output="")
        self.assertEqual(_format_execute_output(self_result, None), "")

    def test_includes_ai_and_humaneval_failures(self) -> None:
        self_result = SandboxResult(passed=False, returncode=1, output="AI fail")
        he_result = SandboxResult(passed=False, returncode=1, output="HE fail")
        output = _format_execute_output(self_result, he_result)
        self.assertIn("AI self-tests FAILED", output)
        self.assertIn("HumanEval tests FAILED", output)
        self.assertIn("AI fail", output)
        self.assertIn("HE fail", output)


class TestBuildAgent(unittest.TestCase):
    def test_compiles_graph(self) -> None:
        agent = build_agent()
        self.assertIsNotNone(agent)


if __name__ == "__main__":
    unittest.main()
