import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import init_db, engine
from app.routers import auth, stations, slots, cctv_analysis

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure runtime directories exist and initialize database schemas on startup."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.YOLO_MODEL_PATH.parent, exist_ok=True)
    init_db()
    yield
    # Gracefully terminate any running camera stream workers on shutdown
    try:
        from app.services.live_camera_service import live_camera_manager
        live_camera_manager.shutdown_all()
    except Exception:
        pass

app = FastAPI(
    title="FuelFlow API",
    description="Real Fuel-Station Queue Management and Recommendation System",
    version="0.3.0",
    lifespan=lifespan
)

# CORS setup for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth.router)
app.include_router(stations.router)
app.include_router(slots.router)
app.include_router(cctv_analysis.router)

@app.get("/api/health")
def health_check():
    """Health check endpoint to verify API and persistent database status."""
    db_status = "connected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "FuelFlow Backend API",
        "version": "0.2.0",
        "environment": settings.ENVIRONMENT,
        "database": db_status
    }
