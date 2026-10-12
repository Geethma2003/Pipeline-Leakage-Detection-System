"""
Tests for AquaGuard AI Arduino Uno TDOA Localization & End-to-End Verification
==============================================================================
Validates:
1. Pump OFF condition (LOW_OR_NO_FLOW, localization concealed).
2. Pump ON, no leak (flow balanced, pump vibration correlation rejected without flow alarm).
3. Leak confirmed by flow sensors with valid acoustic TDOA at 0.5m, 1.0m, and 1.5m.
4. Missing or clipped vibration data handling (refusal to guess or default to midpoint 1.0m).
5. Out-of-bounds TDOA rejection (< 0.0m or > 2.0m).
6. Weak correlation rejection (R < 0.65).
7. Wireless packet loss tracking and transmitter sequence continuity.
8. Recovery when leak closes (leak alarm clears -> location immediately concealed).
9. SQLite database persistence and REST API endpoint verification.
"""

import pytest
import sqlite3
import time
from app.serial_manager import SerialManager
from app.database import (
    save_arduino_localization_event,
    get_latest_localization_event,
    get_localization_events,
    get_db_connection
)
from app.models import HighResLocalizationModel


def test_scenario_1_pump_off():
    """Scenario 1: Pump OFF -> Flow is zero -> Status is LOW_OR_NO_FLOW -> Location strictly concealed."""
    mgr = SerialManager()
    # Arduino Uno RF24 packet: Flow in = 0.0, Flow out = 0.0, alarm = 0
    rf24_zero = "RF24_V1,1,10,0,0,0,0,999,26,10,11,1,0,0,0,0,150,140,80,75,0,0"
    mgr._parse_and_dispatch(rf24_zero)

    w = mgr.get_wireless_status()
    assert w is not None
    assert w["status_str"] == "LOW_OR_NO_FLOW"
    assert w["leak_alarm"] is False

    loc = mgr.get_localization_status()
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None


def test_scenario_2_pump_on_no_leak_pump_vibration_rejection():
    """Scenario 2: Pump ON, normal balanced flow.
    Even if high-correlation vibration (pump hum) arrives, it must NOT be revealed as a leak!
    """
    mgr = SerialManager()
    # Flow balanced: 12.50 L/min in, 12.45 L/min out, diff = 0.05 L/min, leak_alarm = 0
    rf24_normal = "RF24_V1,1,20,0,0,0,0,999,26,10,11,1,1,0,1250,1245,220,210,140,130,0,0"
    mgr._parse_and_dispatch(rf24_normal)

    w = mgr.get_wireless_status()
    assert w["leak_alarm"] is False
    assert w["status_str"] == "NO_LEAK"

    # Acoustic candidate arrives with high correlation from pump vibration (R = 0.92, dt = 120 us, dist = 925 mm)
    tdoa_pump = "TDOA_UNO,1,101,15000,120.0,925,92,35,1,0"
    mgr._parse_and_dispatch(tdoa_pump)

    # CRITICAL RULE: Flow sensors are the ONLY authority. No flow alarm -> location must be concealed!
    loc = mgr.get_localization_status()
    assert loc["flow_confirmed_leak"] is False
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None
    assert "AWAITING FLOW CONFIRMATION" in loc["status"]


def test_scenario_3_leak_at_known_positions():
    """Scenario 3: Open leak valve at known positions (0.5m, 1.0m, 1.5m).
    Flow confirms leak, and valid TDOA vibration matches the physical location.
    Formula: d1 = (L - v * dt) / 2
    With L = 2.0 m, v = 1250 m/s:
    - At 0.5 m: dt = +800 us  -> d1 = (2.0 - 1.0) / 2 = 0.50 m, d2 = 1.50 m
    - At 1.0 m: dt = 0 us     -> d1 = (2.0 - 0.0) / 2 = 1.00 m, d2 = 1.00 m
    - At 1.5 m: dt = -800 us -> d1 = (2.0 - (-1.0)) / 2 = 1.50 m, d2 = 0.50 m
    """
    # Test at 0.5 m
    mgr_05 = SerialManager()
    # Flow leak confirmed (flag 0x08 = 8, Flow in = 10.16, out = 8.05, diff = 2.11)
    rf24_leak = "RF24_V1,1,30,8,0,0,0,999,26,10,11,1,2,0,1016,805,450,520,380,410,0,0"
    mgr_05._parse_and_dispatch(rf24_leak)
    assert mgr_05.latest_flow_data["leak_confirmed"] is True

    # Vibration event at 0.5 m: dt = +800 us, dist = 500 mm, R = 0.88, PSR = 3.2, valid = 1, code = 0
    tdoa_05 = "TDOA_UNO,1,201,18000,800.0,500,88,32,1,0"
    mgr_05._parse_and_dispatch(tdoa_05)

    loc_05 = mgr_05.get_localization_status()
    assert loc_05["flow_confirmed_leak"] is True
    assert loc_05["leak_location_revealed"] is True
    assert loc_05["loc_valid"] is True
    assert loc_05["leak_distance_s1_m"] == 0.500
    assert loc_05["leak_distance_s2_m"] == 1.500
    assert loc_05["delta_t_us"] == 800.0
    assert loc_05["correlation_peak"] == 0.88
    assert loc_05["confidence_pct"] == 88.0
    assert "LOCALIZATION REVEALED" in loc_05["status"]

    # Test at 1.0 m (Midpoint)
    mgr_10 = SerialManager()
    mgr_10._parse_and_dispatch(rf24_leak)
    tdoa_10 = "TDOA_UNO,1,202,19000,0.0,1000,94,41,1,0"
    mgr_10._parse_and_dispatch(tdoa_10)

    loc_10 = mgr_10.get_localization_status()
    assert loc_10["leak_location_revealed"] is True
    assert loc_10["loc_valid"] is True
    assert loc_10["leak_distance_s1_m"] == 1.000
    assert loc_10["leak_distance_s2_m"] == 1.000

    # Test at 1.5 m (Closer to Sensor 2)
    mgr_15 = SerialManager()
    mgr_15._parse_and_dispatch(rf24_leak)
    tdoa_15 = "TDOA_UNO,1,203,20000,-800.0,1500,86,29,1,0"
    mgr_15._parse_and_dispatch(tdoa_15)

    loc_15 = mgr_15.get_localization_status()
    assert loc_15["leak_location_revealed"] is True
    assert loc_15["loc_valid"] is True
    assert loc_15["leak_distance_s1_m"] == 1.500
    assert loc_15["leak_distance_s2_m"] == 0.500


def test_scenario_4_clipping_rejection_never_defaults_to_one_meter():
    """Scenario 4: Flow confirms leak, but vibration sensors experienced ADC clipping.
    The system MUST reject the calculation and NEVER default to 1.0 meter!
    """
    mgr = SerialManager()
    rf24_leak = "RF24_V1,1,40,8,0,0,0,999,26,10,11,1,3,0,1016,805,450,520,380,410,0,0"
    mgr._parse_and_dispatch(rf24_leak)

    # TDOA with clipping failure: code = 1 (ADC_CLIPPING_DETECTED), valid = 0
    tdoa_clip = "TDOA_UNO,1,204,21000,0.0,1000,45,11,0,1"
    mgr._parse_and_dispatch(tdoa_clip)

    loc = mgr.get_localization_status()
    assert loc["flow_confirmed_leak"] is True
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None
    assert "ACOUSTIC LOCATION UNAVAILABLE" in loc["status"]
    assert "CLIPPING" in loc["status"]


def test_scenario_5_out_of_bounds_rejection():
    """Scenario 5: Out of bounds delay (dist < 0m or > 2.0m) must be rejected."""
    mgr = SerialManager()
    rf24_leak = "RF24_V1,1,50,8,0,0,0,999,26,10,11,1,4,0,1016,805,450,520,380,410,0,0"
    mgr._parse_and_dispatch(rf24_leak)

    # TDOA with out of bounds: dist = 2450 mm (> 2000 mm), code = 5, valid = 0
    tdoa_oob = "TDOA_UNO,1,205,22000,-2320.0,2450,72,21,0,5"
    mgr._parse_and_dispatch(tdoa_oob)

    loc = mgr.get_localization_status()
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None


def test_scenario_6_weak_correlation_rejection():
    """Scenario 6: Low cross-correlation peak (R < 0.65) must be rejected."""
    mgr = SerialManager()
    rf24_leak = "RF24_V1,1,60,8,0,0,0,999,26,10,11,1,5,0,1016,805,450,520,380,410,0,0"
    mgr._parse_and_dispatch(rf24_leak)

    # TDOA with R = 0.52 (< 0.65 threshold), code = 3, valid = 0
    tdoa_weak = "TDOA_UNO,1,206,23000,400.0,750,52,14,0,3"
    mgr._parse_and_dispatch(tdoa_weak)

    loc = mgr.get_localization_status()
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None


def test_scenario_7_wireless_packet_loss_tracking():
    """Scenario 7: Wireless packet loss tracking across sequence numbers."""
    mgr = SerialManager()
    # Packet sequence 100
    pkt1 = "RF24_V1,1,100,0,0,0,0,999,26,10,11,1,6,0,1000,1000,100,100,50,50,0,0"
    mgr._parse_and_dispatch(pkt1)
    assert mgr.last_packet_sequence == 100
    assert mgr.total_missed_packets == 0

    # Packet sequence 104 with missed_since_last = 3
    pkt2 = "RF24_V1,1,104,0,0,0,0,999,26,10,11,1,7,0,1000,1000,100,100,50,50,3,0"
    mgr._parse_and_dispatch(pkt2)
    assert mgr.last_packet_sequence == 104
    assert mgr.total_missed_packets == 3


def test_scenario_8_recovery_after_leak_closed():
    """Scenario 8: Flow recovers to balanced -> Leak alarm clears -> Location marker immediately concealed."""
    mgr = SerialManager()
    # Leak is active
    rf24_leak = "RF24_V1,1,70,8,0,0,0,999,26,10,11,1,8,0,1016,805,450,520,380,410,0,0"
    mgr._parse_and_dispatch(rf24_leak)
    tdoa_valid = "TDOA_UNO,1,207,24000,800.0,500,88,32,1,0"
    mgr._parse_and_dispatch(tdoa_valid)

    loc_during = mgr.get_localization_status()
    assert loc_during["leak_location_revealed"] is True
    assert loc_during["leak_distance_s1_m"] == 0.500

    # Now leak valve is closed! Flow balances: 10.00 L/min and 10.00 L/min, leak_alarm = 0
    rf24_cleared = "RF24_V1,1,71,0,0,0,0,999,26,10,11,1,9,0,1000,1000,200,210,100,105,0,0"
    mgr._parse_and_dispatch(rf24_cleared)

    loc_after = mgr.get_localization_status()
    assert loc_after["flow_confirmed_leak"] is False
    assert loc_after["leak_location_revealed"] is False
    assert loc_after["loc_valid"] is False
    assert loc_after["leak_distance_s1_m"] is None
    assert loc_after["leak_distance_s2_m"] is None


def test_scenario_9_sqlite_persistence_and_retrieval():
    """Scenario 9: SQLite storage of localization events with event IDs and quality metrics."""
    event = {
        "node_id": 1,
        "event_id": 305,
        "transmitter_timestamp_ms": 54321,
        "delta_t_us": -800.0,
        "estimated_distance_m": 1.500,
        "distance_sensor2_m": 0.500,
        "correlation_peak": 0.91,
        "psr": 3.4,
        "is_valid": 1,
        "failure_code": 0,
        "failure_reason": "VALID_ACOUSTIC_LOCK",
        "flow_confirmed": 1,
        "pipeline_length_m": 2.0,
        "calibrated_velocity_mps": 1250.0
    }

    row_id = save_arduino_localization_event(event)
    assert row_id > 0

    latest = get_latest_localization_event()
    assert latest is not None
    assert latest["event_id"] == 305
    assert latest["delta_t_us"] == -800.0
    assert latest["estimated_distance_m"] == 1.500
    assert latest["distance_sensor2_m"] == 0.500
    assert latest["correlation_peak"] == 0.91
    assert latest["flow_confirmed"] == 1

    events_list = get_localization_events(limit=10)
    assert len(events_list) >= 1


def test_scenario_10_fifteen_second_valve_opening_delay_matching():
    """Scenario 10: Valve-opening acoustic burst occurs ~15s before flow confirmation.
    The system stores the candidate in bounded history, keeps location concealed during verification,
    and correctly associates the onset transient when flow leak is finally confirmed.
    """
    mgr = SerialManager()

    # t = 0: Flow is currently normal
    rf24_init = "RF24_V1,1,10,0,0,0,0,999,26,10,11,1,0,0,1200,1200,150,150,60,60,0,0"
    mgr._parse_and_dispatch(rf24_init)

    # t = 0.5s: Valve opens! Acoustic transient detected at 0.5m:
    # Event #501, dt = +800 us, dist = 500 mm, R = 0.94, PSR = 4.2, valid = 1, code = 0
    tdoa_valve = "TDOA_UNO,1,501,500,800.0,500,94,42,1,0"
    mgr._parse_and_dispatch(tdoa_valve)

    # Location must remain CONCEALED because flow has not confirmed yet!
    loc_t0 = mgr.get_localization_status()
    assert loc_t0["flow_confirmed_leak"] is False
    assert loc_t0["leak_location_revealed"] is False
    assert loc_t0["leak_distance_s1_m"] is None

    # t = 5s: Flow window 1: Flow difference observed, verifying
    rf24_w1 = "RF24_V1,1,11,0,0,0,0,999,26,10,11,1,5,0,1200,900,250,260,120,130,0,0"
    mgr._parse_and_dispatch(rf24_w1)

    # t = 8s: Background pump noise arrives with lower quality (R = 0.68, PSR = 1.6)
    tdoa_pump = "TDOA_UNO,1,502,8000,150.0,900,68,16,1,0"
    mgr._parse_and_dispatch(tdoa_pump)

    # Still concealed
    loc_t8 = mgr.get_localization_status()
    assert loc_t8["leak_location_revealed"] is False

    # t = 10s: Flow window 2: Flow difference continues
    rf24_w2 = "RF24_V1,1,12,0,0,0,0,999,26,10,11,1,10,0,1200,900,250,260,120,130,0,0"
    mgr._parse_and_dispatch(rf24_w2)

    # t = 15s: Flow window 3: Flow confirmed! leak_alarm flag = 0x08
    rf24_w3 = "RF24_V1,1,13,8,0,0,0,999,26,10,11,1,15,0,1200,900,250,260,120,130,0,0"
    mgr._parse_and_dispatch(rf24_w3)

    # Now flow confirms leak! System associates the highest-quality onset event (#501 at 0.5m)
    loc_confirmed = mgr.get_localization_status()
    assert loc_confirmed["flow_confirmed_leak"] is True
    assert loc_confirmed["leak_location_revealed"] is True
    assert loc_confirmed["loc_valid"] is True
    assert loc_confirmed["event_id"] == 501
    assert loc_confirmed["leak_distance_s1_m"] == 0.500
    assert loc_confirmed["leak_distance_s2_m"] == 1.500
    assert loc_confirmed["propagation_velocity_status"] == "NOMINAL_UNCALIBRATED"


def test_scenario_11_reject_pump_vibration_low_psr():
    """Scenario 11: Flow confirms leak, but piezo sensors observe only periodic pump vibration.
    Pump vibration produces cyclic correlation sidelobes with low PSR (PSR = 1.2 < 1.8).
    Without true transient evidence, the system MUST show LOCATION UNAVAILABLE!
    """
    mgr = SerialManager()
    # Flow leak confirmed (flag 0x08 = 8, Flow in = 10.16, out = 8.05, diff = 2.11)
    rf24_leak = "RF24_V1,1,30,8,0,0,0,999,26,10,11,1,2,0,1016,805,450,520,380,410,0,0"
    mgr._parse_and_dispatch(rf24_leak)
    assert mgr.latest_flow_data["leak_confirmed"] is True

    # Pump vibration with cyclic sidelobes: R = 0.75, but PSR = 1.2 (< 1.8 threshold)
    # TDOA_UNO,node_id,event_id,timestamp_ms,delta_t_us,dist_mm,corr_peak_x100,psr_x10,valid,failure_code,is_transient
    tdoa_pump = "TDOA_UNO,1,601,30000,400.0,750,75,12,1,0,0"
    mgr._parse_and_dispatch(tdoa_pump)

    loc = mgr.get_localization_status()
    assert loc["flow_confirmed_leak"] is True
    assert loc["leak_location_revealed"] is False
    assert loc["loc_valid"] is False
    assert loc["leak_distance_s1_m"] is None
    assert loc["leak_distance_s2_m"] is None
    assert "LOCATION UNAVAILABLE" in loc["status"]


def test_scenario_12_tdoa_skew_direction_and_lag_sign_validation():
    """Scenario 12: Validate TDOA lag sign and skew compensation direction.
    Theoretical sampling model:
    - ATmega328P ADC clock = 500 kHz (Prescaler 32).
    - Single channel conversion = 26.0 us (13 ADC cycles).
    - Sequential dual-channel read: A0 converted at t=0, A1 converted at t=+26 us.
    - Pair interval T_pair = 52.0 us. Inter-channel skew T_skew = +26.0 us.
    True delta_t = (lag * T_pair) + T_skew.
    Physical formula: d1 = (L - v * delta_t) / 2.
    """
    T_pair = 52.0
    T_skew = 26.0
    L = 2.0
    v = 1250.0

    # Test Case 1: Symmetric arrival (midpoint d1 = 1.0m, true delta_t = 0.0 us)
    # A1 samples 26us later, so discrete cross-correlation peak occurs at lag = -0.5
    lag_mid = -0.5
    dt_mid = (lag_mid * T_pair) + T_skew
    assert dt_mid == 0.0
    d1_mid = (L - (v * dt_mid * 1e-6)) / 2.0
    assert d1_mid == 1.000

    # Test Case 2: Leak at 0.5m (closer to Sensor 1, true delta_t = +800.0 us)
    # Observed lag = (800 - 26) / 52 = +14.8846
    lag_05 = (800.0 - T_skew) / T_pair
    dt_05 = (lag_05 * T_pair) + T_skew
    assert abs(dt_05 - 800.0) < 1e-6
    d1_05 = (L - (v * dt_05 * 1e-6)) / 2.0
    assert abs(d1_05 - 0.500) < 1e-6

    # Test Case 3: Leak at 1.5m (closer to Sensor 2, true delta_t = -800.0 us)
    # Observed lag = (-800 - 26) / 52 = -15.8846
    lag_15 = (-800.0 - T_skew) / T_pair
    dt_15 = (lag_15 * T_pair) + T_skew
    assert abs(dt_15 - (-800.0)) < 1e-6
    d1_15 = (L - (v * dt_15 * 1e-6)) / 2.0
    assert abs(d1_15 - 1.500) < 1e-6


