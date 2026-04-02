"""
app/logger.py — SentinelShield v2
==================================
Centralised structured logger.  All layers write through here so that
sentinel.log is always consistent JSON-lines for the /logs audit endpoint.
"""

import json
import os
import logging
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "sentinel.log")

logging.basicConfig(level=logging.INFO)
_console = logging.getLogger("sentinel")


def log(level: str, layer: str, event: str, **kwargs):
    """Write a structured JSON log line to sentinel.log and stdout."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "layer": layer,
        "event": event,
        **kwargs,
    }
    line = json.dumps(record)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    _console.info(line)


def info(layer: str, event: str, **kwargs):
    log("INFO", layer, event, **kwargs)


def warn(layer: str, event: str, **kwargs):
    log("WARN", layer, event, **kwargs)


def error(layer: str, event: str, **kwargs):
    log("ERROR", layer, event, **kwargs)
