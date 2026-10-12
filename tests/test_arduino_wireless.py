"""
Comprehensive Unit & Integration Tests for Arduino Uno nRF24L01 Wireless Telemetry
===================================================================================
Tests:
- RF24_V1 fixed-point decoding
- Leak alarm flag interpretation
- GPS no-fix and valid fix handling
- Vibration clipping and signal validity bitmasks
- Packet sequence rollover and transmitter restart
- Serial staleness and communication loss (>5s)
- Prevention of false vibration-based leak localization ("LOCATION UNAVAILABLE")
- Fallback human-readable text receiver parsing
- SQLite storage in wireless_telemetry_records & leak transition event history
- FastAPI endpoints (/api/wireless/latest, /api/wireless/history, /api/debug/telemetry)
"""

import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.serial_manager import SerialManager, auto_detect_serial_port
from app.database import (
    init_db, save_wireless_record, get_latest_wireless_record,
    get_wireless_history, record_leak_transition, get_db_connection
)
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_rf24_fixed_point_decoding():
    """Verify exact fixed-point conversion of flow, RMS, P2P, and GPS fields."""
    mgr = SerialManager()
    # RF24_V1,node_id,sequence,flags,lat_e7,lng_e7,satellites,hdop_x10,year_2000,month,day,hour,minute,second,flow_in_x100,flow_out_x100,rms1_x10,rms2_x10,p2p1,p2p2,missed_since_last,sequence_reset
    line = "RF24_V1,1,19,8,0,0,0,255,0,0,0,0,0,0,1792,1475,6,6,4,4,0,0"
    mgr._parse_and_dispatch(line)

    w = mgr.latest_wireless_data
    assert w is not None
    assert w["node_id"] == 1
    assert w["packet_sequence"] == 19
    assert w["flow_in_lpm"] == 17.92
    assert w["flow_out_lpm"] == 14.75
    assert w["flow_diff_lpm"] == 3.17
    assert w["leak_alarm"] is True
    assert w["rms1"] == 0.6  # 10-bit Arduino ADC counts
    assert w["rms2"] == 0.6
    assert w["p2p1"] == 4
    assert w["p2p2"] == 4
    assert w["communication_source"] == "ARDUINO_UNO_NRF24"


def test_leak_alarm_flag_interpretation():
    """Verify leak alarm flag (bit 3 = 0x08) and status string determination."""
    mgr = SerialManager()
    
    # Leak Alarm = 1 (bit 3 set)
    mgr._parse_and_dispatch("RF24_V1,1,20,8,0,0,0,255,0,0,0,0,0,0,1500,1200,10,10,5,5,0,0")
    assert mgr.latest_wireless_data["leak_alarm"] is True
    assert mgr.latest_wireless_data["status_str"] == "LEAK_CONFIRMED"

    # Leak Alarm = 0, normal flow (bit 3 clear, diff < 0.10)
    mgr._parse_and_dispatch("RF24_V1,1,21,0,0,0,0,255,0,0,0,0,0,0,1500,1500,10,10,5,5,0,0")
    assert mgr.latest_wireless_data["leak_alarm"] is False
    assert mgr.latest_wireless_data["status_str"] == "NO_LEAK"


def test_low_or_no_flow_handling():
    """Verify LOW_OR_NO_FLOW indication when inlet flow is below 0.50 L/min."""
    mgr = SerialManager()
    # Inlet flow = 0.35 L/min (< 0.50 L/min floor)
    mgr._parse_and_dispatch("RF24_V1,1,22,0,0,0,0,255,0,0,0,0,0,0,35,0,5,5,2,2,0,0")
    assert mgr.latest_wireless_data["flow_in_lpm"] == 0.35
    assert mgr.latest_wireless_data["status_str"] == "LOW_OR_NO_FLOW"


def test_gps_valid_and_no_fix_handling():
    """Verify GPS coordinate decoding when fix exists and NO FIX when valid bit is clear."""
    mgr = SerialManager()

    # NO FIX (flags = 0, coords = 0)
    mgr._parse_and_dispatch("RF24_V1,1,23,0,0,0,0,255,0,0,0,0,0,0,1000,1000,5,5,2,2,0,0")
    assert mgr.latest_wireless_data["gps_valid"] is False
    assert mgr.latest_wireless_data["latitude"] is None
    assert mgr.latest_wireless_data["longitude"] is None
    assert mgr.latest_gps_data["fix_status"] == "NO_FIX"

    # VALID FIX (flags = 1, lat = 6.9270790, lng = 79.8612440, sats = 8, hdop = 1.2)
    # lat_e7 = 69270790, lng_e7 = 798612440, sats = 8, hdop_x10 = 12
    mgr._parse_and_dispatch("RF24_V1,1,24,1,69270790,798612440,8,12,26,10,10,12,30,0,1200,1200,5,5,2,2,0,0")
    assert mgr.latest_wireless_data["gps_valid"] is True
    assert mgr.latest_wireless_data["latitude"] == 6.927079
    assert mgr.latest_wireless_data["longitude"] == 79.861244
    assert mgr.latest_wireless_data["satellites"] == 8
    assert mgr.latest_wireless_data["hdop"] == 1.2
    assert mgr.latest_gps_data["fix_status"] == "FIX"


def test_vibration_clipping_and_validity_flags():
    """Verify vibration clipping and window validity bitmasks (bits 1, 2, 4)."""
    mgr = SerialManager()
    # flags = 0x02 (S1 clipped) + 0x04 (S2 clipped) + 0x10 (vibration invalid) = 2 + 4 + 16 = 22
    mgr._parse_and_dispatch("RF24_V1,1,25,22,0,0,0,255,0,0,0,0,0,0,1500,1500,800,850,1023,1023,0,0")
    w = mgr.latest_wireless_data
    assert w["s1_clipped"] is True
    assert w["s2_clipped"] is True
    assert w["vibration_invalid"] is True
    assert mgr.latest_adc_diagnostics["is_clipping"] is True


def test_packet_sequence_and_transmitter_restart():
    """Verify sequence counting, missed packet tracking, and sequence resets."""
    mgr = SerialManager()
    # Packet 10, missed 2, sequence_reset = 0
    mgr._parse_and_dispatch("RF24_V1,1,10,0,0,0,0,255,0,0,0,0,0,0,1000,1000,5,5,2,2,2,0")
    assert mgr.last_packet_sequence == 10
    assert mgr.total_missed_packets == 2

    # Transmitter restart: sequence resets to 1, sequence_reset flag = 1
    mgr._parse_and_dispatch("RF24_V1,1,1,0,0,0,0,255,0,0,0,0,0,0,1000,1000,5,5,2,2,0,1")
    assert mgr.last_packet_sequence == 1
    assert mgr.sequence_reset_count == 1


def test_data_freshness_and_staleness_detection():
    """Verify COMMUNICATION_LOST status when wireless packet is older than 5.0 seconds."""
    mgr = SerialManager()
    mgr._parse_and_dispatch("RF24_V1,1,30,8,0,0,0,255,0,0,0,0,0,0,1600,1200,6,6,4,4,0,0")
    
    # Immediately: active
    fresh = mgr.get_wireless_status()
    assert fresh["status_str"] == "LEAK_CONFIRMED"

    # Simulate 6 seconds passing without new packets
    with mgr.lock:
        mgr.latest_wireless_data["last_updated"] = time.time() - 6.0
        mgr.latest_flow_data["last_updated"] = time.time() - 6.0

    stale_w = mgr.get_wireless_status()
    stale_flow = mgr.get_flow_status()
    assert stale_w["status_str"] == "COMMUNICATION_LOST"
    assert stale_flow["status"] == "COMMUNICATION LOST"


def test_prevention_of_false_leak_location_display():
    """CRITICAL RULE: Arduino Uno nRF24 telemetry must NEVER reveal fabricated leak location."""
    mgr = SerialManager()
    # Even if leak is confirmed by flow
    mgr._parse_and_dispatch("RF24_V1,1,35,8,0,0,0,255,0,0,0,0,0,0,1800,1200,6,6,4,4,0,0")
    
    loc = mgr.get_localization_status()
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None
    assert "LOCATION UNAVAILABLE" in loc["status"]


def test_human_readable_receiver_text_fallback():
    """Verify fallback parser handles multi-line human-readable receiver text."""
    mgr = SerialManager()
    lines = [
        "Packet #1  (Node 1, Seq 19, missed since last: 0, total missed: 0)",
        "GPS Fix    : NO (searching for satellites...)",
        "Satellites : 0",
        "HDOP       : --",
        "Flow inlet : 17.92 L/min",
        "Flow outlet: 14.75 L/min",
        "Leak alarm : yes",
        "Piezo 1    : RMS 0.6  P2P 4",
        "Piezo 2    : RMS 0.6  P2P 4"
    ]
    for l in lines:
        mgr._parse_and_dispatch(l)

    w = mgr.latest_wireless_data
    assert w is not None
    assert w["communication_source"] == "ARDUINO_UNO_NRF24"
    assert w["flow_in_lpm"] == 17.92
    assert w["flow_out_lpm"] == 14.75
    assert w["flow_diff_lpm"] == 3.17
    assert w["leak_alarm"] is True
    assert w["rms1"] == 0.6
    assert w["rms2"] == 0.6
    assert w["status_str"] == "LEAK_CONFIRMED"


def test_sqlite_storage_and_history():
    """Verify persistence into wireless_telemetry_records and leak transition events."""
    test_record = {
        "utc_timestamp": "2026-10-10T15:00:00.000Z",
        "node_id": 1,
        "packet_sequence": 99,
        "flow_in_lpm": 16.50,
        "flow_out_lpm": 14.10,
        "flow_diff_lpm": 2.40,
        "leak_alarm": True,
        "rms1": 0.8,
        "p2p1": 5,
        "rms2": 0.7,
        "p2p2": 4,
        "s1_clipped": False,
        "s2_clipped": False,
        "vibration_invalid": False,
        "gps_valid": True,
        "latitude": 6.927079,
        "longitude": 79.861244,
        "satellites": 7,
        "hdop": 1.1,
        "gps_time": "2026-10-10T15:00:00Z",
        "missed_packets": 0,
        "sequence_reset": 0,
        "communication_source": "ARDUINO_UNO_NRF24",
        "is_demo": False
    }

    row_id = save_wireless_record(test_record)
    assert row_id > 0

    latest = get_latest_wireless_record()
    assert latest is not None
    assert latest["packet_sequence"] == 99
    assert latest["flow_in_lpm"] == 16.50
    assert latest["leak_alarm"] == 1

    history = get_wireless_history(limit=5)
    assert len(history) >= 1
    assert any(h["packet_sequence"] == 99 for h in history)

    # Test leak transition recording in events table
    record_leak_transition("LEAK_CONFIRMED", test_record)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1")
    event = c.fetchone()
    conn.close()
    assert event is not None
    assert "CONFIRMED LEAK (WIRELESS FLOW ALARM)" in event["status"]


def test_fastapi_wireless_endpoints():
    """Verify /api/wireless/latest, /api/wireless/history, and /api/debug/telemetry."""
    client = TestClient(app)

    # Test wireless latest endpoint
    res = client.get("/api/wireless/latest")
    assert res.status_code == 200
    data = res.json()
    assert "flow_in_lpm" in data or "flow_in_x100" in data or "communication_source" in data

    # Test wireless history endpoint
    res_hist = client.get("/api/wireless/history?limit=10")
    assert res_hist.status_code == 200
    assert isinstance(res_hist.json(), list)

    # Test debug telemetry endpoint
    res_dbg = client.get("/api/debug/telemetry")
    assert res_dbg.status_code == 200
    dbg = res_dbg.json()
    assert "radio_diagnostic" in dbg
    assert "flow_readings" in dbg
    assert dbg["communication_source"] == "ARDUINO_UNO_NRF24"


def test_real_arduino_serial_log_parsing():
    """Verify parser on actual hardware log lines from D:/pipeline/backend/arduino_serial.log.
    Must parse exactly 5 complete packets (103, 104, 105, 106, 107) and match exact sensor readings.
    """
    import os
    import re
    log_file = os.path.join(os.path.dirname(__file__), "..", "backend", "arduino_serial.log")
    assert os.path.exists(log_file), f"Log file {log_file} does not exist"

    mgr = SerialManager()
    with open(log_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            # Strip log timestamps like "[22:19:28.164] "
            clean_line = re.sub(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]\s*", "", raw_line.strip())
            if clean_line:
                mgr._parse_and_dispatch(clean_line)

    # Verify exactly 5 complete packets were received and validated
    assert mgr.valid_rf24_count == 5
    assert mgr.last_packet_sequence == 107

    # Verify latest packet sensor readings match the physical log exactly
    w = mgr.latest_wireless_data
    assert w is not None
    assert w["node_id"] == 1
    assert w["packet_sequence"] == 107
    assert w["flow_in_lpm"] == 0.00
    assert w["flow_out_lpm"] == 0.00
    assert w["flow_diff_lpm"] == 0.00
    assert w["leak_alarm"] is False
    assert w["rms1"] == 16.0
    assert w["p2p1"] == 89
    assert w["rms2"] == 143.3
    assert w["p2p2"] == 791
    assert w["gps_valid"] is False
    assert w["latitude"] is None
    assert w["longitude"] is None
    assert w["status_str"] == "LOW_OR_NO_FLOW"

    # Verify localization is strictly unavailable
    loc = mgr.get_localization_status()
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert "LOCATION UNAVAILABLE" in loc["status"]

