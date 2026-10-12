"""
Settings & Hardware Control REST Endpoints
"""
import time
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.serial_manager import list_available_ports
from app.models import SerialConfigModel

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SerialConnectRequest(BaseModel):
    port: str
    baud_rate: int = 115200


class CommandRequest(BaseModel):
    command: str  # "CALIBRATE", "CSV_MODE", "VERBOSE_MODE", "SET_PERSISTENCE"
    parameter: Optional[int] = None
    confirm_no_leak: Optional[bool] = False


@router.get("/ports", response_model=List[Dict[str, Any]])
def get_serial_ports():
    return list_available_ports()


@router.get("/status", response_model=SerialConfigModel)
def get_serial_status():
    t0 = time.perf_counter()
    from app.main import serial_mgr, demo_mode
    if serial_mgr:
        status = serial_mgr.get_status()
        status.output_mode = "DEMO" if demo_mode else "CSV"
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms > 100.0:
            print(f"[STATUS WARNING] Slow status response: {elapsed_ms:.2f} ms")
        return status
    return SerialConfigModel(port="NOT_CONNECTED", connected=False)
