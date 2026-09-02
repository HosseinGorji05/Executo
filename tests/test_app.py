"""Smoke tests for the Gradio UI."""

from __future__ import annotations

import unittest


class TestAppImport(unittest.TestCase):
    def test_app_imports(self) -> None:
        import app  # noqa: F401

    def test_build_ui_returns_blocks(self) -> None:
        import gradio as gr

        from app import build_ui

        demo = build_ui()
        self.assertIsInstance(demo, gr.Blocks)


if __name__ == "__main__":
    unittest.main()
