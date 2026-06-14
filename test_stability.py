#!/usr/bin/env python3
"""test_stability.py — Week 4 stability test: run 20+ prompts and report pass rate.

Usage:
    python test_stability.py                  # all 20 prompts
    python test_stability.py --limit 10       # first N prompts
    python test_stability.py --stream         # show live progress per prompt
    python test_stability.py --out results.json  # save detailed results

Prompts are graded Easy / Medium / Hard so you can see where failures cluster.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from core.agent import DEFAULT_MAX_ATTEMPTS, run_executo
from core.errors import format_setup_error, format_llm_error

# ---------------------------------------------------------------------------
# Prompt bank (20+ prompts, three difficulty tiers)
# ---------------------------------------------------------------------------

PROMPTS: list[dict] = [
    # ── Easy (tier 1) ──────────────────────────────────────────────────────
    {
        "id": "E01",
        "tier": "Easy",
        "task": (
            "Write a function add(a, b) that returns the sum of two numbers. "
            "Works for ints and floats."
        ),
    },
    {
        "id": "E02",
        "tier": "Easy",
        "task": (
            "Write a function reverse_string(s) that returns the string s reversed. "
            "reverse_string('hello') == 'olleh'."
        ),
    },
    {
        "id": "E03",
        "tier": "Easy",
        "task": (
            "Write a function count_vowels(s) that returns the number of vowels "
            "(a e i o u, case-insensitive) in the string s."
        ),
    },
    {
        "id": "E04",
        "tier": "Easy",
        "task": (
            "Write a function is_palindrome(s) that returns True if s is a palindrome "
            "ignoring spaces and case. 'Race a car' -> False, 'racecar' -> True."
        ),
    },
    {
        "id": "E05",
        "tier": "Easy",
        "task": (
            "Write a function factorial(n) that returns n! for non-negative integers. "
            "factorial(0) == 1. Raise ValueError for negative input."
        ),
    },
    {
        "id": "E06",
        "tier": "Easy",
        "task": (
            "Write a function celsius_to_fahrenheit(c) that converts Celsius to "
            "Fahrenheit. Formula: F = C * 9/5 + 32."
        ),
    },
    {
        "id": "E07",
        "tier": "Easy",
        "task": (
            "Write a function sum_list(lst) that returns the sum of all numbers in a list. "
            "sum_list([]) == 0."
        ),
    },
    # ── Medium (tier 2) ────────────────────────────────────────────────────
    {
        "id": "M01",
        "tier": "Medium",
        "task": (
            "Write a function fibonacci(n) that returns the nth Fibonacci number. "
            "fib(0)=0, fib(1)=1, fib(2)=1, fib(10)=55. Raise ValueError for n<0."
        ),
    },
    {
        "id": "M02",
        "tier": "Medium",
        "task": (
            "Write a function is_prime(n) that returns True if n is prime. "
            "is_prime(2)=True, is_prime(1)=False, is_prime(0)=False, is_prime(-5)=False."
        ),
    },
    {
        "id": "M03",
        "tier": "Medium",
        "task": (
            "Write a function merge_sorted(a, b) that merges two sorted lists into "
            "one sorted list without using sort(). merge_sorted([1,3],[2,4]) == [1,2,3,4]."
        ),
    },
    {
        "id": "M04",
        "tier": "Medium",
        "task": (
            "Write a function is_leap_year(year) that returns True for leap years. "
            "Rules: div by 4 → leap, EXCEPT div by 100 → not leap, EXCEPT div by 400 → leap. "
            "1900=False, 2000=True, 2024=True, 2100=False."
        ),
    },
    {
        "id": "M05",
        "tier": "Medium",
        "task": (
            "Write a function flatten(lst) that flattens one level of nesting. "
            "flatten([[1,2],[3,[4]]]) == [1,2,3,[4]]. Strings are not flattened."
        ),
    },
    {
        "id": "M06",
        "tier": "Medium",
        "task": (
            "Write a function word_frequency(text) that returns a dict of word → count, "
            "case-insensitive, ignoring punctuation. "
            "word_frequency('Hello world hello') == {'hello':2,'world':1}."
        ),
    },
    {
        "id": "M07",
        "tier": "Medium",
        "task": (
            "Write a function two_sum(nums, target) that returns the indices [i, j] "
            "of two distinct elements that add up to target. Exactly one solution exists. "
            "Return the pair with the smaller index first."
        ),
    },
    {
        "id": "M08",
        "tier": "Medium",
        "task": (
            "Write a function remove_duplicates(lst) that returns a new list with "
            "duplicates removed, preserving the original order."
        ),
    },
    # ── Hard (tier 3) ──────────────────────────────────────────────────────
    {
        "id": "H01",
        "tier": "Hard",
        "task": (
            "Write a function roman_to_int(s) that converts a Roman numeral string to "
            "an integer. Handle subtractive notation: IV=4, IX=9, XL=40, XC=90, "
            "CD=400, CM=900. Invalid characters must raise ValueError."
        ),
    },
    {
        "id": "H02",
        "tier": "Hard",
        "task": (
            "Write a function is_balanced(s) that returns True if parentheses (), "
            "brackets [], and braces {} in s are properly balanced and nested. "
            "is_balanced('([{}])') == True, is_balanced('([)]') == False."
        ),
    },
    {
        "id": "H03",
        "tier": "Hard",
        "task": (
            "Write a function merge_intervals(intervals) that merges overlapping intervals. "
            "Input: list of [start, end] pairs (may be unsorted). "
            "merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]."
        ),
    },
    {
        "id": "H04",
        "tier": "Hard",
        "task": (
            "Write a function deep_flatten(lst) that fully flattens arbitrarily nested lists. "
            "Do NOT flatten strings, dicts, or tuples. "
            "deep_flatten([1,[2,[3,[4]]],'hi',{'a':1}]) == [1,2,3,4,'hi',{'a':1}]."
        ),
    },
    {
        "id": "H05",
        "tier": "Hard",
        "task": (
            "Write a function longest_palindrome(s) that returns the longest palindromic "
            "substring of s. For 'babad' return 'bab' or 'aba'. "
            "For '' return ''. For a single char return that char."
        ),
    },
    {
        "id": "H06",
        "tier": "Hard",
        "task": (
            "Write a function group_anagrams(words) that groups a list of strings into "
            "sublists of anagrams. Order within groups and order of groups don't matter. "
            "group_anagrams(['eat','tea','tan','ate','nat','bat']) -> "
            "[['eat','tea','ate'],['tan','nat'],['bat']] (any order)."
        ),
    },
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    id: str
    tier: str
    task: str
    passed: bool
    attempts: int
    elapsed_seconds: float
    error: str = ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_prompt(prompt: dict, stream: bool, max_attempts: int) -> PromptResult:
    pid = prompt["id"]
    task = prompt["task"]
    tier = prompt["tier"]

    t0 = time.time()
    try:
        result = run_executo(task, max_attempts=max_attempts)
        elapsed = time.time() - t0
        return PromptResult(
            id=pid,
            tier=tier,
            task=task,
            passed=bool(result.get("passed")),
            attempts=result.get("attempts", 0),
            elapsed_seconds=round(elapsed, 1),
        )
    except RuntimeError as exc:
        elapsed = time.time() - t0
        return PromptResult(
            id=pid,
            tier=tier,
            task=task,
            passed=False,
            attempts=0,
            elapsed_seconds=round(elapsed, 1),
            error=format_setup_error(str(exc)),
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - t0
        return PromptResult(
            id=pid,
            tier=tier,
            task=task,
            passed=False,
            attempts=0,
            elapsed_seconds=round(elapsed, 1),
            error=format_llm_error(str(exc)),
        )


def print_result(r: PromptResult) -> None:
    status = "✅ PASS" if r.passed else "❌ FAIL"
    print(f"  [{r.id}] {status} | {r.attempts} attempt(s) | {r.elapsed_seconds}s")
    if r.error:
        short_err = r.error.splitlines()[0][:120]
        print(f"        ⚠ {short_err}")


def print_summary(results: list[PromptResult]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pct = round(100 * passed / total) if total else 0

    print()
    print("=" * 60)
    print(f"  STABILITY TEST RESULTS — {passed}/{total} passed ({pct}%)")
    print("=" * 60)

    for tier in ("Easy", "Medium", "Hard"):
        tier_results = [r for r in results if r.tier == tier]
        if not tier_results:
            continue
        t_pass = sum(1 for r in tier_results if r.passed)
        print(f"  {tier:8s}  {t_pass}/{len(tier_results)}")

    fails = [r for r in results if not r.passed]
    if fails:
        print()
        print("  Failed prompts:")
        for r in fails:
            short_task = r.task[:70] + ("…" if len(r.task) > 70 else "")
            print(f"    [{r.id}] {short_task}")
            if r.error:
                print(f"           ⚠ {r.error.splitlines()[0][:100]}")

    avg_attempts = (
        sum(r.attempts for r in results) / total if total else 0
    )
    total_time = sum(r.elapsed_seconds for r in results)
    print()
    print(f"  Avg attempts per prompt : {avg_attempts:.1f}")
    print(f"  Total wall time         : {total_time:.0f}s")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Executo stability test suite")
    parser.add_argument("--limit", type=int, default=len(PROMPTS), help="Run first N prompts")
    parser.add_argument("--stream", action="store_true", help="Show agent output per prompt")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--out", type=str, default="", help="Save JSON results to file")
    parser.add_argument("--tier", choices=["Easy", "Medium", "Hard"], help="Run only one tier")
    args = parser.parse_args()

    prompts = PROMPTS
    if args.tier:
        prompts = [p for p in prompts if p["tier"] == args.tier]
    prompts = prompts[: args.limit]

    print(f"\n⚡ Executo stability test — {len(prompts)} prompt(s)\n")

    results: list[PromptResult] = []
    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] {prompt['tier']} {prompt['id']}: {prompt['task'][:60]}…")
        result = run_prompt(prompt, stream=args.stream, max_attempts=args.max_attempts)
        results.append(result)
        print_result(result)
        print()

    print_summary(results)

    if args.out:
        path = Path(args.out)
        path.write_text(json.dumps([asdict(r) for r in results], indent=2))
        print(f"\n  Results saved to {path}")


if __name__ == "__main__":
    main()
