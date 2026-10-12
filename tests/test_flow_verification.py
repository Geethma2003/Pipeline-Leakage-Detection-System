"""
AquaGuard AI - Unit Tests for Flow-Based Leak Verification & Localization Architecture
====================================================================================
Tests the critical architectural rules:
1. ONLY the flow sensors determine whether a leak is confirmed.
2. The vibration sensors must ONLY determine the estimated leak location.
3. The website must NOT reveal an official leak location until the flow sensors confirm leakage.
4. Retain candidate vibration events from the onset of flow imbalance and associate them upon 3-window confirmation.
5. If no reliable candidate acoustic lock was found, state that location is unavailable.
6. A high TDOA correlation alone (e.g. normal pump noise) CANNOT trigger leak alarm or reveal leak position without flow confirmation.
7. Correct mathematical pulse-to-flow conversion:
   flow_lpm = (pulse_count * 60000.0) / (K * interval_ms)
"""
import pytest
import time
from fastapi.testclient import TestClient

from app.models import FlowTelemetryModel, HighResLocalizationModel, TelemetryRecord, BaselineProfileModel
from app.serial_manager import SerialManager
from app.decision_engine import DecisionEngine
from app.main import app, build_telemetry_payload


client = TestClient(app)


def compute_flow_lpm(pulses: int, k_pulses_per_liter: float, interval_ms: float) -> float:
    """Exact ESP32 firmware formula for flow rate in liters per minute."""
    if k_pulses_per_liter <= 0 or interval_ms <= 0:
        return 0.0
    return (pulses * 60000.0) / (k_pulses_per_liter * interval_ms)


def test_pulse_to_flow_conversion_known_values():
    """Verify exact mathematical pulse-to-flow conversion formula.
    
    Verifies user's exact observation:
    - 1125 pulses over 5000 ms with K=450 = 30.000 L/min (NOT 3.0 L/min).
    - 930 pulses over 5000 ms with K=450 = 24.800 L/min (NOT 2.48 L/min).
    - To produce 3.000 L/min over 5000 ms, the physical pulse count is 112.5 (112-113 pulses).
    - To produce 2.480 L/min over 5000 ms, the physical pulse count is 93.0 pulses.
    """
    k = 450.0  # pulses per liter nominal
    dt = 5000.0  # ms

    # Check user's reported numbers:
    flow_1125 = compute_flow_lpm(1125, k, dt)
    assert pytest.approx(flow_1125, rel=1e-4) == 30.000, "1125 pulses over 5s must equal 30.0 L/min"

    flow_930 = compute_flow_lpm(930, k, dt)
    assert pytest.approx(flow_930, rel=1e-4) == 24.800, "930 pulses over 5s must equal 24.8 L/min"

    # Check nominal test flow numbers (~2.5 - 3.0 L/min):
    flow_inlet_113 = compute_flow_lpm(113, k, dt)
    assert pytest.approx(flow_inlet_113, abs=0.02) == 3.013

    flow_outlet_93 = compute_flow_lpm(93, k, dt)
    assert pytest.approx(flow_outlet_93, abs=0.01) == 2.480

    diff = flow_inlet_113 - flow_outlet_93
    assert pytest.approx(diff, abs=0.02) == 0.533  # > 0.10 L/min threshold

    # Variable timing interval (e.g. FreeRTOS task jitter 4995 ms vs 5008 ms)
    flow_jitter = compute_flow_lpm(113, k, 5008.0)
    assert pytest.approx(flow_jitter, abs=0.02) == 3.008


def test_flow_telemetry_model():
    """Verify FlowTelemetryModel schema and default properties."""
    f = FlowTelemetryModel(
        esp32_ms=5000,
        interval_ms=5000,
        in_pulses=113,
        out_pulses=93,
        flow_in_lpm=3.013,
        flow_out_lpm=2.480,
        flow_diff_lpm=0.533,
        leak_progress=3,
        leak_confirmed=True,
        status="LEAK_CONFIRMED"
    )
    assert f.flow_in_lpm == 3.013
    assert f.flow_diff_lpm == 0.533
    assert f.leak_confirmed is True
    assert f.leak_progress == 3
    assert f.status == "LEAK_CONFIRMED"


def test_serial_manager_flow_parsing():
    """Verify SerialManager parses machine-readable FLOW records with exact pulse counts."""
    mgr = SerialManager()
    # Corrected pulse counts: 113 inlet pulses (~3.01 L/min), 98 outlet pulses (~2.61 L/min)
    flow_line = "FLOW,25000,5004,113,98,3.011,2.611,0.400,2,0,VERIFYING_FLOW"
    
    mgr._parse_and_dispatch(flow_line)
    assert mgr.valid_flow_count == 1
    flow_data = mgr.get_flow_status()

    assert flow_data["esp32_ms"] == 25000
    assert flow_data["interval_ms"] == 5004
    assert flow_data["in_pulses"] == 113
    assert flow_data["out_pulses"] == 98
    assert flow_data["flow_in_lpm"] == 3.011
    assert flow_data["flow_out_lpm"] == 2.611
    assert flow_data["flow_diff_lpm"] == 0.400
    assert flow_data["leak_progress"] == 2
    assert flow_data["leak_confirmed"] is False
    assert flow_data["status"] == "VERIFYING_FLOW"


def test_critical_rule_location_concealment_until_flow_confirmed():
    """CRITICAL RULE TEST: Website must NOT reveal official leak location until flow confirms leakage."""
    mgr = SerialManager()

    # 1. High-speed acoustic event occurs with strong cross-correlation (R = 0.89)
    tdoa_line = "TDOA,15000,560.2,0.890,4.50,0.65,1.35,10000,1250.0,1,LOCALIZATION_ACQUIRED"
    mgr._parse_and_dispatch(tdoa_line)

    # 2. Flow sensor reports normal operation (window 0, unconfirmed)
    normal_flow = "FLOW,15000,5000,100,99,2.667,2.640,0.027,0,0,NO_LEAK"
    mgr._parse_and_dispatch(normal_flow)

    # Invariant: Leak location MUST be concealed!
    status = mgr.get_localization_status()
    assert status["flow_confirmed_leak"] is False
    assert status["leak_location_revealed"] is False
    assert status["loc_valid"] is False
    assert status["leak_distance_s1_m"] is None
    assert status["leak_distance_s2_m"] is None
    assert "CONCEALED" in status["status"] or "AWAITING" in status["status"]

    # 3. Flow sensors now reach 3 consecutive abnormal windows and confirm leakage
    confirmed_flow = "FLOW,30000,5000,113,93,3.013,2.480,0.533,3,1,LEAK_CONFIRMED"
    mgr._parse_and_dispatch(confirmed_flow)

    # Invariant: Now leak location MUST be revealed with candidate acoustic lock!
    status_confirmed = mgr.get_localization_status()
    assert status_confirmed["flow_confirmed_leak"] is True
    assert status_confirmed["leak_location_revealed"] is True
    assert status_confirmed["loc_valid"] is True
    assert status_confirmed["leak_distance_s1_m"] == 0.65
    assert status_confirmed["leak_distance_s2_m"] == 1.35
    assert status_confirmed["correlation_peak"] == 0.890


def test_normal_pump_vibration_rejected_without_flow_confirmation():
    """CRITICAL RULE TEST: High TDOA correlation alone (e.g. coherent pump noise) CANNOT select a leak event when flow is normal."""
    mgr = SerialManager()

    # Coherent periodic pump vibration yields high cross-correlation R = 0.94
    pump_tdoa = "TDOA,10000,0.0,0.940,5.80,1.00,1.00,10000,1250.0,1,LOCALIZATION_ACQUIRED"
    mgr._parse_and_dispatch(pump_tdoa)

    # Flow sensors confirm pipeline is in balanced steady state (NO_LEAK, diff = 0.01 L/min)
    normal_flow = "FLOW,10000,5000,95,94,2.533,2.507,0.026,0,0,NO_LEAK"
    mgr._parse_and_dispatch(normal_flow)

    status = mgr.get_localization_status()
    # High correlation MUST NOT reveal a leak location when flow is balanced!
    assert status["flow_confirmed_leak"] is False
    assert status["leak_location_revealed"] is False
    assert status["loc_valid"] is False
    assert status["leak_distance_s1_m"] is None
    assert status["leak_distance_s2_m"] is None


def test_candidate_vibration_association_across_delay():
    """Test candidate acoustic buffer association when leak valve produces sudden vibration before 15s flow confirmation."""
    mgr = SerialManager()

    # Early candidate acoustic burst (at t = 5s, when valve opened)
    early_tdoa = "TDOA,5000,480.0,0.875,4.10,0.70,1.30,10000,1250.0,1,LOCALIZATION_ACQUIRED"
    mgr._parse_and_dispatch(early_tdoa)

    # Subsequent noisy / post-settling readings with lower correlation (diffuse fluid noise)
    settling_tdoa_1 = "TDOA,10000,120.0,0.420,1.50,0.92,1.08,10000,1250.0,0,INSUFFICIENT_CORRELATION"
    mgr._parse_and_dispatch(settling_tdoa_1)
    settling_tdoa_2 = "TDOA,15000,80.0,0.380,1.20,0.95,1.05,10000,1250.0,0,INSUFFICIENT_CORRELATION"
    mgr._parse_and_dispatch(settling_tdoa_2)

    # Flow sensors confirm leak after 3 consecutive 5-second windows (15 seconds total)
    confirmed_flow = "FLOW,20000,5000,115,95,3.067,2.533,0.534,3,1,LEAK_CONFIRMED"
    mgr._parse_and_dispatch(confirmed_flow)

    # The system must associate with the valid early candidate burst (R=0.875, d1=0.70m), NOT the noisy settling reading!
    loc = mgr.get_localization_status()
    assert loc["flow_confirmed_leak"] is True
    assert loc["leak_location_revealed"] is True
    assert loc["leak_distance_s1_m"] == 0.70
    assert loc["leak_distance_s2_m"] == 1.30
    assert loc["correlation_peak"] == 0.875


def test_flow_confirmed_with_no_acoustic_candidate():
    """Verify that if flow confirms leak but no reliable acoustic candidate exists, location is reported as UNAVAILABLE (never invent false coordinates)."""
    mgr = SerialManager()

    # Only low-correlation diffuse noise
    diffuse_tdoa = "TDOA,10000,0.0,0.250,1.10,1.00,1.00,10000,1250.0,0,INSUFFICIENT_CORRELATION"
    mgr._parse_and_dispatch(diffuse_tdoa)

    # Flow confirms leakage
    confirmed_flow = "FLOW,20000,5000,115,95,3.067,2.533,0.534,3,1,LEAK_CONFIRMED"
    mgr._parse_and_dispatch(confirmed_flow)

    loc = mgr.get_localization_status()
    assert loc["flow_confirmed_leak"] is True
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None
    assert "UNAVAILABLE" in loc["status"]


def test_flow_status_distinction():
    """Verify system distinguishes LOW_OR_NO_FLOW, FLOW_SENSOR_UNAVAILABLE, VERIFYING_FLOW, NO_LEAK and LEAK_CONFIRMED."""
    mgr = SerialManager()

    # 1. LOW_OR_NO_FLOW
    mgr._parse_and_dispatch("FLOW,5000,5000,10,9,0.267,0.240,0.027,0,0,LOW_OR_NO_FLOW")
    assert mgr.get_flow_status()["status"] == "LOW_OR_NO_FLOW"

    # 2. VERIFYING_FLOW (window 1 of 3)
    mgr._parse_and_dispatch("FLOW,10000,5000,113,95,3.013,2.533,0.480,1,0,VERIFYING_FLOW")
    assert mgr.get_flow_status()["status"] == "VERIFYING_FLOW"
    assert mgr.get_flow_status()["leak_progress"] == 1

    # 3. LEAK_CONFIRMED (window 3 of 3)
    mgr._parse_and_dispatch("FLOW,20000,5000,113,93,3.013,2.480,0.533,3,1,LEAK_CONFIRMED")
    assert mgr.get_flow_status()["status"] == "LEAK_CONFIRMED"
    assert mgr.get_flow_status()["leak_confirmed"] is True

    # 4. NO_LEAK (recovered normal balance)
    mgr._parse_and_dispatch("FLOW,25000,5000,100,100,2.667,2.667,0.000,0,0,NO_LEAK")
    assert mgr.get_flow_status()["status"] == "NO_LEAK"
    assert mgr.get_flow_status()["leak_confirmed"] is False

    # 5. FLOW_SENSOR_UNAVAILABLE / COMMUNICATION LOST (stale timestamp simulation)
    mgr.latest_flow_data["last_updated"] = time.time() - 20.0  # > 15s ago
    assert mgr.get_flow_status()["status"] in ["COMMUNICATION LOST", "STALE", "DATA UNAVAILABLE"]


def test_decision_engine_flow_integration():
    """Verify DecisionEngine enforces flow-only leak confirmation and conceals location when flow unconfirmed."""
    engine = DecisionEngine(persistence_req=10)
    engine.set_baseline(BaselineProfileModel(
        s1_rms_median=12.0, s1_thresh=25.0,
        s2_rms_median=12.0, s2_thresh=25.0
    ))

    # Feed 60 records with high vibration (RMS = 250 counts)
    records = []
    for i in range(60):
        records.append(TelemetryRecord(
            pc_timestamp="2026-10-10T12:00:00",
            second_index=i,
            s1_rms=250.0,
            s2_rms=15.0,
            s1_abnormal=1,
            s2_abnormal=0
        ))

    # Case A: Flow has NOT confirmed leakage
    engine.update_flow_telemetry({"leak_confirmed": False, "leak_progress": 1, "status": "VERIFYING_FLOW"})
    decision_unconfirmed = engine.evaluate_60s_window(records, 1)

    assert engine.system_state == "SUSPECTED_ANOMALY"
    assert "AWAITING" in decision_unconfirmed.decision or "SUSPECTED" in decision_unconfirmed.decision
    assert decision_unconfirmed.loc_valid is False
    assert decision_unconfirmed.estimated_distance_m is None

    # Case B: Flow sensors confirm leakage
    engine.update_flow_telemetry({"leak_confirmed": True, "leak_progress": 3, "status": "LEAK_CONFIRMED"})
    decision_confirmed = engine.evaluate_60s_window(records, 2)

    assert engine.system_state == "CONFIRMED_LEAK"
    assert "CONFIRMED" in decision_confirmed.decision


def test_rest_api_flow_endpoint():
    """Verify GET /api/serial/flow endpoint returns valid flow telemetry."""
    response = client.get("/api/serial/flow")
    assert response.status_code == 200
    data = response.json()
    assert "flow_in_lpm" in data
    assert "flow_out_lpm" in data
    assert "flow_diff_lpm" in data
    assert "leak_progress" in data
    assert "leak_confirmed" in data
    assert "status" in data


def test_build_telemetry_payload_includes_flow():
    """Verify build_telemetry_payload includes valid flow sub-object in WebSocket broadcast payload."""
    payload = build_telemetry_payload()
    assert payload.flow is not None
    assert isinstance(payload.flow.flow_in_lpm, float)
    assert isinstance(payload.flow.leak_confirmed, bool)
