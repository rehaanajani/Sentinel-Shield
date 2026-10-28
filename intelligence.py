"""
intelligence.py — SentinelShield v2
=====================================
Layer 3: Sits AFTER OpenClaw agent reasoning, BEFORE ArmorClaw.

Three sub-engines:
  A) RiskEngine         — stateful exposure tracking (per-asset + daily cap)
  B) BehaviorDetector   — bot/replay detection, spike detection, scope escalation
  C) DecisionEngine     — aggregates all results → Decision Record → audit_log.jsonl

Usage:
  from intelligence import IntelligenceLayer
  result = IntelligenceLayer().check(intent)
  # intent = {"action": "BUY", "ticker": "AAPL", "amount": 500, "scope": "execute"}
"""

import json
import os
import time
import hashlib
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATE_DIR   = os.path.join(BASE_DIR, "state")
EXPOSURE_F  = os.path.join(STATE_DIR, "exposure.json")
BEHAVIOR_F  = os.path.join(STATE_DIR, "behavior_log.json")
AUDIT_LOG   = os.path.join(BASE_DIR, "audit_log.jsonl")

os.makedirs(STATE_DIR, exist_ok=True)

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_PER_TICKER_USD  = 5_000   # max cumulative exposure per single asset
MAX_DAILY_USD       = 10_000  # max total daily exposure across all assets
RATE_LIMIT_WINDOW_S = 60      # seconds window for bot detection
RATE_LIMIT_MAX      = 3       # max identical commands in that window
SPIKE_MULTIPLIER    = 3.0     # flag if trade > 3x recent average
SPIKE_LOOKBACK      = 5       # how many past trades to avg for spike check

# ── Market hours (NYSE regular session, US/Eastern, DST-aware) ─────────────
MARKET_TZ    = ZoneInfo("America/New_York")
MARKET_OPEN  = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)


def market_is_open(now: datetime | None = None) -> bool:
    """True during the regular Mon–Fri 9:30–16:00 ET session (holidays not handled)."""
    et = (now or datetime.now(timezone.utc)).astimezone(MARKET_TZ)
    return et.weekday() < 5 and MARKET_OPEN <= et.time() < MARKET_CLOSE


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: str, default) -> dict | list:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _append_audit(record: dict):
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# A) Risk Engine
# ─────────────────────────────────────────────────────────────────────────────

class RiskEngine:
    """
    Tracks stateful exposure — per-asset and daily totals — across sessions.
    State is persisted to state/exposure.json.
    """

    def __init__(self):
        raw = _load_json(EXPOSURE_F, {})
        today = datetime.now(timezone.utc).date().isoformat()

        # Reset daily total if it's a new day
        if raw.get("date") != today:
            raw = {"date": today, "daily_total": 0.0, "per_ticker": {}}

        self.date        = today
        self.daily_total = float(raw.get("daily_total", 0.0))
        self.per_ticker  = {k: float(v) for k, v in raw.get("per_ticker", {}).items()}

    def _persist(self):
        _save_json(EXPOSURE_F, {
            "date":        self.date,
            "daily_total": self.daily_total,
            "per_ticker":  self.per_ticker,
        })

    def check(self, action: str, ticker: str, amount: float) -> list[str]:
        """Return a list of violation reasons (empty = OK)."""
        if action.upper() != "BUY":
            return []   # SELL doesn't increase exposure

        reasons = []
        current_ticker = self.per_ticker.get(ticker, 0.0)

        if current_ticker + amount > MAX_PER_TICKER_USD:
            reasons.append(
                f"Exposure limit exceeded for {ticker}: "
                f"current ${current_ticker:,.0f} + new ${amount:,.0f} > cap ${MAX_PER_TICKER_USD:,.0f}"
            )

        if self.daily_total + amount > MAX_DAILY_USD:
            reasons.append(
                f"Daily exposure cap exceeded: "
                f"today ${self.daily_total:,.0f} + new ${amount:,.0f} > cap ${MAX_DAILY_USD:,.0f}"
            )

        return reasons

    def commit(self, action: str, ticker: str, amount: float):
        """Persist exposure update after a trade is fully approved."""
        if action.upper() == "BUY":
            self.per_ticker[ticker] = self.per_ticker.get(ticker, 0.0) + amount
            self.daily_total += amount
            self._persist()

    def state_snapshot(self) -> dict:
        return {
            "date":        self.date,
            "daily_total": self.daily_total,
            "per_ticker":  self.per_ticker,
            "limits": {
                "max_per_ticker_usd": MAX_PER_TICKER_USD,
                "max_daily_usd":      MAX_DAILY_USD,
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# B) Behavior Detector
# ─────────────────────────────────────────────────────────────────────────────

class BehaviorDetector:
    """
    Detects:
      - Bot / replay attacks (identical commands too fast)
      - Abnormal trade size spikes
      - Market-hours violations
      - Scope escalation (read-only delegation trying to execute)
    """

    def __init__(self):
        self.log: list = _load_json(BEHAVIOR_F, [])

    def _persist(self):
        # Keep only entries newer than 24 h to bound file size
        cutoff = time.time() - 86_400
        self.log = [e for e in self.log if e.get("ts", 0) >= cutoff]
        _save_json(BEHAVIOR_F, self.log)

    def _fingerprint(self, intent: dict) -> str:
        key = f"{intent.get('action','')}{intent.get('ticker','')}{intent.get('amount',0)}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def check(self, intent: dict) -> list[str]:
        reasons = []
        now     = time.time()
        action  = intent.get("action", "").upper()
        amount  = float(intent.get("amount", 0))
        scope   = intent.get("scope", "execute")  # "research" | "execute"

        # ── Scope escalation check (P3) ──────────────────────────────────────
        if scope == "research" and action in ("BUY", "SELL"):
            reasons.append(
                "Scope escalation blocked: delegation is read-only ('research') "
                "but agent attempted an execution action"
            )

        # ── Market hours check (P6) ───────────────────────────────────────────
        if action in ("BUY", "SELL") and not market_is_open():
            now_et = datetime.now(MARKET_TZ)
            reasons.append(
                "Market hours violation: trades only allowed Mon–Fri "
                "09:30–16:00 ET "
                f"(now {now_et:%a %H:%M} ET)"
            )

        # ── Rate limiting / bot detection (P5) ─────────────────────────────
        if action in ("BUY", "SELL"):
            fp     = self._fingerprint(intent)
            window = [e for e in self.log if e.get("ts", 0) >= now - RATE_LIMIT_WINDOW_S
                      and e.get("fp") == fp]
            if len(window) >= RATE_LIMIT_MAX:
                reasons.append(
                    f"Bot-like behavior: {len(window)+1} identical commands "
                    f"detected within {RATE_LIMIT_WINDOW_S}s"
                )

        # ── Trade spike detection ────────────────────────────────────────────
        if action in ("BUY", "SELL") and amount > 0:
            recent_amounts = [
                e.get("amount", 0) for e in self.log
                if e.get("action") in ("BUY", "SELL")
            ][-SPIKE_LOOKBACK:]

            if len(recent_amounts) >= 2:
                avg = sum(recent_amounts) / len(recent_amounts)
                if avg > 0 and amount > avg * SPIKE_MULTIPLIER:
                    reasons.append(
                        f"Abnormal trade spike: ${amount:,.0f} is "
                        f"{amount/avg:.1f}x the recent average (${avg:,.0f})"
                    )

        # ── Log this request regardless ──────────────────────────────────────
        self.log.append({
            "ts":     now,
            "action": action,
            "ticker": intent.get("ticker", ""),
            "amount": amount,
            "scope":  scope,
            "fp":     self._fingerprint(intent),
        })
        self._persist()
        return reasons


# ─────────────────────────────────────────────────────────────────────────────
# C) Decision Engine (orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class IntelligenceLayer:
    """
    Top-level entry point.  Call .check(intent) with:
      {
        "action":  "BUY" | "SELL" | "ACCOUNT" | "POSITIONS",
        "ticker":  "AAPL",
        "amount":  500,
        "scope":   "execute"   # optional, default "execute"
      }

    Returns:
      {"status": "approved"|"rejected", "reasons": [...], "decision_id": "..."}
    """

    def __init__(self):
        self.risk      = RiskEngine()
        self.behavior  = BehaviorDetector()

    def check(self, intent: dict, commit: bool = True) -> dict:
        """
        Run every engine on the intent and write a Decision Record.
        Pass commit=False when later layers still have to approve the trade,
        then call commit(intent) once they do.
        """
        all_reasons = []

        # Run both engines
        all_reasons += self.risk.check(
            intent.get("action", ""),
            intent.get("ticker", ""),
            float(intent.get("amount", 0)),
        )
        all_reasons += self.behavior.check(intent)

        status = "rejected" if all_reasons else "approved"

        # Build Decision Record
        decision_id = hashlib.sha256(
            (str(time.time()) + json.dumps(intent, sort_keys=True)).encode()
        ).hexdigest()[:12]

        record = {
            "layer":       "intelligence",
            "decision_id": decision_id,
            "status":      status,
            "intent":      intent,
            "reasons":     all_reasons,
            "checks_run":  ["risk_engine", "behavior_detector"],
        }
        _append_audit(record)

        # Commit exposure only when fully approved
        if status == "approved" and commit:
            self.commit(intent)

        return {
            "status":      status,
            "reasons":     all_reasons,
            "decision_id": decision_id,
        }

    def commit(self, intent: dict):
        """Record the trade's exposure. Call only after every layer approved it."""
        self.risk.commit(
            intent.get("action", ""),
            intent.get("ticker", ""),
            float(intent.get("amount", 0)),
        )

    def state(self) -> dict:
        return self.risk.state_snapshot()


# ── CLI test harness ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    # Example: python intelligence.py BUY AAPL 500
    action = sys.argv[1].upper() if len(sys.argv) > 1 else "BUY"
    ticker = sys.argv[2].upper() if len(sys.argv) > 2 else "AAPL"
    amount = float(sys.argv[3])  if len(sys.argv) > 3 else 500.0
    scope  = sys.argv[4]         if len(sys.argv) > 4 else "execute"

    layer  = IntelligenceLayer()
    result = layer.check({"action": action, "ticker": ticker, "amount": amount, "scope": scope})
    print(json.dumps(result, indent=2))
