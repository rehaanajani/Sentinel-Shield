"""
app/main.py — SentinelShield v2
=================================
FastAPI Audit & Demo API.

Endpoints:
  GET  /health                 — liveness check
  GET  /policy                 — view active ArmorClaw policy
  POST /sanitize               — run Input Sanitizer on raw text (Layer 1)
  POST /intelligence/check     — run Intelligence Layer on a parsed intent (Layer 3)
  GET  /intelligence/status    — live exposure + limits state
  GET  /audit/log              — last N decision records from audit_log.jsonl
  GET  /logs                   — last N entries from sentinel.log
"""

import json
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Resolve project root (one level up from app/) ────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from input_sanitizer import sanitize_input          # noqa: E402
from intelligence import IntelligenceLayer           # noqa: E402
from app.policy_engine import load_policy            # noqa: E402

AUDIT_LOG  = os.path.join(ROOT, "audit_log.jsonl")
SENTINEL_LOG = os.path.join(ROOT, "sentinel.log")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SentinelShield v2 — Audit API",
    description=(
        "Real-time financial security and enforcement layer for autonomous trading agents. "
        "Exposes all internal layers for hackathon demo and audit transparency."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request Models ────────────────────────────────────────────────────────────

class SanitizeRequest(BaseModel):
    input: str

class IntentRequest(BaseModel):
    action: str         # BUY | SELL | ACCOUNT | POSITIONS
    ticker: str = ""
    amount: float = 0.0
    scope:  str = "execute"  # "execute" | "research"

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "system": "SentinelShield v2"}


@app.get("/policy", tags=["audit"])
def get_policy():
    """Returns the live ArmorClaw policy being enforced."""
    return load_policy()


@app.post("/sanitize", tags=["layer-1: input sanitizer"])
def sanitize_endpoint(req: SanitizeRequest):
    """
    Layer 1 — Runs the Input Sanitizer on raw user text.
    Use this BEFORE passing input to the OpenClaw agent.
    """
    result = sanitize_input(req.input)
    return result


@app.post("/intelligence/check", tags=["layer-3: intelligence"])
def intelligence_check(req: IntentRequest):
    """
    Layer 3 — Runs the full Intelligence Layer on a parsed intent.
    Checks: Risk Engine (exposure) + Behavior Detector (bots, scope, market hours, spikes).
    Writes a Decision Record to audit_log.jsonl regardless of outcome.
    """
    intent = {
        "action": req.action,
        "ticker": req.ticker,
        "amount": req.amount,
        "scope":  req.scope,
    }
    layer  = IntelligenceLayer()
    result = layer.check(intent)
    return result


@app.get("/intelligence/status", tags=["layer-3: intelligence"])
def intelligence_status():
    """
    Returns the current live exposure state tracked by the Risk Engine.
    Use this during the demo to show stateful cumulative tracking.
    """
    layer = IntelligenceLayer()
    return layer.state()


@app.get("/audit/log", tags=["audit"])
def audit_log(limit: int = 20):
    """
    Returns the last `limit` Decision Records from audit_log.jsonl.
    Each record shows: layer, decision_id, status, intent, reasons, timestamp.
    """
    if not os.path.exists(AUDIT_LOG):
        return {"records": [], "total": 0}

    with open(AUDIT_LOG, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    return {"records": list(reversed(records)), "total": len(lines)}


@app.get("/logs", tags=["audit"])
def get_logs(limit: int = 50):
    """
    Returns the last `limit` lines from sentinel.log as structured JSON.
    """
    if not os.path.exists(SENTINEL_LOG):
        return {"logs": [], "total": 0}

    with open(SENTINEL_LOG, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    parsed = []
    for line in lines[-limit:]:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append({"raw": line})

    return {"logs": list(reversed(parsed)), "total": len(lines)}
