"""
Unit Tests for ESP32 Serial Telemetry Data Parser
=================================================
Validates serial line parsing, legacy raw ADC warning detection, malformed line rejection,
ADC clipping/flatline warnings, and backend SerialManager integration.
"""

import pytest
import datetime
from serial_logger import parse_serial_line, CSV_HEADER
from app.serial_manager import SerialManager
from app.models import TelemetryRecord


def test_parse_valid_csv_telemetry():
    """Test 1: Valid 15-field firmware CSV telemetry is correctly parsed."""
    line = "CSV,5000,5,12.50,33.6,158.66,5.04,12.37,35.6,153.02,4.95,0,0,0,PRELIM_NORMAL"
    ts = "2026-10-09T12:00:00.000000"
    result = parse_serial_line(line, pc_ts=ts)

    assert result["status_code"] == "CSV_VALID"
    assert result["row_data"] is not None
    assert len(result["row_data"]) == 15
    assert result["row_data"][0] == ts
    assert result["row_data"][1] == "5000"
    assert result["row_data"][2] == "5"
    assert float(result["row_data"][3]) == 12.50
    assert float(result["row_data"][7]) == 12.37
    assert result["row_data"][14] == "PRELIM_NORMAL"
    assert len(result["warnings"]) == 0


def test_parse_legacy_raw_adc_lines():
    """Test 2: Legacy raw serial lines ('Sensor 1: 2782  Sensor 2: 2865') emit a warning and are NOT logged as fake RMS."""
    line = "Sensor 1: 2782    Sensor 2: 2865"
    result = parse_serial_line(line)

    assert result["status_code"] == "LEGACY_RAW"
    assert result["row_data"] is None
    assert any("legacy/unstructured firmware" in result["message"] for w in ["legacy"])
    assert len(result["warnings"]) > 0


def test_parse_truncated_csv_line():
    """Test 3: Incomplete/truncated CSV lines trigger PARSE_ERROR."""
    line = "CSV,5000,5,12.50,33.6"
    result = parse_serial_line(line)

    assert result["status_code"] == "PARSE_ERROR"
    assert result["row_data"] is None
    assert "Expected 15 CSV fields, got 5" in result["warnings"][0]


def test_parse_adc_warnings():
    """Test 4: ADC clipping and hardware fault status strings generate appropriate warnings."""
    # Test clipping warning
    clip_line = "CSV,10000,10,250.0,4095.0,2000.0,15.0,12.0,30.0,100.0,4.0,1,0,0,PRELIM_ABNORMAL"
    clip_res = parse_serial_line(clip_line)
    assert clip_res["status_code"] == "CSV_VALID"
    assert any("ADC Clipping Warning" in w for w in clip_res["warnings"])

    # Test FAULT status string warning
    fault_line = "CSV,11000,11,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0,0,0,FAULT"
    fault_res = parse_serial_line(fault_line)
    assert fault_res["status_code"] == "CSV_VALID"
    assert any("Firmware FAULT Status" in w for w in fault_res["warnings"])


def test_backend_serial_manager_dispatch():
    """Test 5: Backend SerialManager correctly dispatches TelemetryRecord to callback."""
    received_records = []

    def callback(record: TelemetryRecord):
        received_records.append(record)

    mgr = SerialManager(callback_on_record=callback)

    # Valid line dispatch
    mgr._parse_and_dispatch("CSV,2000,2,14.2,38.1,180.5,5.2,11.8,32.0,120.0,4.5,0,0,0,PRELIM_NORMAL")
    assert len(received_records) == 1
    rec = received_records[0]
    assert rec.esp32_ms == 2000
    assert rec.second_index == 2
    assert rec.s1_rms == 14.2
    assert rec.s2_rms == 11.8
    assert rec.status_str == "PRELIM_NORMAL"
    assert rec.is_demo is False

    # Legacy raw line dispatch (should NOT trigger callback)
    mgr._parse_and_dispatch("Sensor 1: 2864    Sensor 2: 3200")
    assert len(received_records) == 1


def test_firmware_diagnostics_ignored_without_parse_errors():
    """Test 6: Legitimate firmware diagnostic messages do NOT increment parse_error_count or set last_processing_error."""
    mgr = SerialManager()
    initial_errors = mgr.parse_error_count
    assert initial_errors == 0

    diagnostic_samples = [
        "[STAGE: TDOA_ACQ_START]",
        "[STAGE: TDOA_ACQ_DONE] (50000 us)",
        "[STAGE: TDOA_FILTER_START]",
        "[STAGE: TDOA_FILTER_DONE]",
        "[STAGE: TDOA_CORR_START]",
        "[STAGE: TDOA_CORR_DONE]",
        "[STAGE: RMS_CAPTURE_START]",
        "[STAGE: RMS_CAPTURE_DONE] (700000 us)",
        "[STAGE: CALIBRATION_START]",
        "[STAGE: CALIBRATION_COMPLETE]",
        "[STAGE: CALIBRATION_FAILED]",
        "[MEM-CHECK @ CALIB_START] FreeHeap: 284128 B | MinHeap: 284000 B | StackHighWater: 1840 B",
        "[MEM-CHECK @ CALIB_SEC_0_DONE] FreeHeap: 284128 B | MinHeap: 284000 B | StackHighWater: 1840 B",
        "[LIVE-DIAG 01/60] S1 RMS: 159.2 (Th: 195.0) | S2 RMS: 1616.0 (Th: 1950.0) [ADC_CLIPPING_FAULT]",
        "[CALIBRATING 01/60] S1 RMS: 159.2 P2P: 1152.0 | S2 RMS: 1616.0 P2P: 4095.0 [CLIPPED/INVALID]",
        "[COMMAND] Manual Baseline Recalibration Triggered.",
        "=================================================",
        "60-SECOND BASELINE CALIBRATION: PUMP ON, NO LEAK",
        "Ensure pipeline is operating normally without tap/leak.",
        "=================================================",
        "REJECTION BREAKDOWN:",
        "  - Sensor 1 ADC Clipping (>5% clipped): 0/60 seconds",
        "  - Sensor 2 ADC Clipping (>5% clipped): 60/60 seconds",
        "  - Sample Timing Overruns (>2% late):   0/60 seconds",
        "Latest ADC Range: S1 [1472..2624] (Clips: 0) | S2 [0..4095] (Clips: 2000)",
        "HARDWARE DIAGNOSTIC ADVICE:",
        "  1. Check 100k/100k voltage divider creating ~1.65V DC bias at GPIO 34 & 35.",
        "  2. Check 0.1uF AC coupling capacitor & 1M resistor across piezo element.",
        "  3. Check BAT54S dual Schottky clamping diodes to 3.3V and GND.",
        "Send 'B' command after correcting hardware to retry baseline calibration.",
        "Guru Meditation Error: Core 1 panic'ed (Unhandled debug exception).",
        "Debug exception reason: Stack canary watchpoint triggered (loopTask)",
    ]

    for diag_line in diagnostic_samples:
        mgr._parse_and_dispatch(diag_line)

    assert mgr.parse_error_count == 0, f"Expected 0 parse errors, got {mgr.parse_error_count}"
    assert mgr.last_processing_error is None, f"Expected None processing error, got {mgr.last_processing_error}"
    assert mgr.last_diagnostic_line is not None
    assert len(mgr.get_diagnostic_messages()) == len(diagnostic_samples)


def test_raw_adc_telemetry_parsing():
    """Test 7: ADC telemetry line exposes min/max, mean, rail-hit counts, and clipping percentage for GPIO34 and GPIO35."""
    mgr = SerialManager()

    # Normal / healthy ADC line
    normal_adc_line = "ADC,10500,1500,2600,2048.2,0,0.00,1490,2610,2046.8,0,0.00"
    mgr._parse_and_dispatch(normal_adc_line)

    diag = mgr.get_adc_diagnostics()
    assert mgr.parse_error_count == 0
    assert diag["s1_min"] == 1500
    assert diag["s1_max"] == 2600
    assert diag["s1_mean"] == 2048.2
    assert diag["s1_clips"] == 0
    assert diag["s1_clip_pct"] == 0.00
    assert diag["s2_min"] == 1490
    assert diag["s2_max"] == 2610
    assert diag["s2_mean"] == 2046.8
    assert diag["s2_clips"] == 0
    assert diag["s2_clip_pct"] == 0.00
    assert diag["is_clipping"] is False
    assert diag["status"] == "OK"

    # Clipped ADC line (simulating Sensor 2 physical saturation at GPIO35: P2P=4095, RMS=1616)
    clipped_adc_line = "ADC,61856,1472,2624,2048.5,0,0.00,0,4095,3950.0,2000,100.00"
    mgr._parse_and_dispatch(clipped_adc_line)

    diag_clipped = mgr.get_adc_diagnostics()
    assert mgr.parse_error_count == 0
    assert diag_clipped["s1_clips"] == 0
    assert diag_clipped["s2_min"] == 0
    assert diag_clipped["s2_max"] == 4095
    assert diag_clipped["s2_mean"] == 3950.0
    assert diag_clipped["s2_clips"] == 2000
    assert diag_clipped["s2_clip_pct"] == 100.00
    assert diag_clipped["is_clipping"] is True
    assert diag_clipped["status"] == "ADC_CLIPPING_FAULT"


def test_serial_parser_preserves_all_telemetry_types():
    """Test 8: Ensure parser seamlessly interleaves CSV, TDOA, WAVE, GPS, ADC, and diagnostic lines."""
    records = []
    mgr = SerialManager(callback_on_record=lambda r: records.append(r))

    lines = [
        "[STAGE: TDOA_ACQ_START]",
        "[STAGE: TDOA_ACQ_DONE] (50000 us)",
        "CSV,10000,10,159.2,1152.0,25344.6,12.3,1616.0,4095.0,2611456.0,15.1,0,1,0,ADC_CLIPPING_FAULT",
        "TDOA,10000,0.0,0.120,1.10,1.00,1.00,10004,1250.0,0,ADC_CLIPPING_FAULT",
        "WAVE," + ",".join(["10"] * 50) + ";" + ",".join(["2048"] * 50),
        "ADC,10000,1472,2624,2048.0,0,0.00,0,4095,4095.0,2000,100.00",
        "GPS,6.927079,79.861244,9,0.90,120,FIX",
        "[LIVE-DIAG 10/60] S1 RMS: 159.2 | S2 RMS: 1616.0 [ADC_CLIPPING_FAULT]"
    ]

    for line in lines:
        mgr._parse_and_dispatch(line)

    assert mgr.parse_error_count == 0, f"Expected 0 parse errors, got {mgr.parse_error_count}"
    assert len(records) == 1
    assert records[0].status_str == "ADC_CLIPPING_FAULT"
    assert mgr.valid_csv_count == 1
    assert mgr.valid_gps_count == 1
    assert mgr.latest_localization_data["status"] == "LOCATION UNAVAILABLE — INSUFFICIENT SIGNAL QUALITY"
    assert mgr.latest_adc_diagnostics["status"] == "ADC_CLIPPING_FAULT"

