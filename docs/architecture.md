# SentinelShield Architecture v2

SentinelShield is a **real-time financial security and enforcement layer** for autonomous AI trading agents, built for OSSome Hacks 3.0.

## System Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER / ENVIRONMENT                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Raw Input
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LAYER 1: INPUT SANITIZER  (input_sanitizer.py)           │
│  • Prompt injection scan (14 regex patterns: ignore, bypass, DAN…)  │
│  • Input length guard (>500 chars rejected)                          │
│  • Output sanitization — redacts sensitive fields before re-entry   │
│  • All flags written to audit_log.jsonl                              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Clean Input
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LAYER 2: OPENCLAW AGENT  (Gemini Pro)                    │
│  • Parses natural language → structured intent                       │
│  • Plans tool execution (alpaca_buy, alpaca_sell…)                  │
│  • Multi-step reasoning                                              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Planned Intent
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LAYER 3: INTELLIGENCE LAYER  (intelligence.py)           │
│                                                                      │
│  ┌─────────────────────┐  ┌──────────────────────────────────────┐  │
│  │   Risk Engine       │  │   Behavior Detector                  │  │
│  │  • Per-asset cap    │  │  • Scope escalation check (P3)       │  │
│  │    ($5,000 max)     │  │  • Market hours enforcement (P6)     │  │
│  │  • Daily cap        │  │  • Bot/replay detection (P5)         │  │
│  │    ($10,000 max)    │  │  • Trade spike detection             │  │
│  │  • Stateful JSON    │  │  • Behavior log (24h sliding window) │  │
│  └──────────┬──────────┘  └───────────────────┬──────────────────┘  │
│             └──────────────────┬──────────────┘                     │
│                                ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  Decision Engine                             │    │
│  │  • Aggregates all check results                             │    │
│  │  • Writes structured Decision Record → audit_log.jsonl      │    │
│  │  • Returns: {status, reasons, decision_id}                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Approved Actions Only
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LAYER 4: ARMORCLAW PLUGIN  (existing — unchanged)        │
│  • Reads armoriq.policy.json                                         │
│  • Per-trade static checks (size $2k max, ticker allowlist)         │
│  • Defense-in-depth second wall — independent of Layer 3            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Policy-Validated Actions Only
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LAYER 5: ALPACA EXECUTION  (alpaca_actions.py)           │
│  • Paper trading via REST API                                        │
│  • Market orders, positions, account info                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│            AUDIT API  (app/main.py — FastAPI on :8000)              │
│  • GET  /health                   — liveness                        │
│  • GET  /policy                   — live ArmorClaw policy           │
│  • POST /sanitize                 — Layer 1 test endpoint           │
│  • POST /intelligence/check       — Layer 3 test endpoint           │
│  • GET  /intelligence/status      — live exposure state             │
│  • GET  /audit/log                — Decision Records stream         │
│  • GET  /logs                     — sentinel.log structured stream  │
└─────────────────────────────────────────────────────────────────────┘
```

## Security Guarantees

- **Intent Must Be Enforced, Not Inferred**: No layer relies on the LLM to self-police.
- **Fail-Closed Architecture**: Any layer failure blocks the action.
- **Independent Layers**: Input Sanitizer, Intelligence Layer, and ArmorClaw are fully decoupled — an attacker must defeat all three independently.
- **Full Audit Trail**: Every decision (approve or reject) writes a Decision Record with input hash, checks run, reasoning, and timestamp.

## Threat Coverage

| ID | Threat | Layer That Handles It |
|---|---|---|
| P1 | Prompt injection / jailbreak | Layer 1: Input Sanitizer |
| P2 | Cumulative / stateful exposure | Layer 3: Risk Engine |
| P3 | Scope escalation (research → execute) | Layer 3: Behavior Detector |
| P4 | Tool abuse (bash, filesystem) | Layer 4: ArmorClaw |
| P5 | Bot / replay attacks | Layer 3: Behavior Detector |
| P6 | Market hours violation | Layer 3: Behavior Detector |
| P7 | Silent failure / no audit trail | Layer 3: Decision Engine + audit_log.jsonl |
| P8 | Data exfiltration via tool output | Layer 1: Output Sanitizer |
