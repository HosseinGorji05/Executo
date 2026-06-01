#!/usr/bin/env python3
"""
Run a Python unit test against a code snippet in an isolated Docker container.

Usage:
  python run_isolated_unittest.py --code-file snippet.py --test-file test_snippet.py
  python run_isolated_unittest.py --code-file snippet.py --test-file test_snippet.py --image python:3.12-slim
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a short-lived Docker container, run python -m unittest, "
            "and report pass/fail."
        )
    )
    parser.add_argument(
        "--code-file",
        required=True,
        type=Path,
        help="Path to the Python code snippet file under test.",
    )
    parser.add_argument(
        "--test-file",
        required=True,
        type=Path,
        help="Path to the Python unittest file.",
    )
    parser.add_argument(
        "--image",
        default="python:3.12-slim",
        help="Docker image to use (default: python:3.12-slim).",
    )
    return parser.parse_args()


def validate_input_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{label} must be a file: {path}")


def run_unittest_in_docker(code_file: Path, test_file: Path, image: str) -> int:
    with tempfile.TemporaryDirectory(prefix="isolated-unittest-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        container_code_name = "snippet.py"
        container_test_name = "test_snippet.py"

        shutil.copy2(code_file, tmp_dir / container_code_name)
        shutil.copy2(test_file, tmp_dir / container_test_name)

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--workdir",
            "/workspace",
            "--volume",
            f"{tmp_dir}:/workspace:ro",
            image,
            "python",
            "-m",
            "unittest",
            container_test_name,
        ]

        completed = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        output = (completed.stdout or "") + (completed.stderr or "")
        if output.strip():
            print(output.rstrip())

        if completed.returncode == 0:
            print("PASS")
        else:
            print("FAIL")

        return completed.returncode


def main() -> int:
    args = parse_args()

    try:
        validate_input_file(args.code_file, "--code-file")
        validate_input_file(args.test_file, "--test-file")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    try:
        return run_unittest_in_docker(args.code_file, args.test_file, args.image)
    except FileNotFoundError:
        print(
            "Docker is not installed or not available in PATH. "
            "Install Docker and try again.",
            file=sys.stderr,
        )
        return 3
    except subprocess.SubprocessError as exc:
        print(f"Docker execution error: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
