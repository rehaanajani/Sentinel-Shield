import intelligence
from intelligence import IntelligenceLayer, market_is_open
from datetime import datetime, timezone


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_market_hours_follow_eastern_time():
    assert market_is_open(utc("2026-07-15T13:35"))       # 9:35 EDT
    assert not market_is_open(utc("2026-07-15T13:25"))   # 9:25 EDT
    assert market_is_open(utc("2026-01-15T14:35"))       # 9:35 EST
    assert not market_is_open(utc("2026-07-15T20:30"))   # 16:30 EDT
    assert not market_is_open(utc("2026-07-18T15:00"))   # Saturday


def test_rejects_outside_market_hours(monkeypatch):
    monkeypatch.setattr(intelligence, "market_is_open", lambda now=None: False)
    result = IntelligenceLayer().check({"action": "BUY", "ticker": "AAPL", "amount": 100})
    assert result["status"] == "rejected"
    assert "Market hours" in result["reasons"][0]


def test_approval_commits_exposure(market_open):
    IntelligenceLayer().check({"action": "BUY", "ticker": "AAPL", "amount": 500})
    assert IntelligenceLayer().state()["per_ticker"]["AAPL"] == 500


def test_commit_false_defers_exposure(market_open):
    layer = IntelligenceLayer()
    intent = {"action": "BUY", "ticker": "AAPL", "amount": 500}
    assert layer.check(intent, commit=False)["status"] == "approved"
    assert IntelligenceLayer().state()["per_ticker"] == {}
    layer.commit(intent)
    assert IntelligenceLayer().state()["per_ticker"]["AAPL"] == 500


def test_per_ticker_cap(market_open):
    for amount in (2000, 2000):
        IntelligenceLayer().check({"action": "BUY", "ticker": "AAPL", "amount": amount})
    result = IntelligenceLayer().check({"action": "BUY", "ticker": "AAPL", "amount": 1500})
    assert result["status"] == "rejected"
    assert any("Exposure limit" in r for r in result["reasons"])


def test_scope_escalation(market_open):
    result = IntelligenceLayer().check(
        {"action": "BUY", "ticker": "AAPL", "amount": 100, "scope": "research"})
    assert any("Scope escalation" in r for r in result["reasons"])


def test_bot_detection(market_open):
    intent = {"action": "BUY", "ticker": "MSFT", "amount": 10}
    for _ in range(3):
        IntelligenceLayer().check(intent)
    result = IntelligenceLayer().check(intent)
    assert any("Bot-like" in r for r in result["reasons"])
