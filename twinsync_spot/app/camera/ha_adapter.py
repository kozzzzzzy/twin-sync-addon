"""Home Assistant camera adapter."""

import os
import logging
from typing import Optional, List

import aiohttp

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

    async def get_cameras(self) -> List[Camera]:
        """Get list of camera entities from Home Assistant.

        Returns a list of Camera models. If anything fails (no token, bad
        response, exception), it returns an empty list and logs the reason.
        """
        token = self._get_token()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            # Some Supervisor setups also honour this legacy header
            "X-Hassio-Key": token,
        }

        cameras: List[Camera] = []

        try:
            async with aiohttp.ClientSession() as session:
                states_url = f"{self.ha_base_url}/api/states"
                async with session.get(states_url, headers=headers) as response:
                    if response.status != 200:
                        detail = (await response.text())[:200]
                        LOGGER.warning(
                            "Failed to fetch states from Home Assistant: %s %s",
                            response.status,
                            detail,
                        )
                        return []

                    states = await response.json()

            # Extract all camera.* entities
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

        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Error fetching cameras: %s", exc)
            return []

        return cameras

    async def get_snapshot(self, entity_id: str) -> Optional[bytes]:
        """Get a snapshot from a camera."""
        token = self._get_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Hassio-Key": token,
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.ha_base_url}/api/camera_proxy/{entity_id}"
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        detail = (await response.text())[:200]
                        LOGGER.warning(
                            "Failed to get snapshot for %s: %s %s",
                            entity_id,
                            response.status,
                            detail,
                        )
                        return None

                    return await response.read()

        except Exception as exc:  # noqa: BLE001
            LOGGER.exception(
                "Error getting snapshot for %s: %s",
                entity_id,
                exc,
            )
            return None

    async def test_camera(self, entity_id: str) -> bool:
        """Test if a camera is accessible."""
        snapshot = await self.get_snapshot(entity_id)
        return bool(snapshot)
