"""User-friendly error messages for Executo."""

from __future__ import annotations


def format_setup_error(message: str) -> str:
    if "GROQ_API_KEY" in message:
        return (
            "Groq API key missing.\n"
            "Copy .env.example to .env and add your key from https://console.groq.com/keys"
        )
    if "Docker" in message:
        return (
            "Docker is not available.\n"
            "Start Docker Desktop, then try again."
        )
    return f"Setup error: {message}"


def format_llm_error(message: str) -> str:
    lower = message.lower()
    if "429" in message or "rate_limit" in lower or "resource_exhausted" in lower:
        return (
            "Groq rate limit hit.\n"
            "Wait a minute or set GROQ_MODEL=llama-3.1-8b-instant in .env.\n"
            "Dashboard: https://console.groq.com/"
        )
    if "invalid_api_key" in lower or "401" in message:
        return (
            "Invalid Groq API key.\n"
            "Check GROQ_API_KEY in .env (keys start with gsk_)."
        )
    return f"LLM error: {message}"


def format_failure_summary(result: dict) -> str | None:
    if result.get("passed"):
        return None

    lines: list[str] = []
    attempts = result.get("attempts", 0)
    max_attempts = result.get("max_attempts", 4)

    if result.get("timed_out"):
        lines.append("Sandbox timed out — code may be too slow or stuck in a loop.")

    if not result.get("self_test_passed"):
        lines.append("AI self-tests did not pass.")
    if result.get("humaneval_test_code") and not result.get("humaneval_passed"):
        lines.append("HumanEval fixed tests did not pass.")

    if attempts >= max_attempts:
        lines.append(f"Stopped after {attempts} attempt(s) (limit: {max_attempts}).")

    return "\n".join(lines) if lines else "Tests did not pass."
