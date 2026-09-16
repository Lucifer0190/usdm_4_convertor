"""Pytest configuration.

Forces the deterministic (no-LLM) path so the suite is fast, free, offline, and
reproducible even when an OpenRouter/Anthropic key is present in the environment.
The Assurance ensemble's deterministic members carry the run; the LLM member is
exercised manually via the CLI, not in unit tests.
"""
import os

os.environ["USDM4_NO_LLM"] = "1"
