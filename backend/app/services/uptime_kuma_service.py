"""Uptime Kuma integration service.

Creates and manages maintenance windows in Uptime Kuma so that monitors
are automatically placed into maintenance mode while a backup job runs.

Authenticates via Uptime Kuma's ``/login/access-token`` endpoint using
username + password (HTTP Basic-style credentials).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class UptimeKumaService:
    """Manages maintenance windows in Uptime Kuma via its REST API."""

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _get_settings(self) -> dict[str, Any]:
        """Load Uptime Kuma settings from the database."""
        from app.database import SessionLocal
        from app.models import Setting

        db = SessionLocal()
        try:
            keys = (
                "uptime_kuma_enabled",
                "uptime_kuma_url",
                "uptime_kuma_username",
                "uptime_kuma_password",
            )
            result: dict[str, Any] = {}
            for key in keys:
                row = db.query(Setting).get(key)
                if row and row.value is not None:
                    try:
                        result[key] = json.loads(row.value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = row.value
            return result
        finally:
            db.close()

    def _is_enabled(self, settings: dict[str, Any] | None = None) -> bool:
        s = settings or self._get_settings()
        return bool(s.get("uptime_kuma_enabled")) and bool(s.get("uptime_kuma_url"))

    def _base_url(self, url: str) -> str:
        """Normalise the base URL (strip trailing slash)."""
        return url.rstrip("/")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(
        self,
        client: httpx.Client,
        base: str,
        username: str,
        password: str,
    ) -> str:
        """Log in to Uptime Kuma and return a Bearer token.

        Uptime Kuma exposes ``POST /login/access-token`` which accepts
        ``{"username": "…", "password": "…"}`` and returns
        ``{"token": "…"}``.
        """
        resp = client.post(
            f"{base}/login/access-token",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        data = self._parse_json_response(resp)
        token = data.get("token")
        if not token:
            raise ValueError(
                "Uptime Kuma login succeeded but no token was returned. "
                f"Response: {data}"
            )
        return token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _resolve_credentials(
        self,
        url: str | None,
        username: str | None,
        password: str | None,
    ) -> tuple[str, str, str] | None:
        """Return (base_url, username, password) from explicit args or DB.

        Returns ``None`` when the integration is disabled or credentials
        are missing.
        """
        if url and username and password:
            return self._base_url(url), username, password

        settings = self._get_settings()
        if not self._is_enabled(settings):
            return None
        base = self._base_url(settings["uptime_kuma_url"])
        uname = settings.get("uptime_kuma_username", "")
        pwd = settings.get("uptime_kuma_password", "")
        if not uname or not pwd:
            return None
        return base, uname, pwd

    @staticmethod
    def _parse_json_response(resp: httpx.Response) -> Any:
        """Safely parse a JSON response, raising a clear error on failure."""
        content_type = resp.headers.get("content-type", "")
        body = resp.text
        if not body or not body.strip():
            raise ValueError(
                f"Uptime Kuma returned an empty response (HTTP {resp.status_code}). "
                "Check that the URL is correct and points to the Uptime Kuma API."
            )
        if "application/json" not in content_type and body.lstrip().startswith("<"):
            raise ValueError(
                f"Uptime Kuma returned HTML instead of JSON (HTTP {resp.status_code}). "
                "This usually means the URL is wrong or the instance requires login. "
                "Ensure the URL points directly to Uptime Kuma (e.g. http://uptime-kuma:3001)."
            )
        try:
            return resp.json()
        except Exception:
            raise ValueError(
                f"Uptime Kuma returned an unexpected response (HTTP {resp.status_code}): "
                f"{body[:200]}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_maintenance(self, monitor_id: int, job_name: str) -> int | None:
        """Create a maintenance window for the given monitor.

        Returns the Uptime Kuma maintenance ID, or *None* on failure / disabled.
        """
        creds = self._resolve_credentials(None, None, None)
        if creds is None:
            return None
        base, username, password = creds

        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=4)

        payload = {
            "title": f"Backup Buddy: {job_name}",
            "strategy": "manual",
            "active": True,
            "description": (
                f"Automated maintenance window created by Backup Buddy "
                f"for job '{job_name}'."
            ),
            "dateRange": [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                end.strftime("%Y-%m-%d %H:%M:%S"),
            ],
            "intervalDay": 1,
            "timezoneOption": "UTC",
        }

        try:
            with httpx.Client(timeout=15) as client:
                token = self._login(client, base, username, password)
                headers = self._auth_headers(token)

                # 1. Create the maintenance window
                resp = client.post(
                    f"{base}/api/maintenances", json=payload, headers=headers,
                )
                resp.raise_for_status()
                data = self._parse_json_response(resp)
                maintenance_id: int = (
                    data.get("maintenance", {}).get("id") or data.get("id")
                )
                if not maintenance_id:
                    logger.error(
                        "Uptime Kuma did not return a maintenance ID: %s", data,
                    )
                    return None

                logger.info(
                    "Created Uptime Kuma maintenance #%d for job '%s'",
                    maintenance_id,
                    job_name,
                )

                # 2. Attach the monitor to this maintenance window
                monitor_resp = client.post(
                    f"{base}/api/maintenances/{maintenance_id}/monitors",
                    json={"monitors": [monitor_id]},
                    headers=headers,
                )
                monitor_resp.raise_for_status()
                logger.info(
                    "Attached monitor %d to maintenance #%d",
                    monitor_id,
                    maintenance_id,
                )

                return maintenance_id

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Uptime Kuma API error (%s %s): %s",
                exc.response.status_code,
                exc.request.url,
                exc.response.text,
            )
        except Exception as exc:
            logger.error("Failed to create Uptime Kuma maintenance window: %s", exc)

        return None

    def end_maintenance(self, maintenance_id: int) -> None:
        """End (delete) a maintenance window by its ID."""
        creds = self._resolve_credentials(None, None, None)
        if creds is None:
            return
        base, username, password = creds

        try:
            with httpx.Client(timeout=15) as client:
                token = self._login(client, base, username, password)
                headers = self._auth_headers(token)
                resp = client.delete(
                    f"{base}/api/maintenances/{maintenance_id}", headers=headers,
                )
                resp.raise_for_status()
                logger.info("Deleted Uptime Kuma maintenance #%d", maintenance_id)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Could not delete Uptime Kuma maintenance #%d (%s): %s",
                maintenance_id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:
            logger.warning(
                "Failed to end Uptime Kuma maintenance #%d: %s",
                maintenance_id,
                exc,
            )

    def list_monitors(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch the list of monitors from Uptime Kuma."""
        creds = self._resolve_credentials(url, username, password)
        if creds is None:
            return []
        base, uname, pwd = creds

        try:
            with httpx.Client(timeout=15) as client:
                token = self._login(client, base, uname, pwd)
                headers = self._auth_headers(token)
                resp = client.get(f"{base}/api/monitors", headers=headers)
                resp.raise_for_status()
                data = self._parse_json_response(resp)
                monitors = (
                    data if isinstance(data, list) else data.get("monitors", [])
                )
                return [
                    {
                        "id": m.get("id"),
                        "name": m.get("name"),
                        "type": m.get("type"),
                    }
                    for m in monitors
                    if m.get("id") is not None
                ]
        except Exception as exc:
            logger.error("Failed to list Uptime Kuma monitors: %s", exc)
            return []

    def test_connection(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        """Verify connectivity to Uptime Kuma.

        Returns ``{"success": True/False, "message": "..."}``
        """
        creds = self._resolve_credentials(url, username, password)
        if creds is None:
            return {
                "success": False,
                "message": (
                    "Uptime Kuma integration is not enabled or credentials "
                    "are missing. Fill in the URL, username, and password."
                ),
            }
        base, uname, pwd = creds

        try:
            with httpx.Client(timeout=10) as client:
                token = self._login(client, base, uname, pwd)
                headers = self._auth_headers(token)
                resp = client.get(f"{base}/api/monitors", headers=headers)
                resp.raise_for_status()
                data = self._parse_json_response(resp)
                monitors = (
                    data if isinstance(data, list) else data.get("monitors", [])
                )
                return {
                    "success": True,
                    "message": (
                        f"Connected successfully – {len(monitors)} monitor(s) found"
                    ),
                }
        except httpx.HTTPStatusError as exc:
            return {
                "success": False,
                "message": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}


uptime_kuma_service = UptimeKumaService()
