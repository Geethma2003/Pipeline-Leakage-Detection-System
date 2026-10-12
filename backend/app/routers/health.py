"""
System Health & Diagnostics REST Endpoints
"""
import time
from fastapi import APIRouter
from app.config import PIPE_LENGTH_METERS, SENSOR_1_POSITION, SENSOR_2_POSITION, SAMPLE_RATE_HZ

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("")
def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "pipe_length_m": PIPE_LENGTH_METERS,
        "s1_position_m": SENSOR_1_POSITION,
        "s2_position_m": SENSOR_2_POSITION,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "system": "AquaGuard AI Pipeline Monitor"
    }
