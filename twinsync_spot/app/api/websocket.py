"""WebSocket for real-time updates."""

import asyncio
import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Connected clients
clients: Set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates."""
    await websocket.accept()
    clients.add(websocket)
    
    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
            
    except WebSocketDisconnect:
        clients.discard(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        clients.discard(websocket)


async def broadcast(event_type: str, data: dict):
    """Broadcast event to all connected clients."""
    if not clients:
        return
    
    message = json.dumps({"type": event_type, "data": data})
    
    disconnected = set()
    for client in clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    
    # Clean up disconnected clients
    for client in disconnected:
        clients.discard(client)


async def notify_spot_updated(spot_id: int, status: str):
    """Notify clients that a spot was updated."""
    await broadcast("spot_updated", {"spot_id": spot_id, "status": status})


async def notify_check_started(spot_id: int):
    """Notify clients that a check started."""
    await broadcast("check_started", {"spot_id": spot_id})


async def notify_check_complete(spot_id: int, result: dict):
    """Notify clients that a check completed."""
    await broadcast("check_complete", {"spot_id": spot_id, "result": result})
