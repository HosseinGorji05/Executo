"""Tests for core.errors."""

from __future__ import annotations

import unittest

from core.errors import format_failure_summary, format_llm_error, format_setup_error


class TestFormatSetupError(unittest.TestCase):
    def test_groq_api_key_missing(self) -> None:
        msg = format_setup_error("GROQ_API_KEY is not set")
        self.assertIn("Groq API key missing", msg)
        self.assertIn("console.groq.com", msg)

    def test_docker_missing(self) -> None:
        msg = format_setup_error("Docker is not installed or not in PATH.")
        self.assertIn("Docker is not available", msg)

    def test_generic_setup_error(self) -> None:
        msg = format_setup_error("something else")
        self.assertIn("Setup error: something else", msg)


class TestFormatLlmError(unittest.TestCase):
    def test_model_not_found(self) -> None:
        msg = format_llm_error(
            "The model `old-model` does not exist or you do not have access to it."
        )
        self.assertIn("Groq model not found", msg)
        self.assertIn("openai/gpt-oss-20b", msg)

    def test_rate_limit(self) -> None:
        msg = format_llm_error("Error 429: rate_limit exceeded")
        self.assertIn("Groq rate limit hit", msg)

    def test_invalid_api_key(self) -> None:
        msg = format_llm_error("401 invalid_api_key")
        self.assertIn("Invalid Groq API key", msg)

    def test_generic_llm_error(self) -> None:
        msg = format_llm_error("unexpected boom")
        self.assertEqual(msg, "LLM error: unexpected boom")


class TestFormatFailureSummary(unittest.TestCase):
    def test_passed_returns_none(self) -> None:
        self.assertIsNone(format_failure_summary({"passed": True}))

    def test_self_tests_failed(self) -> None:
        summary = format_failure_summary(
            {"passed": False, "self_test_passed": False, "attempts": 2, "max_attempts": 4}
        )
        self.assertIn("AI self-tests did not pass", summary)

    def test_humaneval_failed(self) -> None:
        summary = format_failure_summary(
            {
                "passed": False,
                "self_test_passed": True,
                "humaneval_test_code": "import unittest",
                "humaneval_passed": False,
                "attempts": 3,
                "max_attempts": 4,
            }
        )
        self.assertIn("HumanEval fixed tests did not pass", summary)

    def test_timeout_and_max_attempts(self) -> None:
        summary = format_failure_summary(
            {
                "passed": False,
                "timed_out": True,
                "self_test_passed": False,
                "attempts": 4,
                "max_attempts": 4,
            }
        )
        self.assertIn("Sandbox timed out", summary)
        self.assertIn("Stopped after 4 attempt(s)", summary)


if __name__ == "__main__":
    unittest.main()
