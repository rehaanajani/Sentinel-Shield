"""
sentinel_run.py — SentinelShield v2
=====================================
THE UNIFIED LAUNCHER — Run this instead of calling openclaw directly.

This script chains all 5 layers end-to-end:

  Layer 1: Input Sanitizer   → blocks injection before agent sees anything
  Layer 2: OpenClaw Agent    → Gemini/OpenRouter reasoning
  Layer 3: Intelligence Gate → inside alpaca_actions.py (auto-called)
  Layer 4: ArmorClaw Plugin  → policy enforcement via OpenClaw plugin
  Layer 5: Alpaca Execution  → live paper trade

Usage:
  python sentinel_run.py "Buy $500 of AAPL"
  python sentinel_run.py   (interactive mode)
"""

import sys
import os
import json
import subprocess
from datetime import datetime, timezone

# ── Load .env into environment ────────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip("'\"")
                os.environ.setdefault(key.strip(), val)

_load_env()

# ── Import our layers ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from input_sanitizer import sanitize_input        # Layer 1
from app.logger import info, warn                  # structured logging

AUDIT_LOG = os.path.join(BASE_DIR, "audit_log.jsonl")
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║          SentinelShield v2  🛡️  Secure Agent Runner         ║
║    4 independent enforcement layers · OSSome Hacks 3.0      ║
╚══════════════════════════════════════════════════════════════╝
"""


def _append_audit(event: dict):
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def run_layer1_sanitizer(user_input: str) -> bool:
    """Layer 1 — Input Sanitizer. Returns True if clean."""
    print("\n[Layer 1] Input Sanitizer scanning...", flush=True)
    result = sanitize_input(user_input)
    if result["status"] == "rejected":
        print(json.dumps({
            "layer":   "1_input_sanitizer",
            "status":  "BLOCKED",
            "reasons": result["reasons"],
        }, indent=2))
        warn("sentinel_run", "input_blocked", reasons=result["reasons"])
        return False
    print("[Layer 1] ✅ Clean — passing to OpenClaw agent", flush=True)
    info("sentinel_run", "input_clean", preview=user_input[:80])
    return True


def run_layer2_openclaw(user_input: str) -> int:
    """
    Layer 2 — OpenClaw Agent.
    Calls `openclaw agent --message "<input>"`.
    Layers 3 (intelligence) and 4 (ArmorClaw) fire automatically inside this call.
    Returns process exit code (0 = success, non-zero = blocked/failed).
    """
    print("\n[Layer 2] OpenClaw Agent reasoning...", flush=True)
    print("[Layer 3] Intelligence Layer will fire inside alpaca_actions.py", flush=True)
    print("[Layer 4] ArmorClaw will enforce policy before execution\n", flush=True)

    env = os.environ.copy()

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", user_input],
            env=env,
            cwd=BASE_DIR,
        )
        return result.returncode
    except FileNotFoundError:
        print("\n⚠️  OpenClaw not found in PATH.")
        print("Run the setup first:\n  powershell .\\setup_openclaw.ps1\n")
        print("OR test individual layers directly:")
        print("  python intelligence.py BUY AAPL 500")
        print("  python input_sanitizer.py 'your text here'")
        print("  uvicorn app.main:app --reload  (then hit http://localhost:8000/docs)")
        return 127


def main():
    print(BANNER)

    # Get user message (CLI arg or interactive)
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        print(f"Command: {user_input}\n")
    else:
        print("Interactive mode — type a trading command, or 'exit' to quit.")
        try:
            user_input = input("\nSentinelShield> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExited.")
            return

    if not user_input or user_input.lower() == "exit":
        print("No command given. Exited.")
        return

    # ── Layer 1: Input Sanitizer ───────────────────────────────────────────
    if not run_layer1_sanitizer(user_input):
        sys.exit(1)

    # ── Layer 2–4: OpenClaw → Intelligence → ArmorClaw → Alpaca ──────────
    exit_code = run_layer2_openclaw(user_input)

    if exit_code == 0:
        print("\n✅ Pipeline complete — trade executed via Alpaca.")
        _append_audit({"event": "pipeline_success", "command": user_input})
    elif exit_code == 127:
        print("\n⚠️  OpenClaw not installed. See setup instructions above.")
    else:
        print(f"\n❌ Trade blocked by Intelligence Layer or ArmorClaw (exit: {exit_code}).")
        _append_audit({"event": "pipeline_blocked", "command": user_input, "exit_code": exit_code})


if __name__ == "__main__":
    main()
