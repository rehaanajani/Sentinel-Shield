import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import input_sanitizer  # noqa: E402
import intelligence  # noqa: E402
from app import logger  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point every state/log file at a temp dir so tests never touch real data."""
    monkeypatch.setattr(intelligence, "EXPOSURE_F", str(tmp_path / "exposure.json"))
    monkeypatch.setattr(intelligence, "BEHAVIOR_F", str(tmp_path / "behavior_log.json"))
    monkeypatch.setattr(intelligence, "AUDIT_LOG", str(tmp_path / "audit_log.jsonl"))
    monkeypatch.setattr(input_sanitizer, "AUDIT_LOG", str(tmp_path / "audit_log.jsonl"))
    monkeypatch.setattr(logger, "LOG_PATH", str(tmp_path / "sentinel.log"))
    return tmp_path


@pytest.fixture
def market_open(monkeypatch):
    monkeypatch.setattr(intelligence, "market_is_open", lambda now=None: True)
