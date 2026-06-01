#!/usr/bin/env python3
"""
Download open-source coding datasets for prompt+test training/eval loops.

Usage:
  python download_coding_datasets.py
  python download_coding_datasets.py --output-dir data/datasets
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
from pathlib import Path


DATASET_URLS = {
    "HumanEval.jsonl.gz": "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz",
    "mbpp.jsonl": "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl",
    "sanitized-mbpp.json": "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/sanitized-mbpp.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download HumanEval and MBPP datasets to a local directory."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/datasets"),
        help="Directory to store downloaded datasets (default: data/datasets).",
    )
    return parser.parse_args()


def download_with_curl(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-fsSL", url, "-o", str(destination)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("curl is not installed or not in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to download {url}. curl exited with code {exc.returncode}."
        ) from exc


def gunzip_file(source: Path, destination: Path) -> None:
    with gzip.open(source, "rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading datasets to: {output_dir}")
    for filename, url in DATASET_URLS.items():
        target = output_dir / filename
        print(f"- {filename}")
        download_with_curl(url, target)

    gz_path = output_dir / "HumanEval.jsonl.gz"
    plain_path = output_dir / "HumanEval.jsonl"
    gunzip_file(gz_path, plain_path)

    print("Done.")
    print(f"HumanEval (jsonl): {plain_path}")
    print(f"MBPP (jsonl): {output_dir / 'mbpp.jsonl'}")
    print(f"MBPP sanitized (json): {output_dir / 'sanitized-mbpp.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
