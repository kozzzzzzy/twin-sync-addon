"""TwinSync Spot - Does this match YOUR definition?"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.config import settings
from app.db.sqlite import Database
from app.api.routes import router as api_router
from app.api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("🚀 TwinSync Spot starting up...")
    
    # Initialize database
    db = Database()
    await db.init()
    app.state.db = db
    
    print(f"📁 Data directory: {settings.data_dir}")
    print(f"🔑 Gemini API key: {'configured' if settings.gemini_api_key else 'NOT SET'}")
    print(f"🏠 HA mode: {settings.is_ha_addon}")
    print("✅ Ready!")
    
    yield
    
    # Shutdown
    print("👋 TwinSync Spot shutting down...")
    await db.close()


app = FastAPI(
    title="TwinSync Spot",
    description="Does this match YOUR definition?",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
)

# Get the directory where this file lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web/static")), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web/templates"))

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "ingress_path": settings.ingress_path,
        }
    )


@app.get("/spot/{spot_id}", response_class=HTMLResponse)
async def spot_detail(request: Request, spot_id: int):
    """Spot detail page."""
    db: Database = request.app.state.db
    spot = await db.get_spot(spot_id)
    
    if not spot:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Spot not found", "ingress_path": settings.ingress_path},
            status_code=404
        )
    
    checks = await db.get_recent_checks(spot_id, limit=10)
    memory = await db.get_spot_memory(spot_id)
    
    return templates.TemplateResponse(
        "spot_detail.html",
        {
            "request": request,
            "spot": spot,
            "checks": checks,
            "memory": memory,
            "ingress_path": settings.ingress_path,
        }
    )


@app.get("/add", response_class=HTMLResponse)
async def add_spot_page(request: Request):
    """Add new spot page."""
    db: Database = request.app.state.db
    cameras = await get_available_cameras()
    
    return templates.TemplateResponse(
        "add_spot.html",
        {
            "request": request,
            "cameras": cameras,
            "spot_types": SPOT_TYPES,
            "voices": VOICES,
            "ingress_path": settings.ingress_path,
        }
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "ingress_path": settings.ingress_path,
        }
    )


async def get_available_cameras():
    """Get list of available cameras."""
    from app.camera.ha_adapter import HACamera
    
    if settings.is_ha_addon:
        ha_camera = HACamera()
        return await ha_camera.get_cameras()
    return []


# Import these here to avoid circular imports
from app.core.voices import VOICES
from app.core.models import SPOT_TYPES
