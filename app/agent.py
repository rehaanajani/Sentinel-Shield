"""
app/agent.py — SentinelShield v2
==================================
Python-based agent fallback runner.

This module provides a pure-Python demo agent that simulates the OpenClaw
reasoning loop WITHOUT requiring OpenClaw to be installed. It's used for:
  - Hackathon judges who want to see the full chain in a single Python process
  - Direct API testing via POST /agent/run on the FastAPI server
  - Local development / CI testing

Flow:
  User message
    → Input Sanitizer (Layer 1)
    → Intent Parser (simple regex-based, no LLM required for demo)
    → Intelligence Layer (Layer 3)
    → PolicyEngine check (Layer 4 mirror - ArmorClaw logic in Python)
    → alpaca_actions.py (Layer 5, optional - requires Alpaca keys)
"""

import re
import os
import sys
import json
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from input_sanitizer import sanitize_input
from intelligence import IntelligenceLayer
from app.policy_engine import validate_against_policy
from app.logger import info, warn


# ── Simple intent parser (no LLM - deterministic for demo) ───────────────────
_BUY_RE  = re.compile(
    r"\b(buy|purchase|get)\b.{0,40}?\$?([\d,]+(?:\.\d+)?)(.{0,40})",
    re.IGNORECASE
)
_SELL_RE = re.compile(
    r"\b(sell|liquidate|dump)\b.{0,40}?\$?([\d,]+(?:\.\d+)?)(.{0,40})",
    re.IGNORECASE
)
_WORD_RE = re.compile(r"\b[A-Za-z]{1,5}\b")
# Filler words that can sit between the amount and the ticker
_NOT_TICKERS = {
    "of", "in", "on", "the", "a", "an", "worth", "usd", "more", "some",
    "share", "shares", "stock", "buck", "bucks", "for", "into", "at", "k",
}


def _find_ticker(tail: str) -> str:
    """Return the first word after the amount that isn't filler ('' if none)."""
    for word in _WORD_RE.findall(tail):
        if word.lower() not in _NOT_TICKERS:
            return word.upper()
    return ""


_ACCOUNT_RE  = re.compile(r"\b(account|balance|equity|portfolio)\b", re.IGNORECASE)
_POSITION_RE = re.compile(r"\b(position|holding|stock|portfolio)\b", re.IGNORECASE)
_RESEARCH_RE = re.compile(r"\b(research|analyze|look up|check|what is)\b", re.IGNORECASE)


def parse_intent(message: str) -> dict:
    """
    Parse a natural language trading command into a structured intent dict.
    Returns: {"action": str, "ticker": str, "amount": float, "scope": str}
    """
    # Check if research-only scope
    scope = "research" if _RESEARCH_RE.search(message) and not _BUY_RE.search(message) else "execute"

    for action, pattern in (("BUY", _BUY_RE), ("SELL", _SELL_RE)):
        m = pattern.search(message)
        if m:
            ticker = _find_ticker(m.group(3))
            if ticker:
                amount = float(m.group(2).replace(",", ""))
                return {"action": action, "ticker": ticker, "amount": amount, "scope": scope}

    if _ACCOUNT_RE.search(message):
        return {"action": "ACCOUNT", "ticker": "", "amount": 0, "scope": scope}

    if _POSITION_RE.search(message):
        return {"action": "POSITIONS", "ticker": "", "amount": 0, "scope": scope}

    return {"action": "UNKNOWN", "ticker": "", "amount": 0, "scope": scope}


def run_agent(message: str, dry_run: bool = True) -> dict:
    """
    Full pipeline run in pure Python.

    Args:
        message:  The user's natural language command.
        dry_run:  If True, skip the live Alpaca call (Layer 5). Default: True.

    Returns a dict with the full pipeline decision log.
    """
    log = {
        "input": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layers": {}
    }

    # ── Layer 1: Input Sanitizer ───────────────────────────────────────────
    sanitize_result = sanitize_input(message)
    log["layers"]["1_input_sanitizer"] = sanitize_result
    info("agent", "layer1_complete", status=sanitize_result["status"])

    if sanitize_result["status"] == "rejected":
        log["final"] = {"status": "blocked", "blocked_by": "input_sanitizer",
                        "reasons": sanitize_result["reasons"]}
        return log

    # ── Layer 2: Intent Parsing (simulated OpenClaw reasoning) ─────────────
    intent = parse_intent(message)
    log["layers"]["2_intent_parse"] = intent
    info("agent", "layer2_complete", intent=intent)

    if intent["action"] == "UNKNOWN":
        log["final"] = {"status": "error",
                        "message": "Could not parse intent from message. Please use a clear buy/sell command."}
        return log

    # Skip L3/L4 for non-trade actions
    if intent["action"] in ("ACCOUNT", "POSITIONS"):
        log["final"] = {"status": "approved",
                        "note": "Read-only action — skipped risk/policy checks"}
        return log

    # ── Layer 3: Intelligence Layer ────────────────────────────────────────
    intelligence = IntelligenceLayer()
    intelligence_result = intelligence.check(intent, commit=False)
    log["layers"]["3_intelligence"] = intelligence_result
    info("agent", "layer3_complete", status=intelligence_result["status"])

    if intelligence_result["status"] == "rejected":
        log["final"] = {"status": "blocked", "blocked_by": "intelligence_layer",
                        "reasons": intelligence_result["reasons"]}
        return log

    # ── Layer 4: Policy Engine (ArmorClaw mirror) ──────────────────────────
    policy_violations = validate_against_policy(
        intent["action"], intent["ticker"], intent["amount"]
    )
    log["layers"]["4_policy_engine"] = {
        "status": "rejected" if policy_violations else "approved",
        "reasons": policy_violations
    }
    info("agent", "layer4_complete", violations=len(policy_violations))

    if policy_violations:
        log["final"] = {"status": "blocked", "blocked_by": "armorclaw_policy",
                        "reasons": policy_violations}
        return log

    # Every gate passed — only now does the trade count toward exposure
    intelligence.commit(intent)

    # ── Layer 5: Alpaca Execution ──────────────────────────────────────────
    if dry_run:
        log["layers"]["5_alpaca"] = {"status": "skipped", "note": "dry_run=True"}
        log["final"] = {"status": "approved",
                        "note": "All layers passed. Set dry_run=False to execute live paper trade."}
    else:
        # Call Alpaca in-process: the trade already passed Layer 3, and going
        # through alpaca_actions.trade() would run (and commit) the gate twice.
        from alpaca_actions import API_KEY, API_SECRET, submit_order
        if not API_KEY or not API_SECRET:
            log["layers"]["5_alpaca"] = {"status": "error",
                                          "output": "Alpaca API keys not found in environment."}
            log["final"] = {"status": "error"}
            return log
        try:
            order = submit_order(intent["action"], intent["ticker"], intent["amount"])
            log["layers"]["5_alpaca"] = {"status": "executed", "output": order}
            log["final"] = {"status": "executed"}
        except Exception as exc:
            log["layers"]["5_alpaca"] = {"status": "error", "output": str(exc)}
            log["final"] = {"status": "error"}

    return log
