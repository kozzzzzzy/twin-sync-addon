"""API routes for TwinSync Spot."""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.models import SPOT_TEMPLATES, SpotStatus
from app.core.voices import get_all_voices
from app.core.analyzer import SpotAnalyzer
from app.camera.ha_adapter import HACamera


router = APIRouter()


def _extract_ha_token(request: Request) -> Optional[str]:
    """Extract Home Assistant access token from request.
    
    Checks in order:
    1. Authorization: Bearer <token> header
    2. X-Hassio-Key header  
    3. x-hassio-key header (lowercase)
    4. Environment variables (fallback)
    
    HA's ingress proxy adds these headers when proxying requests.
    """
    # Check Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token

    # Check X-Hassio-Key header (various cases)
    for header_name in ("X-Hassio-Key", "x-hassio-key", "X-HASSIO-KEY"):
        token = request.headers.get(header_name)
        if token:
            return token

    # Fallback to environment
    return os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")


# Request/Response models
class CreateSpotRequest(BaseModel):
    name: str
    camera_entity: str
    definition: str
    spot_type: str = "custom"
    voice: str = "supportive"
    custom_voice_prompt: Optional[str] = None


class UpdateSpotRequest(BaseModel):
    name: Optional[str] = None
    camera_entity: Optional[str] = None
    definition: Optional[str] = None
    spot_type: Optional[str] = None
    voice: Optional[str] = None
    custom_voice_prompt: Optional[str] = None


class SnoozeRequest(BaseModel):
    minutes: int = 30


# Spots
@router.get("/spots")
async def list_spots(request: Request):
    """List all spots."""
    db = request.app.state.db
    spots = await db.get_all_spots()
    
    return {
        "spots": [
            {
                "id": s.id,
                "name": s.name,
                "camera_entity": s.camera_entity,
                "definition": s.definition,
                "spot_type": s.spot_type,
                "voice": s.voice,
                "status": s.status.value if isinstance(s.status, SpotStatus) else s.status,
                "last_check": s.last_check,
                "current_streak": s.current_streak,
                "longest_streak": s.longest_streak,
                "snoozed_until": s.snoozed_until,
            }
            for s in spots
        ]
    }


@router.post("/spots")
async def create_spot(request: Request, data: CreateSpotRequest):
    """Create a new spot."""
    db = request.app.state.db
    
    spot_id = await db.create_spot(
        name=data.name,
        camera_entity=data.camera_entity,
        definition=data.definition,
        spot_type=data.spot_type,
        voice=data.voice,
        custom_voice_prompt=data.custom_voice_prompt,
    )
    
    return {"id": spot_id, "message": "Spot created"}


@router.get("/spots/{spot_id}")
async def get_spot(request: Request, spot_id: int):
    """Get a spot with its memory."""
    db = request.app.state.db
    
    spot = await db.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    memory = await db.get_spot_memory(spot_id)
    recent_checks = await db.get_recent_checks(spot_id, limit=10)
    
    return {
        "spot": {
            "id": spot.id,
            "name": spot.name,
            "camera_entity": spot.camera_entity,
            "definition": spot.definition,
            "spot_type": spot.spot_type,
            "voice": spot.voice,
            "custom_voice_prompt": spot.custom_voice_prompt,
            "status": spot.status.value if isinstance(spot.status, SpotStatus) else spot.status,
            "last_check": spot.last_check,
            "current_streak": spot.current_streak,
            "longest_streak": spot.longest_streak,
            "snoozed_until": spot.snoozed_until,
            "total_resets": spot.total_resets,
        },
        "memory": {
            "total_checks": memory.total_checks,
            "patterns": {
                "recurring_items": memory.patterns.recurring_items,
                "worst_day": memory.patterns.worst_day,
                "best_day": memory.patterns.best_day,
                "usually_sorted_by": memory.patterns.usually_sorted_by,
            }
        },
        "recent_checks": recent_checks,
    }


@router.put("/spots/{spot_id}")
async def update_spot(request: Request, spot_id: int, data: UpdateSpotRequest):
    """Update a spot."""
    db = request.app.state.db
    
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    success = await db.update_spot(spot_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    return {"message": "Spot updated"}


@router.delete("/spots/{spot_id}")
async def delete_spot(request: Request, spot_id: int):
    """Delete a spot."""
    db = request.app.state.db
    
    success = await db.delete_spot(spot_id)
    if not success:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    return {"message": "Spot deleted"}


@router.post("/spots/{spot_id}/check")
async def check_spot(request: Request, spot_id: int):
    """Run a check on a spot."""
    db = request.app.state.db
    
    spot = await db.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    # Extract token from request headers
    token = _extract_ha_token(request)
    
    # Get camera snapshot
    camera = HACamera()
    image_bytes = await camera.get_snapshot(spot.camera_entity, token)
    
    if not image_bytes:
        raise HTTPException(status_code=500, detail="Failed to get camera snapshot")
    
    # Get memory for context
    memory = await db.get_spot_memory(spot_id)
    
    # Analyze with Gemini
    analyzer = SpotAnalyzer()
    result = await analyzer.analyze(
        image_bytes=image_bytes,
        spot_name=spot.name,
        definition=spot.definition,
        voice=spot.voice,
        custom_voice_prompt=spot.custom_voice_prompt,
        memory=memory,
    )
    
    # Save check result
    check_id = await db.save_check(spot_id, result)
    
    # If needs_attention, reset streak
    if result.status == "needs_attention":
        await db.update_spot(spot_id, current_streak=0)
    
    return {
        "check_id": check_id,
        "status": result.status,
        "to_sort": result.to_sort,
        "looking_good": result.looking_good,
        "notes": result.notes,
        "error_message": result.error_message,
        "api_response_time": result.api_response_time,
    }


@router.post("/spots/{spot_id}/reset")
async def reset_spot(request: Request, spot_id: int):
    """Mark a spot as fixed (reset)."""
    db = request.app.state.db
    
    spot = await db.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    await db.record_reset(spot_id)
    
    return {"message": "Spot reset", "new_streak": spot.current_streak + 1}


@router.post("/spots/{spot_id}/snooze")
async def snooze_spot(request: Request, spot_id: int, data: SnoozeRequest):
    """Snooze a spot for N minutes."""
    db = request.app.state.db
    
    spot = await db.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    snoozed_until = (datetime.utcnow() + timedelta(minutes=data.minutes)).isoformat()
    await db.update_spot(spot_id, snoozed_until=snoozed_until, status="snoozed")
    
    return {"message": f"Snoozed for {data.minutes} minutes", "until": snoozed_until}


@router.post("/spots/{spot_id}/unsnooze")
async def unsnooze_spot(request: Request, spot_id: int):
    """Cancel snooze on a spot."""
    db = request.app.state.db
    
    spot = await db.get_spot(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")
    
    await db.update_spot(spot_id, snoozed_until=None, status="unknown")
    
    return {"message": "Snooze cancelled"}


@router.post("/check-all")
async def check_all_spots(request: Request):
    """Check all spots."""
    db = request.app.state.db
    spots = await db.get_all_spots()
    
    # Extract token from request headers
    token = _extract_ha_token(request)
    
    results = []
    camera = HACamera()
    analyzer = SpotAnalyzer()
    
    for spot in spots:
        # Skip snoozed spots
        if spot.snoozed_until:
            try:
                snoozed_until = datetime.fromisoformat(spot.snoozed_until)
                if snoozed_until > datetime.utcnow():
                    results.append({"spot_id": spot.id, "status": "snoozed"})
                    continue
            except ValueError:
                pass
        
        # Get snapshot (pass token)
        image_bytes = await camera.get_snapshot(spot.camera_entity, token)
        if not image_bytes:
            results.append({"spot_id": spot.id, "status": "error", "error": "Failed to get snapshot"})
            continue
        
        # Get memory
        memory = await db.get_spot_memory(spot.id)
        
        # Analyze
        result = await analyzer.analyze(
            image_bytes=image_bytes,
            spot_name=spot.name,
            definition=spot.definition,
            voice=spot.voice,
            custom_voice_prompt=spot.custom_voice_prompt,
            memory=memory,
        )
        
        # Save
        await db.save_check(spot.id, result)
        
        if result.status == "needs_attention":
            await db.update_spot(spot.id, current_streak=0)
        
        results.append({
            "spot_id": spot.id,
            "status": result.status,
            "to_sort_count": len(result.to_sort),
        })
    
    return {"results": results}


# Cameras
@router.get("/cameras")
async def list_cameras(request: Request):
    """List available cameras from Home Assistant."""
    # Extract token from request headers
    token = _extract_ha_token(request)
    
    camera = HACamera()
    cameras = await camera.get_cameras(token)
    
    return {
        "cameras": [
            {"entity_id": c.entity_id, "name": c.name, "state": c.state}
            for c in cameras
        ]
    }


# Spot types and templates
@router.get("/spot-types")
async def get_spot_types():
    """Get spot types with their templates."""
    return {
        "types": [
            {"key": key, "template": template}
            for key, template in SPOT_TEMPLATES.items()
        ]
    }


# Voices
@router.get("/voices")
async def get_voices():
    """Get available voices."""
    return {"voices": get_all_voices()}


# Settings
@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    return {
        "has_api_key": bool(gemini_key and len(gemini_key) > 10),
        "mode": "addon" if os.environ.get("SUPERVISOR_TOKEN") else "standalone",
    }


@router.post("/settings/validate-key")
async def validate_api_key():
    """Validate the Gemini API key."""
    analyzer = SpotAnalyzer()
    valid = await analyzer.validate_api_key()
    
    return {"valid": valid}
