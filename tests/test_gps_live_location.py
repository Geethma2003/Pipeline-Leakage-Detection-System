"""
Tests for AquaGuard AI GPS Live-Location Integration
====================================================
Tests:
1. GPS fix unavailable (coords = None, NO_FIX, is_stale = True).
2. GPS fix becomes available (valid latitude & longitude parsed).
3. Valid latitude and longitude transmitted via multiline receiver format
   (separate 'Latitude   :' and 'Longitude  :' lines) and RF24_V1.
4. GPS coordinates are stored in SQLite wireless_telemetry_records.
5. FastAPI / WebSocket payload contains valid coordinates and updates properly.
6. GPS signal lost (transition to STALE after 5 seconds or NO_FIX).
7. Hardcoded fallback coordinates (Moratuwa) NEVER appear as a live location.
8. Stale GPS coordinates (>5 seconds) are flagged is_stale=True and not current.
9. Zero coordinates (0.0, 0.0) are rejected as an invalid fix.
"""
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app, serial_mgr
from app.serial_manager import SerialManager
from app.database import (
    init_db,
    save_wireless_record,
    get_latest_wireless_record,
    get_db_connection
)
from app.models import GPSDataModel


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_gps_fix_unavailable():
    """Requirement 1 & 7: When GPS fix is unavailable, coordinates are None and NO_FIX is reported."""
    mgr = SerialManager()

    # Simulate receiver packet with NO satellite fix
    lines = [
        "Packet #1  (Node 1, Seq 101, missed since last: 0, total missed: 0)",
        "GPS Fix    : NO (searching for satellites...)",
        "Satellites : 0",
        "HDOP       : --",
        "Flow inlet : 0.00 L/min",
        "Flow outlet: 0.00 L/min",
        "Leak alarm : no",
        "Piezo 1    : RMS 15.2  P2P 93",
        "Piezo 2    : RMS 138.1  P2P 823"
    ]
    for line in lines:
        mgr._parse_and_dispatch(line)

    status = mgr.get_gps_status()
    assert status["latitude"] is None
    assert status["longitude"] is None
    assert status["satellites"] == 0
    assert status["fix_status"] == "NO_FIX"
    assert status["is_stale"] is True

    # Critical check: hardcoded Moratuwa coordinates (6.79719 / 6.7951) never appear
    assert status["latitude"] != 6.79719
    assert status["latitude"] != 6.7951
    assert status["longitude"] != 79.90109
    assert status["longitude"] != 79.9009


def test_gps_separate_line_parsing_and_fix_available():
    """Requirements 2 & 3: Receiver outputs separate Latitude and Longitude lines."""
    mgr = SerialManager()

    lines = [
        "Packet #2  (Node 1, Seq 102, missed since last: 0, total missed: 0)",
        "GPS Fix    : YES",
        "Satellites : 7",
        "HDOP       : 1.2",
        "Date (UTC) : 2026-10-11",
        "Time (UTC) : 00:45:10",
        "Latitude   : 6.8412345",
        "Longitude  : 79.9123456",
        "Flow inlet : 2.50 L/min",
        "Flow outlet: 2.50 L/min",
        "Leak alarm : no",
        "Piezo 1    : RMS 14.5  P2P 88",
        "Piezo 2    : RMS 132.0  P2P 780"
    ]
    for line in lines:
        mgr._parse_and_dispatch(line)

    status = mgr.get_gps_status()
    assert status["latitude"] == 6.8412345
    assert status["longitude"] == 79.9123456
    assert status["satellites"] == 7
    assert status["hdop"] == 1.2
    assert status["fix_status"] == "FIX"
    assert status["is_stale"] is False
    assert mgr.valid_gps_count >= 1

    # Check wireless dictionary
    w = mgr.get_wireless_status()
    assert w is not None
    assert w["gps_valid"] is True
    assert w["latitude"] == 6.8412345
    assert w["longitude"] == 79.9123456
    assert w["satellites"] == 7
    assert w["gps_time"] == "2026-10-11T00:45:10Z"


def test_gps_zero_coordinates_rejected():
    """Requirement 9: Reject 0.0, 0.0 as fake valid coordinates."""
    mgr = SerialManager()

    # Receiver outputs 0.0000000
    lines = [
        "Packet #3  (Node 1, Seq 103, missed since last: 0, total missed: 0)",
        "GPS Fix    : YES",
        "Satellites : 0",
        "HDOP       : 99.9",
        "Latitude   : 0.0000000",
        "Longitude  : 0.0000000",
        "Flow inlet : 0.00 L/min",
        "Flow outlet: 0.00 L/min",
        "Leak alarm : no",
        "Piezo 1    : RMS 10.0  P2P 50",
        "Piezo 2    : RMS 10.0  P2P 50"
    ]
    for line in lines:
        mgr._parse_and_dispatch(line)

    status = mgr.get_gps_status()
    # (0, 0) MUST NOT be accepted as a valid fix
    assert status["latitude"] is None
    assert status["longitude"] is None
    assert status["fix_status"] == "NO_FIX"
    assert status["is_stale"] is True


def test_gps_coordinates_saved_in_sqlite():
    """Requirement 4: Verify coordinates are persisted in SQLite database."""
    test_dict = {
        "utc_timestamp": "2026-10-11T00:45:10Z",
        "node_id": 1,
        "packet_sequence": 102,
        "flow_in_lpm": 2.50,
        "flow_out_lpm": 2.50,
        "flow_diff_lpm": 0.0,
        "leak_alarm": False,
        "rms1": 14.5,
        "p2p1": 88,
        "rms2": 132.0,
        "p2p2": 780,
        "s1_clipped": False,
        "s2_clipped": False,
        "vibration_invalid": False,
        "gps_valid": True,
        "latitude": 6.8412345,
        "longitude": 79.9123456,
        "satellites": 7,
        "hdop": 1.2,
        "gps_time": "2026-10-11T00:45:10Z",
        "missed_packets": 0,
        "sequence_reset": 0,
        "communication_source": "ARDUINO_UNO_NRF24",
        "is_demo": False
    }

    row_id = save_wireless_record(test_dict)
    assert row_id > 0

    latest = get_latest_wireless_record()
    assert latest is not None
    assert latest["gps_valid"] == 1
    assert abs(latest["latitude"] - 6.8412345) < 1e-6
    assert abs(latest["longitude"] - 79.9123456) < 1e-6
    assert latest["satellites"] == 7
    assert latest["hdop"] == 1.2


def test_fastapi_gps_location_endpoint():
    """Requirement 5: FastAPI returns valid coordinates and debug info."""
    client = TestClient(app)

    # First test demo mode disabled
    client.post("/api/mode", json={"demo_mode": False})

    # Feed real GPS coordinates to serial_mgr
    lines = [
        "Packet #10  (Node 1, Seq 110, missed since last: 0, total missed: 0)",
        "GPS Fix    : YES",
        "Satellites : 9",
        "HDOP       : 0.9",
        "Latitude   : 6.8500000",
        "Longitude  : 79.9200000",
        "Flow inlet : 5.00 L/min",
        "Flow outlet: 5.00 L/min",
        "Leak alarm : no",
        "Piezo 1    : RMS 15.0  P2P 90",
        "Piezo 2    : RMS 140.0  P2P 800"
    ]
    for line in lines:
        serial_mgr._parse_and_dispatch(line)

    res = client.get("/api/gps/location")
    assert res.status_code == 200
    data = res.json()
    assert data["latitude"] == 6.85
    assert data["longitude"] == 79.92
    assert data["satellites"] == 9
    assert data["fix_status"] == "FIX"
    assert data["is_stale"] is False

    # Debug endpoint
    debug_res = client.get("/api/debug/gps")
    assert debug_res.status_code == 200
    debug_data = debug_res.json()
    assert debug_data["valid_gps_count"] >= 1
    assert debug_data["latest_gps_data"]["latitude"] == 6.85


def test_gps_staleness_and_signal_lost():
    """Requirement 6 & 8: If no new GPS fixes arrive for >5.0s, status becomes STALE."""
    mgr = SerialManager()

    # Valid fix arrives
    mgr._parse_and_dispatch("RF24_V1,1,200,1,68412345,799123456,8,11,26,10,11,0,0,0,1000,1000,5,5,2,2,0,0")
    assert mgr.get_gps_status()["fix_status"] == "FIX"
    assert mgr.get_gps_status()["is_stale"] is False

    # Simulate 6.0 seconds passing without a new GPS fix
    with mgr.lock:
        mgr.latest_gps_data["last_updated"] = time.time() - 6.0

    stale_status = mgr.get_gps_status()
    assert stale_status["is_stale"] is True
    assert stale_status["fix_status"] == "STALE"


def test_no_hardcoded_fallback_returned_when_disconnected():
    """Requirement 7: No hardcoded fallback coordinates exist when disconnected or uninitialized."""
    mgr = SerialManager()
    status = mgr.get_gps_status()
    assert status["latitude"] is None
    assert status["longitude"] is None
    assert status["fix_status"] == "NO_FIX"
    assert status["is_stale"] is True
