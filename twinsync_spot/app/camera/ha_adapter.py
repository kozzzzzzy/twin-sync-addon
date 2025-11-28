"""Home Assistant camera adapter."""

from typing import Optional
import aiohttp

from app.config import settings
from app.core.models import Camera


class HACamera:
    """Access cameras through Home Assistant API."""
    
    def __init__(self):
        self.base_url = settings.ha_base_url
        self.token = settings.supervisor_token
    
    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
    
    async def get_cameras(self) -> list[Camera]:
        """Get list of available cameras from HA."""
        if not self.token:
            return []
        
        url = f"{self.base_url}/api/states"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status != 200:
                        print(f"HA API error: {resp.status}")
                        return []
                    
                    states = await resp.json()
            except Exception as e:
                print(f"Error getting cameras from HA: {e}")
                return []
        
        cameras = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id.startswith("camera."):
                name = state.get("attributes", {}).get("friendly_name", entity_id)
                cameras.append(Camera(
                    entity_id=entity_id,
                    name=name,
                    source_type="ha",
                ))
        
        return cameras
    
    async def get_snapshot(self, entity_id: str) -> Optional[bytes]:
        """Get snapshot from a camera."""
        if not self.token:
            raise ValueError("Not running as HA add-on")
        
        url = f"{self.base_url}/api/camera_proxy/{entity_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=30) as resp:
                    if resp.status != 200:
                        print(f"Camera snapshot error: {resp.status}")
                        return None
                    
                    return await resp.read()
            except Exception as e:
                print(f"Error getting snapshot: {e}")
                return None
    
    async def test_camera(self, entity_id: str) -> bool:
        """Test if camera is accessible."""
        snapshot = await self.get_snapshot(entity_id)
        return snapshot is not None and len(snapshot) > 0
