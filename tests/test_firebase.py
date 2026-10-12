"""
Unit Tests for AquaGuard AI Firebase Integration
===============================================
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.firebase_manager import firebase_mgr
from app.models import TelemetryRecord, WindowDecisionModel, BaselineProfileModel, HardwareDiagnosticsModel

client = TestClient(app)


def test_firebase_status_endpoint():
    response = client.get("/api/firebase/status")
    assert response.status_code == 200
    data = response.json()
    assert "initialized" in data
    assert data["project_id"] == "aquaguard-pipeline"


def test_firebase_manager_initialization():
    ok = firebase_mgr.initialize()
    assert ok is True
    assert firebase_mgr.db is not None


def test_firebase_save_measurement_reduced_frequency(mocker):
    firebase_mgr.initialize()
    if firebase_mgr.db:
        mocker.patch.object(firebase_mgr.db, "collection")
    rec = TelemetryRecord(
        pc_timestamp="2026-10-08T21:00:00",
        second_index=1,
        s1_rms=12.0, s2_rms=11.5,
        s1_abnormal=0, s2_abnormal=0, is_transient=0,
        status_str="PRELIM_NORMAL", is_demo=True
    )
    res = firebase_mgr.save_measurement_reduced_frequency(rec, force=True)
    assert res is True


def test_firebase_save_window_report(mocker):
    firebase_mgr.initialize()
    if firebase_mgr.db:
        mocker.patch.object(firebase_mgr.db, "collection")
    decision = WindowDecisionModel(
        window_index=1,
        timestamp="2026-10-08T21:00:00",
        decision="NORMAL",
        reasoning="Test normal decision",
        s1_abnormal_count=0, s2_abnormal_count=0,
        s1_max_seq=0, s2_max_seq=0,
        s1_med_rms=12.0, s2_med_rms=11.5,
        s1_var_ratio=0.1, s2_var_ratio=0.1,
        tdoa_sec=0.0, peak_corr=0.2, loc_valid=False,
        is_demo=True
    )
    res = firebase_mgr.save_window_report(decision)
    assert res is True


def test_firebase_update_sensor_health(mocker):
    firebase_mgr.initialize()
    if firebase_mgr.db:
        mocker.patch.object(firebase_mgr.db, "collection")
    diag = HardwareDiagnosticsModel(
        serial_port="COM3",
        baud_rate=115200,
        connection_status="DEMO_MODE",
        esp32_uptime_sec=100,
        sample_rate_hz=2500,
        timing_overruns=0,
        s1_adc_offset_ok=True,
        s2_adc_offset_ok=True,
        pipe_length_m=2.0,
        s1_position_m=0.0,
        s2_position_m=2.0
    )
    base = BaselineProfileModel()
    res = firebase_mgr.update_sensor_health(diag, base)
    assert res is True

