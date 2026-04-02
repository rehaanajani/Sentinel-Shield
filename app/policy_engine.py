"""
app/policy_engine.py — SentinelShield v2
=========================================
Reads and validates the ArmorClaw policy file (armoriq.policy.json).
Used by the FastAPI /policy endpoint and by the pre-execution gate.
"""

import json
import os

POLICY_PATH = os.path.expanduser("~/.openclaw/armoriq.policy.json")

DEFAULT_POLICY = {
    "allow_tools": ["alpaca_buy", "alpaca_sell", "alpaca_get_account", "alpaca_get_positions"],
    "deny_tools":  ["bash", "write", "exec", "browser"],
    "financial_constraints": {
        "max_trade_usd":    2000,
        "min_trade_usd":    1,
        "allowed_tickers":  ["AAPL", "MSFT", "GOOGL", "AMZN"],
        "allowed_actions":  ["BUY", "SELL"],
    }
}


def load_policy() -> dict:
    """Load the ArmorClaw policy. Falls back to DEFAULT_POLICY if file missing."""
    if os.path.exists(POLICY_PATH):
        try:
            with open(POLICY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_POLICY


def validate_against_policy(action: str, ticker: str, amount: float) -> list[str]:
    """
    Run the same per-trade checks ArmorClaw performs, for the /simulate endpoint.
    Returns list of violation reasons (empty = OK).
    """
    policy = load_policy()
    fc     = policy.get("financial_constraints", {})
    reasons = []

    allowed_tickers = [t.upper() for t in fc.get("allowed_tickers", [])]
    if ticker.upper() not in allowed_tickers:
        reasons.append(f"Ticker '{ticker}' is not in the policy allowlist: {allowed_tickers}")

    max_trade = fc.get("max_trade_usd", 2000)
    if amount > max_trade:
        reasons.append(f"Trade amount ${amount:,.0f} exceeds policy max ${max_trade:,.0f}")

    min_trade = fc.get("min_trade_usd", 1)
    if amount < min_trade:
        reasons.append(f"Trade amount ${amount:,.0f} is below policy min ${min_trade:,.0f}")

    allowed_actions = [a.upper() for a in fc.get("allowed_actions", [])]
    if action.upper() not in allowed_actions:
        reasons.append(f"Action '{action}' is not in the policy allowlist: {allowed_actions}")

    return reasons
