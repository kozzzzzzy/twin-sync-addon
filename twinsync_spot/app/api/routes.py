"""API routes for TwinSync Spot."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.db.sqlite import Database
from app.core.models import SPOT_TYPES, SpotStatus
from app.core.voices import VOICES
from app.core.analyzer import SpotAnalyzer, AnalyzerError, validate_api_key
from app.core.memory import enrich_items_with_recurring, MemoryEngine
from app.camera.ha_adapter import HACamera
from app.camera.rtsp_adapter import RTSPCamera


router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

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
    minutes: int = 60


class SettingsRequest(BaseModel):
    gemini_api_key: Optional[str] = None


# =============================================================================
# SPOTS ENDPOINTS
# =============================================================================

@router.get("/spots")
async def list_spots(request: Request):
    """List all spots."""
    db: Database = request.app.state.db
    spots = await db.get_all_spots()
    
    result = []
    for spot in spots:
        memory = await db.get_spot_memory(spot.id)
        recent_check = (await db.get_recent_checks(spot.id, limit=1))
        latest = recent_check[0] if recent_check else None
        
        result.append({
            "id": spot.id,
            "name": spot.name,
            "status": spot.status.value,
            "status_emoji": spot.status_emoji,
            "status_text": spot.status_text,
            "is_snoozed": spot.is_snoozed,
            "last_check": spot.last_check.isoformat() if spot.last_check else None,
            "current_streak": memory.current_streak,
            "longest_streak": memory.longest_streak,
            "to_sort_count": latest.to_sort_count if latest else 0,
            "looking_good_count": latest.looking_good_count if latest else 0,
            "to_sort": [
                {
                    "item": item.item,
                    "location": item.location,
                    "recurring": item.recurring,
                    "recurring_count": item.recurring_count,
                }
                for item in (latest.to_sort if latest else [])
            ],
            "looking_good": latest.looking_good if latest else [],
            "notes": {
                "main": latest.notes_main if latest else None,
                "pattern": latest.notes_pattern if latest else None,
                "encouragement": latest.notes_encouragement if latest else None,
            },
        })
    
    return {"spots": result}


@router.post("/spots")
async def create_spot(request: Request, data: CreateSpotRequest):
    """Create a new spot."""
    db: Database = request.app.state.db
    
    spot = await db.create_spot(
        name=data.name,
        camera_entity=data.camera_entity,
        definition=data.definition,
        spot_type=data.spot_type,
        voice=data.voice,
        custom_voice_prompt=data.custom_voice_prompt,
    )
    
    return {"spot": {"id": spot.id, "name": spot.name}}


@router.get("/spots/{spot_id}")
async def get_spot(request: Request, spot_id: int):
    """Get a spot by ID."""
    db: Database = request.app.state.db
    spot = await db.get_spot(spot_id)
    
    if not spot:
        raise HTTPException(404, "Spot not found")
    
    memory = await db.get_spot_memory(spot_id)
    recent_checks = await db.get_recent_checks(spot_id, limit=10)
    
    return {
        "spot": {
            "id": spot.id,
            "name": spot.name,
            "camera_entity": spot.camera_entity,
            "definition": spot.definition,
            "spot_type": spot.spot_type.value,
            "voice": spot.voice,
            "status": spot.status.value,
            "status_emoji": spot.status_emoji,
            "status_text": spot.status_text,
            "is_snoozed": spot.is_snoozed,
            "snoozed_until": spot.snoozed_until.isoformat() if spot.snoozed_until else None,
            "created_at": spot.created_at.isoformat(),
            "last_check": spot.last_check.isoformat() if spot.last_check else None,
        },
        "memory": {
            "current_streak": memory.current_streak,
            "longest_streak": memory.longest_streak,
            "total_checks": memory.total_checks,
            "recurring_items": memory.top_recurring,
            "worst_day": memory.worst_day,
            "best_day": memory.best_day,
            "usually_sorted_by": memory.usually_sorted_by,
        },
        "recent_checks": [
            {
                "id": check.id,
                "timestamp": check.timestamp.isoformat(),
                "status": check.status.value,
                "to_sort_count": check.to_sort_count,
                "looking_good_count": check.looking_good_count,
            }
            for check in recent_checks
        ]
    }


@router.put("/spots/{spot_id}")
async def update_spot(request: Request, spot_id: int, data: UpdateSpotRequest):
    """Update a spot."""
    db: Database = request.app.state.db
    
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No updates provided")
    
    spot = await db.update_spot(spot_id, **updates)
    if not spot:
        raise HTTPException(404, "Spot not found")
    
    return {"spot": {"id": spot.id, "name": spot.name}}


@router.delete("/spots/{spot_id}")
async def delete_spot(request: Request, spot_id: int):
    """Delete a spot."""
    db: Database = request.app.state.db
    
    deleted = await db.delete_spot(spot_id)
    if not deleted:
        raise HTTPException(404, "Spot not found")
    
    return {"deleted": True}


# =============================================================================
# ACTIONS
# =============================================================================

@router.post("/spots/{spot_id}/check")
async def check_spot(request: Request, spot_id: int):
    """Run a check on a spot."""
    db: Database = request.app.state.db
    spot = await db.get_spot(spot_id)
    
    if not spot:
        raise HTTPException(404, "Spot not found")
    
    # Update status to checking
    await db.update_spot(spot_id, status="checking")
    
    # Get camera snapshot
    if settings.is_ha_addon:
        ha_camera = HACamera()
        image_bytes = await ha_camera.get_snapshot(spot.camera_entity)
    else:
        # TODO: Support custom cameras in standalone mode
        raise HTTPException(501, "Standalone camera support coming soon")
    
    if not image_bytes:
        await db.save_check(
            spot_id=spot_id,
            status="error",
            to_sort=[],
            looking_good=[],
            error_message="Failed to get camera snapshot",
        )
        raise HTTPException(500, "Failed to get camera snapshot")
    
    # Get memory for context
    memory = await db.get_spot_memory(spot_id)
    
    # Analyze with Gemini
    analyzer = SpotAnalyzer()
    try:
        result = await analyzer.analyze(
            image_bytes=image_bytes,
            spot_name=spot.name,
            definition=spot.definition,
            voice=spot.voice,
            memory=memory,
        )
    except AnalyzerError as e:
        await db.save_check(
            spot_id=spot_id,
            status="error",
            to_sort=[],
            looking_good=[],
            error_message=str(e),
        )
        raise HTTPException(500, str(e))
    
    # Enrich to_sort with recurring info from memory
    to_sort_items = [
        {"item": item["item"], "location": item.get("location")}
        for item in result["to_sort"]
    ]
    
    # Add recurring flags
    for item in to_sort_items:
        normalized = item["item"].lower().strip()
        if normalized in memory.recurring_items:
            item["recurring"] = True
            item["recurring_count"] = memory.recurring_items[normalized]
        else:
            item["recurring"] = False
            item["recurring_count"] = 0
    
    # Save check result
    check = await db.save_check(
        spot_id=spot_id,
        status=result["status"],
        to_sort=to_sort_items,
        looking_good=result["looking_good"],
        notes_main=result["notes"]["main"],
        notes_pattern=result["notes"]["pattern"],
        notes_encouragement=result["notes"]["encouragement"],
        api_response_time=result.get("api_response_time", 0),
    )
    
    # Update streak if needed
    if result["status"] == "needs_attention":
        await db.update_spot(spot_id, current_streak=0)
    
    return {
        "check_id": check.id,
        "status": result["status"],
        "to_sort": to_sort_items,
        "looking_good": result["looking_good"],
        "notes": result["notes"],
    }


@router.post("/spots/{spot_id}/reset")
async def reset_spot(request: Request, spot_id: int):
    """Mark spot as fixed/sorted."""
    db: Database = request.app.state.db
    
    spot = await db.record_reset(spot_id)
    
    return {
        "status": "sorted",
        "current_streak": spot.current_streak,
        "longest_streak": spot.longest_streak,
    }


@router.post("/spots/{spot_id}/snooze")
async def snooze_spot(request: Request, spot_id: int, data: SnoozeRequest):
    """Snooze a spot."""
    db: Database = request.app.state.db
    
    until = datetime.now() + timedelta(minutes=data.minutes)
    spot = await db.update_spot(spot_id, snoozed_until=until)
    
    if not spot:
        raise HTTPException(404, "Spot not found")
    
    return {"snoozed_until": until.isoformat()}


@router.post("/spots/{spot_id}/unsnooze")
async def unsnooze_spot(request: Request, spot_id: int):
    """Unsnooze a spot."""
    db: Database = request.app.state.db
    
    spot = await db.update_spot(spot_id, snoozed_until=None)
    if not spot:
        raise HTTPException(404, "Spot not found")
    
    return {"snoozed": False}


@router.post("/check-all")
async def check_all_spots(request: Request):
    """Check all spots."""
    db: Database = request.app.state.db
    spots = await db.get_all_spots()
    
    results = []
    for spot in spots:
        if not spot.is_snoozed:
            try:
                # This is simplified - in production, do these in parallel
                result = await check_spot(request, spot.id)
                results.append({"spot_id": spot.id, "status": result["status"]})
            except Exception as e:
                results.append({"spot_id": spot.id, "error": str(e)})
    
    return {"results": results}


# =============================================================================
# UTILITIES
# =============================================================================

@router.get("/cameras")
async def list_cameras(request: Request):
    """List available cameras."""
    if settings.is_ha_addon:
        ha_camera = HACamera()
        cameras = await ha_camera.get_cameras()
        return {"cameras": [{"entity_id": c.entity_id, "name": c.name} for c in cameras]}
    else:
        # Return empty for standalone mode (user adds manually)
        return {"cameras": []}


@router.get("/spot-types")
async def list_spot_types():
    """Get available spot types with templates."""
    return {
        "types": [
            {
                "value": spot_type.value,
                "label": info["label"],
                "template": info["template"],
            }
            for spot_type, info in SPOT_TYPES.items()
        ]
    }


@router.get("/voices")
async def list_voices():
    """Get available voices."""
    return {
        "voices": [
            {
                "value": key,
                "name": voice["name"],
                "description": voice["description"],
                "emoji": voice["emoji"],
            }
            for key, voice in VOICES.items()
        ]
    }


@router.get("/settings")
async def get_settings():
    """Get current settings."""
    return {
        "has_api_key": bool(settings.gemini_api_key),
        "is_ha_addon": settings.is_ha_addon,
    }


@router.post("/settings/validate-key")
async def validate_gemini_key(data: SettingsRequest):
    """Validate a Gemini API key."""
    if not data.gemini_api_key:
        return {"valid": False, "error": "No key provided"}
    
    valid = await validate_api_key(data.gemini_api_key)
    return {"valid": valid}
