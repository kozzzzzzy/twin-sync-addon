"""Home Assistant camera adapter."""
import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, List
import urllib.request
import urllib.error

from app.core.models import Camera


LOGGER = logging.getLogger(__name__)

# Token file location (written by run.sh)
TOKEN_FILE = Path("/data/.supervisor_token")


class HACamera:
    """Home Assistant camera adapter."""

    def __init__(self) -> None:
        self.ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")

    def _get_token_from_env(self) -> Optional[str]:
        """Get token from environment variables."""
        return os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")

    def _get_token_from_file(self) -> Optional[str]:
        """Get token from file (written by run.sh)."""
        try:
            if TOKEN_FILE.exists():
                token = TOKEN_FILE.read_text().strip()
                if token and len(token) > 10:
                    return token
        except Exception as exc:
            LOGGER.debug("Could not read token file: %s", exc)
        return None

    def _get_token(self, provided_token: Optional[str] = None) -> Optional[str]:
        """Get token from provided value, env, or file.
        
        Priority:
        1. Explicitly provided token (from request headers)
        2. Environment variables
        3. Token file
        """
        # 1. Use provided token if given
        if provided_token and len(provided_token) > 10:
            return provided_token

        # 2. Try environment
        token = self._get_token_from_env()
        if token:
            return token

        # 3. Try file
        token = self._get_token_from_file()
        if token:
            return token

        LOGGER.warning(
            "No supervisor token available. Checked: env vars, token file. "
            "Camera discovery will not work."
        )
        return None

    # -------------------- blocking helpers (run in a thread) --------------------

    def _fetch_states_sync(self, token: str) -> List[dict]:
        """Blocking HTTP call to /api/states using standard library."""
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Hassio-Key": token,
        }
        url = f"{self.ha_base_url}/api/states"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            LOGGER.error("HTTP error fetching states: %s %s", e.code, e.reason)
            raise
        except urllib.error.URLError as e:
            LOGGER.error("URL error fetching states: %s", e.reason)
            raise

    def _fetch_snapshot_sync(self, token: str, entity_id: str) -> Optional[bytes]:
        """Blocking HTTP call to /api/camera_proxy/<entity_id>."""
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Hassio-Key": token,
        }
        url = f"{self.ha_base_url}/api/camera_proxy/{entity_id}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            LOGGER.error("HTTP error fetching snapshot for %s: %s %s", entity_id, e.code, e.reason)
            return None
        except urllib.error.URLError as e:
            LOGGER.error("URL error fetching snapshot for %s: %s", entity_id, e.reason)
            return None

    # -------------------------- async public API -------------------------------

    async def get_cameras(self, token: Optional[str] = None) -> List[Camera]:
        """Get list of camera entities from Home Assistant.
        
        Args:
            token: Optional auth token. If not provided, will try env/file.
        """
        resolved_token = self._get_token(token)
        if not resolved_token:
            return []

        try:
            states = await asyncio.to_thread(self._fetch_states_sync, resolved_token)
        except Exception as exc:
            LOGGER.exception("Error fetching cameras from Home Assistant: %s", exc)
            return []

        cameras: List[Camera] = []
        for state in states:
            entity_id = state.get("entity_id", "") or ""
            if entity_id.startswith("camera."):
                cameras.append(
                    Camera(
                        entity_id=entity_id,
                        name=state.get("attributes", {}).get("friendly_name", entity_id),
                        state=state.get("state", "unknown"),
                    )
                )

        LOGGER.info("Discovered %d cameras from Home Assistant", len(cameras))
        return cameras

    async def get_snapshot(self, entity_id: str, token: Optional[str] = None) -> Optional[bytes]:
        """Get a snapshot from a camera.
        
        Args:
            entity_id: The camera entity ID (e.g., camera.living_room)
            token: Optional auth token. If not provided, will try env/file.
        """
        resolved_token = self._get_token(token)
        if not resolved_token:
            LOGGER.warning("No token available for snapshot request")
            return None

        try:
            return await asyncio.to_thread(
                self._fetch_snapshot_sync,
                resolved_token,
                entity_id,
            )
        except Exception as exc:
            LOGGER.exception("Error getting snapshot for %s: %s", entity_id, exc)
            return None

    async def test_camera(self, entity_id: str, token: Optional[str] = None) -> bool:
        """Test if a camera is accessible."""
        snapshot = await self.get_snapshot(entity_id, token)
        return bool(snapshot)
