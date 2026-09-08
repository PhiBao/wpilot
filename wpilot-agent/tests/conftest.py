"""Hermetic AWS env for tests.

Agent construction resolves real provider chains (BedrockModel builds a
boto3 client at init), so ambient credentials or provider keys would make
tests order- and machine-dependent. Every test gets dummy static creds and
no provider keys; tests for resolve_model() set exactly what they need.
"""

import os

import pytest

_SCRUB_PREFIXES = ("AWS_", "ANTHROPIC_", "OPENAI_", "BEDROCK_")


@pytest.fixture(autouse=True)
def _hermetic_aws_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(_SCRUB_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
