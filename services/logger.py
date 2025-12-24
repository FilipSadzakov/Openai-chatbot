# services/logger.py

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict


def log_event(event: Dict[str, Any]) -> None:
    """
    Production-safe JSON log to stdout (Render captures stdout).
    """
    payload = dict(event)
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())

    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        # Never crash the request because logging failed
        pass
