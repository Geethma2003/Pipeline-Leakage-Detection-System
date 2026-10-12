"""
Telemetry REST Endpoints
"""
from fastapi import APIRouter, Query
from typing import List, Dict, Any
from app.database import get_telemetry_history

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


@router.get("/history", response_model=List[Dict[str, Any]])
def get_history(limit: int = Query(500, ge=1, le=2000)):
    return get_telemetry_history(limit=limit)
