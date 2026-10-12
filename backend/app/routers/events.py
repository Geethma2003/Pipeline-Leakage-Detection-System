"""
Events History REST Endpoints
"""
import csv
import io
from fastapi import APIRouter, Query, HTTPException, Response
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.database import get_recent_events, update_event_operator_status, clear_events

router = APIRouter(prefix="/api/events", tags=["Events"])


class EventOperatorUpdate(BaseModel):
    operator_status: str  # "ACKNOWLEDGED", "CONFIRMED_LEAK", "FALSE_ALARM"
    operator_note: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]])
def get_events(limit: int = Query(100, ge=1, le=1000), status: Optional[str] = None):
    return get_recent_events(limit=limit, status_filter=status)


@router.patch("/{event_id}")
def update_event(event_id: int, payload: EventOperatorUpdate):
    update_event_operator_status(event_id, payload.operator_status, payload.operator_note)
    return {"status": "success", "event_id": event_id, "updated_status": payload.operator_status}


@router.delete("")
def delete_all_events(demo_only: bool = Query(False)):
    clear_events(demo_only=demo_only)
    return {"status": "success", "message": "Events cleared."}


@router.get("/export/csv")
def export_events_csv():
    events = get_recent_events(limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "timestamp", "status", "severity",
        "s1_abnormal_sec", "s2_abnormal_sec", "s1_med_rms", "s2_med_rms",
        "reasoning", "operator_status", "operator_note", "is_demo"
    ])
    for ev in events:
        writer.writerow([
            ev.get("id"), ev.get("timestamp"), ev.get("status"), ev.get("severity"),
            ev.get("s1_abnormal_sec"), ev.get("s2_abnormal_sec"), ev.get("s1_med_rms"), ev.get("s2_med_rms"),
            ev.get("reasoning"), ev.get("operator_status"), ev.get("operator_note"), ev.get("is_demo")
        ])
    return Response(content=output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=aquaguard_events_export.csv"
    })
