"""
input_sanitizer.py — SentinelShield v2
=======================================
Layer 1: Sits BEFORE the OpenClaw agent.

Responsibilities:
  - Detect prompt injection / jailbreak phrases in user input
  - Sanitize tool output before it re-enters the agent context (prevents P8 data exfiltration)
  - Log all flagged content to audit_log.jsonl

Returns a dict: {"status": "ok"} or {"status": "rejected", "reasons": [...]}
"""

import re
import json
import os
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG = os.path.join(BASE_DIR, "audit_log.jsonl")

# ── Injection Patterns ────────────────────────────────────────────────────────
INJECTION_PATTERNS = [
    r"\bignore\b",
    r"\boverride\b",
    r"\bbypass\b",
    r"\bforget\s+rules?\b",
    r"\bdisregard\b",
    r"\bjailbreak\b",
    r"\bunlock\b",
    r"\bno\s+limits?\b",
    r"\bskip\s+(policy|rules?|limits?)\b",
    r"\bact\s+as\s+if\b",
    r"\bpretend\b",
    r"\bsupersede\b",
    r"\bdan\b",                   # "Do Anything Now" jailbreak (input is lowercased)
    r"\bsystem\s+prompt\b",
    r"\byou\s+are\s+now\b",
]

# ── Sensitive fields to redact in tool outputs (P8: data exfiltration) ────────
SENSITIVE_FIELDS = [
    "account_number", "account_id", "id",
    "equity", "buying_power", "cash", "portfolio_value",
    "pattern_day_trader", "crypto_tier",
]

# ── Max input length ──────────────────────────────────────────────────────────
MAX_INPUT_LENGTH = 500


def _write_audit(event: dict):
    """Append a single event dict as a JSON line to audit_log.jsonl."""
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def sanitize_input(user_input: str) -> dict:
    """
    Scan raw user text for injection attempts.
    Returns {"status": "ok"} or {"status": "rejected", "reasons": [...]}.
    """
    reasons = []

    # Length guard
    if len(user_input) > MAX_INPUT_LENGTH:
        reasons.append(f"Input too long ({len(user_input)} chars > {MAX_INPUT_LENGTH} limit)")

    # Injection pattern scan
    lower = user_input.lower()
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            reasons.append(f"Prompt injection detected: '{match.group()}'")
            break  # one match is enough to flag

    if reasons:
        _write_audit({
            "layer": "input_sanitizer",
            "event": "injection_blocked",
            "input_preview": user_input[:120],
            "reasons": reasons,
        })
        return {"status": "rejected", "reasons": reasons}

    return {"status": "ok"}


def sanitize_tool_output(tool_result: dict) -> dict:
    """
    Redact sensitive financial fields from tool responses before they
    re-enter the agent's reasoning context.  (Threat P8)
    """
    redacted = {}
    for k, v in tool_result.items():
        if k in SENSITIVE_FIELDS:
            redacted[k] = "[REDACTED]"
        else:
            redacted[k] = v
    if redacted != tool_result:
        _write_audit({
            "layer": "input_sanitizer",
            "event": "output_redacted",
            "fields_redacted": [k for k in tool_result if k in SENSITIVE_FIELDS],
        })
    return redacted


# ── CLI test harness ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Buy $500 of AAPL"
    result = sanitize_input(text)
    print(json.dumps(result, indent=2))
