"""Tests for core.sandbox."""

from __future__ import annotations

import unittest

from core.sandbox import SandboxResult, docker_available, run_code_with_tests

PASSING_CODE = """def add(a, b):
    return a + b
"""

PASSING_TESTS = """import unittest
from snippet import add

class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
"""


class TestSandboxResult(unittest.TestCase):
    def test_summary_pass(self) -> None:
        result = SandboxResult(passed=True, returncode=0, output="")
        self.assertEqual(result.summary, "PASS")

    def test_summary_fail(self) -> None:
        result = SandboxResult(passed=False, returncode=1, output="boom")
        self.assertEqual(result.summary, "FAIL")

    def test_summary_timeout(self) -> None:
        result = SandboxResult(passed=False, returncode=124, output="", timed_out=True)
        self.assertEqual(result.summary, "TIMEOUT")


@unittest.skipUnless(docker_available(), "Docker is not available")
class TestDockerSandbox(unittest.TestCase):
    def test_run_code_with_tests_passes_valid_code(self) -> None:
        result = run_code_with_tests(PASSING_CODE, PASSING_TESTS, timeout=120)
        self.assertTrue(result.passed, result.output)
        self.assertEqual(result.returncode, 0)

    def test_run_code_with_tests_fails_bad_code(self) -> None:
        bad_code = "def add(a, b):\n    return a - b\n"
        result = run_code_with_tests(bad_code, PASSING_TESTS, timeout=120)
        self.assertFalse(result.passed)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
