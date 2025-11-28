"""RTSP/HTTP camera adapter for standalone mode."""

import asyncio
import subprocess
from typing import Optional

import aiohttp

from app.core.models import Camera


class RTSPCamera:
    """Access cameras via RTSP or HTTP snapshot URLs."""
    
    async def get_snapshot_rtsp(self, url: str) -> Optional[bytes]:
        """Get snapshot from RTSP stream using ffmpeg."""
        try:
            # Use ffmpeg to grab a single frame
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-i", url,
                "-vframes", "1",
                "-f", "image2",
                "-c:v", "mjpeg",
                "-q:v", "2",
                "-y",
                "pipe:1"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )
            
            if process.returncode != 0:
                print(f"ffmpeg error: {stderr.decode()[:200]}")
                return None
            
            return stdout
            
        except asyncio.TimeoutError:
            print("RTSP snapshot timed out")
            return None
        except Exception as e:
            print(f"RTSP error: {e}")
            return None
    
    async def get_snapshot_http(self, url: str) -> Optional[bytes]:
        """Get snapshot from HTTP URL."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=30) as resp:
                    if resp.status != 200:
                        print(f"HTTP snapshot error: {resp.status}")
                        return None
                    
                    return await resp.read()
            except Exception as e:
                print(f"HTTP snapshot error: {e}")
                return None
    
    async def get_snapshot(self, camera: Camera) -> Optional[bytes]:
        """Get snapshot from camera based on type."""
        if not camera.url:
            return None
        
        if camera.source_type == "rtsp":
            return await self.get_snapshot_rtsp(camera.url)
        elif camera.source_type == "http":
            return await self.get_snapshot_http(camera.url)
        else:
            return None
    
    async def test_camera(self, camera: Camera) -> bool:
        """Test if camera is accessible."""
        snapshot = await self.get_snapshot(camera)
        return snapshot is not None and len(snapshot) > 0
