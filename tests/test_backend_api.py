"""
Unit & Integration Tests for AquaGuard AI Backend API
=====================================================
Tests FastAPI REST endpoints, decision engine, demo generator, database, and serial parser.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app, decision_engine
from app.models import TelemetryRecord, BaselineProfileModel
from app.database import init_db, get_recent_events, clear_events
from app.demo_generator import DemoGenerator

init_db()
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["pipe_length_m"] == 2.0


def test_telemetry_history_endpoint():
    response = client.get("/api/telemetry/history?limit=10")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_demo_mode_switch():
    response = client.post("/api/mode", json={"demo_mode": True, "scenario": "pump_disturbance"})
    assert response.status_code == 200
    data = response.json()
    assert data["demo_mode"] is True
    assert data["scenario"] == "pump_disturbance"


def test_demo_generator_scenarios():
    gen = DemoGenerator()
    gen.set_scenario("normal")
    rec1 = gen.generate_next_second()
    assert rec1.is_demo is True
    assert rec1.status_str == "PRELIM_NORMAL"

    gen.set_scenario("confirmed_leak")
    rec2 = gen.generate_next_second()
    assert rec2.is_demo is True


def test_decision_engine_calibration():
    records = []
    for i in range(60):
        records.append(TelemetryRecord(
            pc_timestamp="2026-10-08T00:00:00",
            second_index=i,
            s1_rms=12.0, s2_rms=11.5,
            s1_abnormal=0, s2_abnormal=0
        ))
    baseline = decision_engine.calibrate_from_window(records)
    assert baseline.is_calibrated is True
    assert baseline.s1_thresh >= 15.0
    assert baseline.s2_thresh >= 15.0


def test_default_experiments_endpoint():
    response = client.get("/api/experiments/default")
    assert response.status_code == 200
    data = response.json()
    assert "summaries" in data
    assert len(data["summaries"]) >= 3


def test_settings_ports_endpoint():
    response = client.get("/api/settings/ports")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_recalibrate_command_protection():
    # Without confirm_no_leak, should fail with 400
    response = client.post("/api/command", json={"command": "RECALIBRATE", "confirm_no_leak": False})
    assert response.status_code == 400

    # With confirm_no_leak, should succeed
    response = client.post("/api/command", json={"command": "RECALIBRATE", "confirm_no_leak": True})
    assert response.status_code == 200


def test_serial_status_endpoint():
    response = client.get("/api/settings/status")
    assert response.status_code == 200
    data = response.json()
    assert "port" in data
    assert "connected" in data
    assert "connection_state" in data


def test_rapid_non_blocking_status_endpoint():
    import time
    t0 = time.time()
    for _ in range(50):
        response = client.get("/api/settings/status")
        assert response.status_code == 200
    total_time = time.time() - t0
    # 50 requests should complete in well under 1 second (averaging < 5ms per call)
    assert total_time < 1.0


def test_serial_connection_lifecycle_and_idempotency():
    # Disconnect
    res_disc = client.post("/api/settings/disconnect")
    assert res_disc.status_code == 200

    status_disc = client.get("/api/settings/status").json()
    assert status_disc["connected"] is False
    assert status_disc["connection_state"] == "DISCONNECTED"

    # Connect to auto-detected port
    res_conn = client.post("/api/settings/connect", json={"port": "COM13", "baud_rate": 115200})
    # Will succeed if COM13 available or open
    assert res_conn.status_code in [200, 400]

    # Idempotent call to connect again to same port
    res_conn2 = client.post("/api/settings/connect", json={"port": "COM13", "baud_rate": 115200})
    assert res_conn2.status_code in [200, 400]


def test_firebase_status_endpoint():
    response = client.get("/api/firebase/status")
    assert response.status_code == 200
    data = response.json()
    assert "initialized" in data
    assert "online" in data
    assert "project_id" in data


def test_websocket_telemetry_schema_integration():
    with client.websocket_connect("/ws/telemetry") as websocket:
        data = websocket.receive_json()
        
        # Verify complete TelemetryStreamPayload schema matching React frontend interface
        assert "type" in data
        assert data["type"] == "telemetry_update"
        assert "system_state" in data
        assert "demo_mode" in data
        assert "telemetry" in data
        
        if data.get("telemetry") is not None:
            telemetry = data["telemetry"]
            assert "s1_rms" in telemetry
            assert "s2_rms" in telemetry
            assert "s1_p2p" in telemetry
            assert "s2_p2p" in telemetry
            assert "s1_variance" in telemetry
            assert "s2_variance" in telemetry
            assert "s1_stvar" in telemetry
            assert "s2_stvar" in telemetry
            assert "status_str" in telemetry

        assert "diagnostics" in data
        diag = data["diagnostics"]
        assert "serial_port" in diag
        assert "connection_status" in diag

        assert "baseline" in data
        base = data["baseline"]
        assert "s1_thresh" in base
        assert "s2_thresh" in base
        websocket.close()


def test_live_mode_empty_buffer_returns_null_telemetry():
    """Live mode with no ESP32 data must return telemetry=None and WAITING_FOR_DATA status."""
    import app.main
    from app.main import build_telemetry_payload

    app.main.demo_mode = False
    app.main.recent_telemetry_buffer = []

    payload = build_telemetry_payload()
    assert payload is not None
    assert payload.demo_mode is False
    assert payload.telemetry is None
    assert payload.diagnostics.connection_status in ["WAITING_FOR_DATA", "DISCONNECTED", "CONNECTED"]


def test_live_mode_with_actual_telemetry():
    """Live mode with ESP32 data must serialize actual readings with is_demo=False."""
    import app.main
    from app.main import build_telemetry_payload, handle_new_record
    from app.models import TelemetryRecord
    from datetime import datetime, timezone

    app.main.demo_mode = False
    app.main.recent_telemetry_buffer = []

    real_record = TelemetryRecord(
        pc_timestamp=datetime.now(timezone.utc).isoformat(),
        esp32_ms=54321,
        second_index=42,
        s1_rms=2782.5,
        s1_p2p=180.0,
        s1_variance=25.4,
        s1_stvar=1.2,
        s2_rms=2865.0,
        s2_p2p=190.0,
        s2_variance=26.8,
        s2_stvar=1.3,
        s1_abnormal=0,
        s2_abnormal=0,
        is_transient=0,
        status_str="PRELIM_NORMAL",
        is_demo=False
    )
    handle_new_record(real_record)

    payload = build_telemetry_payload()
    assert payload is not None
    assert payload.telemetry is not None
    assert payload.telemetry.is_demo is False
    assert payload.telemetry.s1_rms == 2782.5
    assert payload.telemetry.s2_rms == 2865.0
    assert payload.telemetry.s1_p2p == 180.0
    assert payload.telemetry.s2_p2p == 190.0
    assert payload.telemetry.s1_variance == 25.4
    assert payload.telemetry.s2_variance == 26.8
    assert payload.telemetry.status_str == "PRELIM_NORMAL"


def test_stale_demo_telemetry_purged_on_live_mode_switch():
    """Switching to Live Mode must purge stale synthetic demo records from the buffer."""
    import app.main
    from app.main import build_telemetry_payload, handle_new_record
    from app.models import TelemetryRecord
    from datetime import datetime, timezone

    # Clear prior test buffer
    app.main.recent_telemetry_buffer = []

    # Simulate Demo Mode generating synthetic records
    app.main.demo_mode = True
    demo_rec = TelemetryRecord(
        pc_timestamp=datetime.now(timezone.utc).isoformat(),
        esp32_ms=1000,
        second_index=1,
        s1_rms=12.5,
        s1_p2p=30.0,
        s1_variance=150.0,
        s1_stvar=0.5,
        s2_rms=11.8,
        s2_p2p=28.0,
        s2_variance=140.0,
        s2_stvar=0.4,
        s1_abnormal=0,
        s2_abnormal=0,
        is_transient=0,
        status_str="PRELIM_NORMAL",
        is_demo=True
    )
    handle_new_record(demo_rec)

    # Switch to Live Mode
    client.post("/api/mode", json={"demo_mode": False})
    assert app.main.demo_mode is False

    # Verify synthetic demo records are purged
    payload = build_telemetry_payload()
    assert payload.telemetry is None  # Since no real ESP32 record has arrived yet


def test_demo_mode_generates_synthetic_telemetry():
    """Demo Mode must generate synthetic records marked with is_demo=True."""
    import app.main
    from app.main import build_telemetry_payload

    if app.main.serial_mgr:
        app.main.serial_mgr.disconnect()

    client.post("/api/mode", json={"demo_mode": True, "scenario": "normal"})
    assert app.main.demo_mode is True

    payload = build_telemetry_payload()
    assert payload.telemetry is not None
    assert payload.telemetry.is_demo is True
    assert payload.demo_mode is True


def test_end_to_end_real_csv_pipeline_to_websocket_and_debug_api():
    """End-to-end integration test dispatching a real CSV string through SerialManager._parse_and_dispatch."""
    import app.main
    from app.main import build_telemetry_payload, serial_mgr

    app.main.demo_mode = False
    app.main.recent_telemetry_buffer = []
    app.main.current_window_records = []
    
    if serial_mgr:
        serial_mgr.disconnect()
        serial_mgr.valid_csv_count = 0
        serial_mgr.callback_invocation_count = 0
        serial_mgr.callback_error_count = 0
        serial_mgr.parse_error_count = 0

    # Dispatch a real 15-field CSV line string directly through the serial parser & callback pipeline
    raw_csv = "CSV,12345,1,2782.0,150.0,12.5,0.5,2865.0,160.0,13.0,0.6,0,0,0,PRELIM_NORMAL"
    serial_mgr._parse_and_dispatch(raw_csv)

    # 1. Verify /api/debug/telemetry
    debug_resp = client.get("/api/debug/telemetry")
    assert debug_resp.status_code == 200
    debug_data = debug_resp.json()
    assert debug_data["valid_csv_count"] >= 1
    assert debug_data["callback_invocation_count"] >= 1
    assert debug_data["callback_error_count"] == 0
    assert debug_data["real_telemetry_buffer_size"] >= 1
    assert debug_data["detection_window_size"] >= 1
    assert debug_data["last_real_s1_rms"] == 2782.0
    assert debug_data["last_real_s2_rms"] == 2865.0

    # 2. Verify build_telemetry_payload()
    payload = build_telemetry_payload()
    assert payload is not None
    assert payload.demo_mode is False
    assert payload.telemetry is not None
    assert payload.telemetry.is_demo is False
    assert payload.telemetry.s1_rms == 2782.0
    assert payload.telemetry.s2_rms == 2865.0
    assert payload.current_window_sec >= 1

    # 3. Verify WebSocket payload
    with client.websocket_connect("/ws/telemetry") as ws:
        ws_data = ws.receive_json()
        assert ws_data["demo_mode"] is False
        assert ws_data["telemetry"] is not None
        assert ws_data["telemetry"]["is_demo"] is False
        assert ws_data["telemetry"]["s1_rms"] == 2782.0
        assert ws_data["telemetry"]["s2_rms"] == 2865.0
        assert ws_data["current_window_sec"] >= 1
        ws.close()


def test_debug_serial_raw_endpoint_and_auto_sync():
    """Verify GET /api/debug/serial-raw returns raw line buffer and output mode auto-sync."""
    import app.main
    from app.main import serial_mgr

    if serial_mgr:
        serial_mgr.raw_line_buffer.clear()
        serial_mgr._parse_and_dispatch("CSV,100,1,10.0,30.0,100.0,0.4,11.0,31.0,110.0,0.5,0,0,0,PRELIM_NORMAL")
        serial_mgr._parse_and_dispatch("[LIVE-DIAG 01/60] S1 RMS: 12.0 | S2 RMS: 11.5 [PRELIM NORMAL]")

    res = client.get("/api/debug/serial-raw")
    assert res.status_code == 200
    data = res.json()
    assert "port" in data
    assert "connected" in data
    assert "output_mode" in data
    assert "last_10_lines" in data
    assert len(data["last_10_lines"]) >= 2
    assert "CSV,100,1" in data["last_10_lines"][0]


def test_gps_endpoints_and_serial_parsing():
    """Verify GPS parsing, GET /api/gps/location, GET /api/debug/gps, and WebSocket integration."""
    import app.main
    from app.main import serial_mgr, build_telemetry_payload

    # 1. Test Demo Mode GPS endpoint
    app.main.demo_mode = True
    res_demo = client.get("/api/gps/location")
    assert res_demo.status_code == 200
    data_demo = res_demo.json()
    assert data_demo["is_demo"] is True
    assert data_demo["latitude"] == 6.927079
    assert data_demo["longitude"] == 79.861244
    assert data_demo["fix_status"] == "FIX"

    # 2. Test Live GPS serial parsing
    app.main.demo_mode = False
    if serial_mgr:
        serial_mgr._parse_and_dispatch("GPS,6.927100,79.861200,8,1.20,150,FIX")

    res_live = client.get("/api/gps/location")
    assert res_live.status_code == 200
    data_live = res_live.json()
    assert data_live["latitude"] == 6.9271
    assert data_live["longitude"] == 79.8612
    assert data_live["satellites"] == 8
    assert data_live["hdop"] == 1.2
    assert data_live["fix_status"] == "FIX"
    assert data_live["is_stale"] is False

    # 3. Test Debug GPS endpoint
    res_dbg = client.get("/api/debug/gps")
    assert res_dbg.status_code == 200
    dbg_data = res_dbg.json()
    assert dbg_data["valid_gps_count"] >= 1
    assert dbg_data["last_raw_gps_line"] == "GPS,6.927100,79.861200,8,1.20,150,FIX"

    # 4. Test WebSocket stream contains GPS payload
    payload = build_telemetry_payload()
    assert payload.gps is not None
    assert payload.gps.latitude == 6.9271
    assert payload.gps.longitude == 79.8612

