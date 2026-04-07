"""Notification service.

Sends notifications via email, Slack, Discord, Gotify, ntfy, or generic webhook
when backup events occur.
"""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatches notifications to configured channels."""

    def notify_event(self, event: str, job_name: str, message: str) -> None:
        """Send notifications to all channels subscribed to this event type.

        event: "success" | "failure" | "warning"
        """
        from app.database import SessionLocal
        from app.models import NotificationChannel

        db = SessionLocal()
        try:
            channels = (
                db.query(NotificationChannel)
                .filter(NotificationChannel.enabled == True)
                .all()
            )
            for ch in channels:
                events = json.loads(ch.events_json or "[]")
                if event not in events:
                    continue

                config = json.loads(ch.config_json or "{}")
                try:
                    self._send(ch.type, config, job_name, event, message)
                    ch.last_triggered_at = datetime.now(timezone.utc)
                except Exception as exc:
                    logger.error("Failed to send %s notification '%s': %s", ch.type, ch.name, exc)

            db.commit()
        except Exception as exc:
            logger.exception("Notification dispatch failed: %s", exc)
        finally:
            db.close()

    def send_test(self, channel_type: str, config: dict[str, Any]) -> tuple[bool, str]:
        """Send a test notification. Returns (success, message)."""
        from app.config import settings
        try:
            self._send(channel_type, config, "Test Job", "info", f"This is a test notification from {settings.APP_NAME}")
            return True, "Test notification sent successfully"
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Dispatchers
    # ------------------------------------------------------------------

    def _send(
        self, channel_type: str, config: dict[str, Any],
        job_name: str, event: str, message: str,
    ) -> None:
        if channel_type == "email":
            self._send_email(config, job_name, event, message)
        elif channel_type == "slack":
            self._send_slack(config, job_name, event, message)
        elif channel_type == "discord":
            self._send_discord(config, job_name, event, message)
        elif channel_type == "gotify":
            self._send_gotify(config, job_name, event, message)
        elif channel_type == "ntfy":
            self._send_ntfy(config, job_name, event, message)
        elif channel_type == "webhook":
            self._send_webhook(config, job_name, event, message)
        else:
            logger.warning("Unknown notification type: %s", channel_type)

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    @staticmethod
    def _send_email(config: dict, job_name: str, event: str, message: str) -> None:
        host = config.get("smtp_host", "localhost")
        port = config.get("smtp_port", 587)
        username = config.get("smtp_username", "")
        password = config.get("smtp_password", "")
        from_addr = config.get("from_address", f"dvbm@{host}")
        to_addrs = config.get("to_addresses", [])
        use_tls = config.get("use_tls", True)

        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        from app.config import settings
        subject = f"[{settings.APP_NAME}] {event.upper()}: {job_name}"
        body = f"Job: {job_name}\nEvent: {event}\n\n{message}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        with smtplib.SMTP(host, port) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(msg)

        logger.info("Email sent to %s", ", ".join(to_addrs))

    # ------------------------------------------------------------------
    # Slack
    # ------------------------------------------------------------------

    @staticmethod
    def _send_slack(config: dict, job_name: str, event: str, message: str) -> None:
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook URL not configured")

        emoji = {"success": ":white_check_mark:", "failure": ":x:", "warning": ":warning:"}.get(event, ":information_source:")

        payload = {
            "text": f"{emoji} *Backup Buddy – {event.upper()}*\n*Job:* {job_name}\n{message}",
        }

        channel = config.get("channel")
        if channel:
            payload["channel"] = channel

        resp = httpx.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack notification sent")

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------

    @staticmethod
    def _send_discord(config: dict, job_name: str, event: str, message: str) -> None:
        webhook_url = config.get("webhook_url", "").strip()
        if not webhook_url:
            raise ValueError("Discord webhook URL not configured")

        color_map = {"success": 0x22C55E, "failure": 0xEF4444, "warning": 0xF59E0B}
        color = color_map.get(event, 0x3B82F6)

        # Discord timestamps must be ISO 8601 with explicit UTC offset.
        # Truncate microseconds — Discord rejects timestamps with sub-second precision.
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        # Truncate fields to Discord's documented limits to avoid 400 errors:
        #   embed title: 256 chars, description: 4096 chars, field value: 1024 chars
        #   username: 80 chars
        payload = {
            "embeds": [
                {
                    "title": f"Backup Buddy \u2013 {event.upper()}"[:256],
                    "description": message[:4096],
                    "color": color,
                    "fields": [
                        {"name": "Job", "value": job_name[:1024], "inline": True},
                        {"name": "Event", "value": event[:1024], "inline": True},
                    ],
                    "timestamp": ts,
                }
            ],
            "username": config.get("username", "Backup Buddy")[:80],
        }

        avatar_url = config.get("avatar_url", "").strip()
        if avatar_url:
            payload["avatar_url"] = avatar_url

        resp = httpx.post(webhook_url, json=payload, timeout=10)

        # Discord returns 204 No Content on success; any non-2xx is a failure.
        if not resp.is_success:
            # Surface the response body so the real reason is visible in logs.
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise ValueError(f"Discord webhook returned {resp.status_code}: {detail}")

        logger.info("Discord notification sent")

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    @staticmethod
    def _send_webhook(config: dict, job_name: str, event: str, message: str) -> None:
        url = config.get("url", "")
        if not url:
            raise ValueError("Webhook URL not configured")

        payload = {
            "source": "dvbm",
            "event": event,
            "job_name": job_name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        headers = config.get("headers", {})
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                headers = {}

        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info("Webhook notification sent to %s", url)

    # ------------------------------------------------------------------
    # Gotify
    # ------------------------------------------------------------------

    @staticmethod
    def _send_gotify(config: dict, job_name: str, event: str, message: str) -> None:
        server_url = config.get("server_url", "").rstrip("/")
        app_token = config.get("app_token", "")
        if not server_url or not app_token:
            raise ValueError("Gotify server URL and application token are required")

        priority_map = {"failure": 8, "warning": 5, "success": 2, "info": 1}
        priority = config.get("priority", priority_map.get(event, 4))

        payload = {
            "title": f"Backup Buddy \u2013 {event.upper()}: {job_name}",
            "message": message,
            "priority": int(priority),
            "extras": {
                "client::display": {"contentType": "text/plain"},
            },
        }

        resp = httpx.post(
            f"{server_url}/message",
            params={"token": app_token},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Gotify notification sent to %s", server_url)

    # ------------------------------------------------------------------
    # ntfy
    # ------------------------------------------------------------------

    @staticmethod
    def _send_ntfy(config: dict, job_name: str, event: str, message: str) -> None:
        server_url = config.get("server_url", "https://ntfy.sh").rstrip("/")
        topic = config.get("topic", "")
        if not topic:
            raise ValueError("ntfy topic is required")

        # Map events to ntfy priority names (1-5) and tags
        priority_map = {"failure": "5", "warning": "4", "success": "3", "info": "3"}
        tag_map = {"failure": "rotating_light,x", "warning": "warning", "success": "white_check_mark", "info": "information_source"}

        headers: dict[str, str] = {
            "Title": f"Backup Buddy \u2013 {event.upper()}: {job_name}",
            "Priority": config.get("priority", priority_map.get(event, "3")),
            "Tags": tag_map.get(event, "information_source"),
        }

        # Optional authentication
        access_token = config.get("access_token", "")
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        resp = httpx.post(
            f"{server_url}/{topic}",
            content=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("ntfy notification sent to %s/%s", server_url, topic)


notification_service = NotificationService()
