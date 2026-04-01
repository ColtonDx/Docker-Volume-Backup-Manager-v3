"""Syslog integration – dynamically attach/detach a SysLogHandler to the root logger."""

import logging
import logging.handlers
import socket
from typing import Any

logger = logging.getLogger(__name__)

# Identifier so we can find and replace our handler later
_HANDLER_NAME = "dvbm_syslog"

# Map human-readable facility names → SysLogHandler constants
_FACILITY_MAP: dict[str, int] = {
    "local0": logging.handlers.SysLogHandler.LOG_LOCAL0,
    "local1": logging.handlers.SysLogHandler.LOG_LOCAL1,
    "local2": logging.handlers.SysLogHandler.LOG_LOCAL2,
    "local3": logging.handlers.SysLogHandler.LOG_LOCAL3,
    "local4": logging.handlers.SysLogHandler.LOG_LOCAL4,
    "local5": logging.handlers.SysLogHandler.LOG_LOCAL5,
    "local6": logging.handlers.SysLogHandler.LOG_LOCAL6,
    "local7": logging.handlers.SysLogHandler.LOG_LOCAL7,
    "daemon": logging.handlers.SysLogHandler.LOG_DAEMON,
    "user": logging.handlers.SysLogHandler.LOG_USER,
}


def _remove_existing_handler() -> None:
    """Remove previously attached syslog handler from root logger."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "name", None) == _HANDLER_NAME:
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass


def configure_syslog(settings: dict[str, Any]) -> None:
    """Attach or detach a SysLogHandler based on the provided settings dict.

    Expected keys (all optional – missing keys fall back to defaults):
        syslog_enabled   – bool (default False)
        syslog_host      – str  (e.g. "192.168.1.100")
        syslog_port      – int  (default 514)
        syslog_protocol  – "udp" | "tcp" (default "udp")
        syslog_facility  – facility name string (default "local0")
    """
    # Always remove existing handler first so settings changes take effect
    _remove_existing_handler()

    enabled = settings.get("syslog_enabled", False)
    host = (settings.get("syslog_host") or "").strip()

    if not enabled or not host:
        if enabled and not host:
            logger.warning("Syslog enabled but no host configured – skipping")
        return

    port = int(settings.get("syslog_port", 514) or 514)
    protocol = (settings.get("syslog_protocol") or "udp").lower()
    facility_name = (settings.get("syslog_facility") or "local0").lower()
    facility = _FACILITY_MAP.get(facility_name, logging.handlers.SysLogHandler.LOG_LOCAL0)

    socktype = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM

    try:
        handler = logging.handlers.SysLogHandler(
            address=(host, port),
            facility=facility,
            socktype=socktype,
        )
        handler.name = _HANDLER_NAME  # type: ignore[attr-defined]

        # RFC 5424-ish format with app name tag
        formatter = logging.Formatter(
            fmt="dvbm: [%(levelname)s] %(name)s – %(message)s",
        )
        handler.setFormatter(formatter)

        logging.getLogger().addHandler(handler)
        logger.info(
            "Syslog handler attached → %s:%d (%s, facility=%s)",
            host, port, protocol.upper(), facility_name,
        )
    except Exception as exc:
        logger.error("Failed to configure syslog handler: %s", exc)
