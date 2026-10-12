"""
GPS Location REST & Debug Endpoints
"""
import time
from fastapi import APIRouter
from app.models import GPSDataModel

router = APIRouter(tags=["GPS"])


@router.get("/api/gps/location", response_model=GPSDataModel)
def get_gps_location():
    from app.main import serial_mgr, demo_mode
    if demo_mode:
        # Synthetic Demo GPS coordinates for AquaGuard Test Facility Alpha
        return GPSDataModel(
            latitude=6.927079,
            longitude=79.861244,
            satellites=9,
            hdop=0.9,
            fix_age_ms=120,
            fix_status="FIX",
            is_stale=False,
            is_demo=True,
            last_updated=time.time()
        )
    
    if serial_mgr:
        gps_dict = serial_mgr.get_gps_status()
        return GPSDataModel(**gps_dict)
    
    return GPSDataModel()


@router.get("/api/debug/gps")
def debug_gps_endpoint():
    from app.main import serial_mgr, demo_mode
    valid_gps_count = serial_mgr.valid_gps_count if serial_mgr else 0
    last_raw_gps_line = serial_mgr.last_raw_gps_line if serial_mgr else None
    latest_gps = serial_mgr.get_gps_status() if serial_mgr else {}
    
    return {
        "valid_gps_count": valid_gps_count,
        "last_raw_gps_line": last_raw_gps_line,
        "latest_gps_data": latest_gps,
        "is_connected": serial_mgr.is_connected if serial_mgr else False,
        "output_mode": serial_mgr.output_mode if serial_mgr else "UNKNOWN",
        "demo_mode": demo_mode
    }
