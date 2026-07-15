"""Tool execution audit trail.

Logs every tool execution with session, tool name, arguments,
result summary, and timestamp for compliance and debugging.
"""

import json
import time
from pathlib import Path

from loguru import logger

# Audit log file path
AUDIT_LOG_PATH: str | None = None


def set_audit_path(path: str) -> None:
    """Set the audit log file path."""
    global AUDIT_LOG_PATH
    AUDIT_LOG_PATH = path
    # Ensure the directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def log_tool_execution(
    session_key: str,
    tool_name: str,
    arguments: dict,
    result_summary: str,
    is_error: bool = False,
    duration_ms: float = 0.0,
) -> None:
    """Record a tool execution to the audit trail."""
    entry = {
        "timestamp": time.time(),
        "session": session_key,
        "tool": tool_name,
        "arguments": arguments,
        "result_summary": result_summary[:500],  # Truncate
        "is_error": is_error,
        "duration_ms": round(duration_ms, 2),
    }

    # Always log to structured logger
    logger.info(
        "AUDIT | session={} tool={} error={} duration={:.0f}ms",
        session_key,
        tool_name,
        is_error,
        duration_ms,
    )

    # Write to audit file if configured
    if AUDIT_LOG_PATH:
        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write audit log: {}", e)
