import os
import sys
import json
import requests

# ── Keys are read from the environment (OpenClaw passes them) ──
API_KEY    = os.environ.get("ALPACA_API_KEY_ID")
API_SECRET = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL   = "https://paper-api.alpaca.markets/v2"

HEADERS = {
    "APCA-API-KEY-ID":     API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
    "Content-Type":        "application/json"
}

# ── Determine project root (handle both direct run and module import) ─────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_intelligence_gate(action: str, ticker: str, amount: float) -> bool:
    """
    Run Intelligence Layer check BEFORE hitting Alpaca.
    Returns True if approved, False if blocked.
    Prints the rejection reasons to stdout so OpenClaw / ArmorClaw can log them.
    """
    try:
        sys.path.insert(0, _THIS_DIR)
        from intelligence import IntelligenceLayer  # noqa: E402

        layer  = IntelligenceLayer()
        result = layer.check({"action": action, "ticker": ticker, "amount": amount, "scope": "execute"})

        if result["status"] == "rejected":
            print(json.dumps({
                "status":  "rejected",
                "layer":   "intelligence",
                "reasons": result["reasons"],
                "decision_id": result.get("decision_id"),
            }, indent=2))
            return False
        return True

    except Exception as exc:
        # Fail-closed: if intelligence layer errors, block the trade
        print(json.dumps({
            "status":  "rejected",
            "layer":   "intelligence",
            "reasons": [f"Intelligence Layer error (fail-closed): {exc}"],
        }, indent=2))
        return False


# ── Alpaca API calls ───────────────────────────────────────────────────────────

def get_account():
    res = requests.get(f"{BASE_URL}/account", headers=HEADERS)
    print(json.dumps(res.json(), indent=2))


def get_positions():
    res = requests.get(f"{BASE_URL}/positions", headers=HEADERS)
    print(json.dumps(res.json(), indent=2))


def trade(side: str, symbol: str, notional: float):
    """Submit a market order by notional (USD amount) — after Intelligence check."""
    if not _run_intelligence_gate(side, symbol, notional):
        sys.exit(1)  # ArmorClaw sees non-zero exit and treats as blocked

    data = {
        "symbol":       symbol.upper(),
        "notional":     float(notional),
        "side":         side.lower(),
        "type":         "market",
        "time_in_force": "day",
    }
    res = requests.post(f"{BASE_URL}/orders", headers=HEADERS, json=data)
    print(json.dumps(res.json(), indent=2))


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        print("Error: Alpaca API keys not found in environment.")
        sys.exit(1)

    cmd = sys.argv[1].upper() if len(sys.argv) > 1 else ""

    try:
        if cmd == "ACCOUNT":
            get_account()
        elif cmd == "POSITIONS":
            get_positions()
        elif cmd in ["BUY", "SELL"]:
            symbol  = sys.argv[2]
            usd_amt = float(sys.argv[3])
            trade(cmd, symbol, usd_amt)
        else:
            print("Usage: python alpaca_actions.py [BUY|SELL|ACCOUNT|POSITIONS] [ticker] [usd_amount]")
    except Exception as e:
        print(f"Error executing Alpaca order: {e}")
        sys.exit(1)
