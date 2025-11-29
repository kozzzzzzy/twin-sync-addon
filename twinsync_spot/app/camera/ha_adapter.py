"""Home Assistant camera adapter."""

import os
import json
import logging
import asyncio
from typing import Optional, List
import urllib.request
import urllib.error

from app.core.models import Camera


LOGGER = logging.getLogger(__name__)


class HACamera:
    """Home Assistant camera adapter."""

    def __init__(self) -> None:
        # Base URL for Home Assistant Core when running as an add-on
        # Supervisor proxy exposes Core at this URL.
        self.ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")

    def _get_token(self) -> Optional[str]:
        """Return an available Supervisor/Home Assistant token.

        We try SUPERVISOR_TOKEN first (current standard), then HASSIO_TOKEN
        as a fallback for older setups.
        """
        token = (
            os.environ.get("SUPERVISOR_TOKEN")
            or os.environ.get("HASSIO_TOKEN")
        )

        if not token:
            LOGGER.warning(
                "Supervisor token unavailable; cannot reach Home Assistant API. "
                "Check hassio_api and homeassistant_api permissions in config.yaml."
            )
            return None

        return token

    # -------------------- blocking helpers (run in a thread) --------------------

    def _fetch_states_sync(self, token: str) -> list[dict]:
        """Blocking HTTP call to /api/states using standard library."""
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Hassio-Key": token,
        }
        url = f"{self.ha_base_url}/api/states"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)

    def _fetch_snapshot_sync(self, token: str, entity_id: str) -> Optional[bytes]:
        """Blocking HTTP call to /api/camera_proxy/<entity_id>."""
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Hassio-Key": token,
        }
        url = f"{self.ha_base_url}/api/camera_proxy/{entity_id}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    # -------------------------- async public API -------------------------------

    async def get_cameras(self) -> List[Camera]:
        """Get list of camera entities from Home Assistant."""
        token = self._get_token()
        if not token:
            return []

        try:
            # Run the blocking HTTP in a thread so we don't freeze the event loop
            states = await asyncio.to_thread(self._fetch_states_sync, token)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Error fetching cameras from Home Assistant: %s", exc)
            return []

        cameras: List[Camera] = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id.startswith("camera."):
                cameras.append(
                    Camera(
                        entity_id=entity_id,
                        name=state.get("attributes", {}).get(
                            "friendly_name", entity_id
                        ),
                        state=state.get("state", "unknown"),
                    )
                )

        LOGGER.info("Discovered %d cameras from Home Assistant", len(cameras))
        return cameras

    async def get_snapshot(self, entity_id: str) -> Optional[bytes]:
        """Get a snapshot from a camera."""
        token = self._get_token()
        if not token:
            return None

        try:
            return await asyncio.to_thread(
                self._fetch_snapshot_sync,
                token,
                entity_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Error getting snapshot for %s: %s", entity_id, exc)
            return None

    async def test_camera(self, entity_id: str) -> bool:
        """Test if a camera is accessible."""
        snapshot = await self.get_snapshot(entity_id)
        return bool(snapshot)
