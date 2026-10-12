"""
AquaGuard AI FastAPI Main Application
=====================================
Features:
- WebSocket endpoint `/ws/telemetry` for live 1-second streaming
- Firebase Cloud Firestore integration for project `aquaguard-pipeline`
- Seamless switching between Live ESP32 Mode and Demo Synthetic Mode
- PySerial integration with automatic reconnection
- Decision Engine for 60-second window multi-criteria pipeline monitoring
- SQLite database persistence + Cloud Firestore document storage
"""
import asyncio
import json
import time
import datetime
from contextlib import asynccontextmanager
from typing import List, Set, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import (
    PIPE_LENGTH_METERS, SENSOR_1_POSITION, SENSOR_2_POSITION, SAMPLE_RATE_HZ, DEFAULT_PERSISTENCE_REQ
)
from app.database import (
    init_db, save_telemetry_record, save_window_decision, save_wireless_record,
    get_wireless_history, get_latest_wireless_record, get_localization_events,
    get_latest_localization_event
)
from app.decision_engine import DecisionEngine
from app.demo_generator import DemoGenerator
from app.serial_manager import SerialManager, list_available_ports
from app.firebase_manager import firebase_mgr
from app.models import (
    TelemetryRecord, BaselineProfileModel, WindowDecisionModel,
    HardwareDiagnosticsModel, TelemetryStreamPayload, GPSDataModel,
    HighResLocalizationModel, ADCDiagnosticsModel, FlowTelemetryModel,
    WirelessTelemetryModel
)
from app.routers import telemetry, events, experiments, settings, health, firebase, gps


import queue
import threading

# Background Persistence Queue (max 500 items) to keep serial thread 100% non-blocking
persistence_queue: queue.Queue = queue.Queue(maxsize=500)
last_websocket_broadcast_timestamp: float = 0.0


def _persistence_worker_loop():
    """Worker loop for offloading SQLite disk writes and Firebase cloud calls off the serial thread."""
    while True:
        try:
            item = persistence_queue.get()
            if item is None:
                break
            item_type, data = item
            if item_type == "telemetry":
                try:
                    save_telemetry_record(data)
                except Exception as e:
                    print(f"[PERSISTENCE ERROR] SQLite save_telemetry_record failed: {e}")
                try:
                    firebase_mgr.save_measurement_reduced_frequency(data)
                except Exception as e:
                    print(f"[FIREBASE ERROR] save_measurement_reduced_frequency failed: {e}")
            elif item_type == "window_decision":
                try:
                    save_window_decision(data)
                except Exception as e:
                    print(f"[PERSISTENCE ERROR] SQLite save_window_decision failed: {e}")
                try:
                    firebase_mgr.save_window_report(data)
                except Exception as e:
                    print(f"[FIREBASE ERROR] save_window_report failed: {e}")
            elif item_type == "wireless":
                try:
                    save_wireless_record(data)
                except Exception as e:
                    print(f"[PERSISTENCE ERROR] SQLite save_wireless_record failed: {e}")
            persistence_queue.task_done()
        except Exception as e:
            print(f"[PERSISTENCE WORKER ERROR] {e}")


persistence_thread = threading.Thread(target=_persistence_worker_loop, daemon=True)
persistence_thread.start()


# Global System State Management
demo_mode: bool = True  # Default to DEMO MODE if hardware disconnected
demo_scenario: str = "normal"  # "normal", "pump_disturbance", "confirmed_leak"

decision_engine = DecisionEngine(persistence_req=DEFAULT_PERSISTENCE_REQ)
demo_generator = DemoGenerator()
active_websockets: Set[WebSocket] = set()

recent_telemetry_buffer: List[TelemetryRecord] = []
current_window_records: List[TelemetryRecord] = []
latest_window_decision: Optional[WindowDecisionModel] = None

# Serial Manager Instance
serial_mgr: Optional[SerialManager] = None


def handle_new_record(record: TelemetryRecord):
    global latest_window_decision, recent_telemetry_buffer, current_window_records

    # Save to in-memory ring buffer (up to 1000 points)
    recent_telemetry_buffer.append(record)
    if len(recent_telemetry_buffer) > 1000:
        recent_telemetry_buffer.pop(0)

    # Accumulate for 60-second window calibration/decision
    current_window_records.append(record)

    # Check if window completed or run decision engine
    decision = decision_engine.add_second_record(record)
    if decision:
        latest_window_decision = decision
        if not record.is_demo:
            try:
                persistence_queue.put_nowait(("window_decision", decision))
            except queue.Full:
                pass

        # Calibration auto-update if uncalibrated (using real records)
        if not decision_engine.baseline.is_calibrated and len(current_window_records) >= 60:
            decision_engine.calibrate_from_window(current_window_records[:60])

        current_window_records = []

    # Offload SQLite & Firebase persistence to background queue
    if not record.is_demo:
        try:
            persistence_queue.put_nowait(("telemetry", record))
        except queue.Full:
            pass


def handle_new_flow(flow_dict: dict):
    decision_engine.update_flow_telemetry(flow_dict)


def handle_new_wireless(wireless_dict: dict):
    if not wireless_dict.get("is_demo", False):
        try:
            persistence_queue.put_nowait(("wireless", wireless_dict))
        except queue.Full:
            pass


def handle_new_localization(loc_dict: dict):
    pass


# Initialize serial callback with record, flow, wireless, and localization handlers
serial_mgr = SerialManager(
    callback_on_record=handle_new_record,
    callback_on_flow=handle_new_flow,
    callback_on_wireless=handle_new_wireless,
    callback_on_localization=handle_new_localization
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    init_db()
    print("[SYSTEM] SQLite Database initialized successfully.")

    # Startup: Initialize Firebase Admin SDK
    fb_ok = firebase_mgr.initialize()
    if fb_ok:
        print("[SYSTEM] Firebase Cloud Firestore initialized for project 'aquaguard-pipeline'.")
    else:
        print(f"[SYSTEM WARNING] Firebase initialization: {firebase_mgr.last_error}")

    # Start serial manager background worker thread
    if serial_mgr:
        serial_mgr.start_worker()

    # Start background loop for broadcasting telemetry to WebSockets
    broadcast_task = asyncio.create_task(telemetry_broadcast_loop())

    yield

    # Shutdown
    broadcast_task.cancel()
    if serial_mgr:
        serial_mgr.stop_worker()
    print("[SYSTEM] Shutdown complete.")


app = FastAPI(
    title="AquaGuard AI Backend",
    description="Smart Pipeline Leak Detection & Monitoring System API with Firebase Firestore integration",
    version="1.1.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(telemetry.router)
app.include_router(events.router)
app.include_router(experiments.router)
app.include_router(settings.router)
app.include_router(health.router)
app.include_router(firebase.router)
app.include_router(gps.router)


class DemoScenarioRequest(BaseModel):
    demo_mode: bool
    scenario: Optional[str] = "normal"  # "normal", "pump_disturbance", "confirmed_leak"


class HardwareCommandRequest(BaseModel):
    command: str  # "RECALIBRATE", "SET_PERSISTENCE", "TOGGLE_CSV", "TOGGLE_VERBOSE"
    parameter: Optional[int] = None
    confirm_no_leak: Optional[bool] = False


@app.post("/api/mode")
def set_system_mode(payload: DemoScenarioRequest):
    global demo_mode, demo_scenario, recent_telemetry_buffer, current_window_records, latest_window_decision
    demo_mode = payload.demo_mode
    if payload.scenario:
        demo_scenario = payload.scenario
        demo_generator.set_scenario(demo_scenario)

    if not demo_mode:
        # Purge synthetic demo records when switching into Live Mode
        recent_telemetry_buffer = [r for r in recent_telemetry_buffer if not r.is_demo]
        current_window_records = [r for r in current_window_records if not r.is_demo]
        decision_engine.history_window = [r for r in decision_engine.history_window if not r.is_demo]
        latest_window_decision = None

    return {
        "status": "success",
        "demo_mode": demo_mode,
        "scenario": demo_scenario
    }


@app.post("/api/command")
def send_hardware_command(payload: HardwareCommandRequest):
    global serial_mgr, decision_engine

    if payload.command == "RECALIBRATE":
        if not payload.confirm_no_leak:
            raise HTTPException(status_code=400, detail="Recalibration requires explicit confirmation that pump is running normally and NO leak is present.")

        # If live serial active, send 'B' command
        if serial_mgr and serial_mgr.is_connected:
            sent = serial_mgr.send_command("B\n")
            if not sent:
                raise HTTPException(status_code=500, detail="Failed to send command to ESP32 serial port.")
        
        # Trigger software decision engine recalibration reset
        real_recs = [r for r in recent_telemetry_buffer if not r.is_demo]
        if len(real_recs) >= 60:
            decision_engine.calibrate_from_window(real_recs[-60:])
        return {"status": "success", "message": "Baseline recalibration command dispatched."}

    elif payload.command == "SET_PERSISTENCE":
        val = payload.parameter or 42
        if val < 10 or val > 60:
            raise HTTPException(status_code=400, detail="Persistence threshold must be between 10 and 60 seconds.")

        decision_engine.persistence_req = val
        if serial_mgr and serial_mgr.is_connected:
            serial_mgr.send_command(f"P {val}\n")
        return {"status": "success", "message": f"Persistence threshold updated to {val}/60s."}

    elif payload.command == "TOGGLE_CSV":
        if serial_mgr and serial_mgr.is_connected:
            serial_mgr.send_command("M\n")
        return {"status": "success", "message": "Toggled output mode."}

    elif payload.command == "TOGGLE_VERBOSE":
        if serial_mgr and serial_mgr.is_connected:
            serial_mgr.send_command("V\n")
        return {"status": "success", "message": "Toggled verbose mode."}

    raise HTTPException(status_code=400, detail="Unknown hardware command.")


@app.post("/api/settings/connect")
def connect_serial_port(payload: dict = Body(...)):
    global demo_mode, recent_telemetry_buffer, current_window_records, latest_window_decision
    port = payload.get("port")
    baud = payload.get("baud_rate", 115200)
    if not serial_mgr:
        raise HTTPException(status_code=500, detail="Serial manager not initialized.")

    success = serial_mgr.connect(port, baud)
    if not success:
        raise HTTPException(status_code=400, detail=serial_mgr.last_error or f"Failed to connect to serial port {port}.")
    
    demo_mode = False
    # Clear out synthetic demo records when switching into Live Mode
    recent_telemetry_buffer = [r for r in recent_telemetry_buffer if not r.is_demo]
    current_window_records = [r for r in current_window_records if not r.is_demo]
    decision_engine.history_window = [r for r in decision_engine.history_window if not r.is_demo]
    latest_window_decision = None
    return {"status": "success", "port": port, "baud_rate": baud, "demo_mode": False}


@app.post("/api/settings/disconnect")
def disconnect_serial_port():
    global demo_mode
    if serial_mgr:
        serial_mgr.disconnect()
    demo_mode = True
    return {"status": "success", "message": "Serial port disconnected.", "demo_mode": True}


@app.get("/api/debug/telemetry")
def debug_telemetry_endpoint():
    now_ts = time.time()
    real_recs = [r for r in recent_telemetry_buffer if not r.is_demo]
    last_real_s1_rms = real_recs[-1].s1_rms if real_recs else None
    last_real_s2_rms = real_recs[-1].s2_rms if real_recs else None
    
    last_real_age = None
    if real_recs:
        try:
            rec_dt = datetime.datetime.fromisoformat(real_recs[-1].pc_timestamp)
            last_real_age = round(now_ts - rec_dt.timestamp(), 2)
        except Exception:
            pass

    w_status = serial_mgr.get_wireless_status() if serial_mgr else None
    last_rf24_ts = serial_mgr.last_rf24_receive_timestamp if serial_mgr else 0.0
    rf24_age = round(now_ts - last_rf24_ts, 2) if last_rf24_ts > 0 else None

    flow_obj = {
        "flow_in_lpm": w_status["flow_in_lpm"] if w_status else (serial_mgr.latest_flow_data.get("flow_in_lpm", 0.0) if serial_mgr else 0.0),
        "flow_out_lpm": w_status["flow_out_lpm"] if w_status else (serial_mgr.latest_flow_data.get("flow_out_lpm", 0.0) if serial_mgr else 0.0),
        "flow_diff_lpm": w_status["flow_diff_lpm"] if w_status else (serial_mgr.latest_flow_data.get("flow_diff_lpm", 0.0) if serial_mgr else 0.0),
        "leak_alarm": w_status["leak_alarm"] if w_status else (serial_mgr.latest_flow_data.get("leak_confirmed", False) if serial_mgr else False),
        "status": w_status["status_str"] if w_status else (serial_mgr.latest_flow_data.get("status", "NO_FLOW") if serial_mgr else "NO_FLOW")
    }

    gps_fix = serial_mgr.latest_gps_data.get("fix_status", "NO_FIX") if serial_mgr else "NO_FIX"

    radio_diag = {
        "valid_rf24_count": serial_mgr.valid_rf24_count if serial_mgr else 0,
        "missed_since_last": w_status.get("missed_packets", 0) if w_status else 0,
        "total_missed_packets": serial_mgr.total_missed_packets if serial_mgr else 0,
        "sequence_reset_count": serial_mgr.sequence_reset_count if serial_mgr else 0
    }

    return {
        "serial_connected": serial_mgr.is_connected if serial_mgr else False,
        "serial_port": serial_mgr.port if serial_mgr else "NOT_CONNECTED",
        "baud_rate": serial_mgr.baud_rate if serial_mgr else 115200,
        "communication_source": "ARDUINO_UNO_NRF24",
        "last_serial_receive_timestamp": serial_mgr.last_seen_timestamp if serial_mgr else 0.0,
        "last_rf24_timestamp": last_rf24_ts,
        "last_rf24_received_iso": datetime.datetime.fromtimestamp(last_rf24_ts).isoformat() if last_rf24_ts > 0 else None,
        "last_packet_sequence": serial_mgr.last_packet_sequence if serial_mgr else -1,
        "packet_age_seconds": rf24_age,
        "flow_readings": flow_obj,
        "gps_fix_status": gps_fix,
        "radio_diagnostic": radio_diag,
        "valid_csv_count": serial_mgr.valid_csv_count if serial_mgr else 0,
        "parse_error_count": serial_mgr.parse_error_count if serial_mgr else 0,
        "callback_invocation_count": serial_mgr.callback_invocation_count if serial_mgr else 0,
        "callback_error_count": serial_mgr.callback_error_count if serial_mgr else 0,
        "real_telemetry_buffer_size": len(real_recs),
        "detection_window_size": len(current_window_records),
        "last_real_s1_rms": last_real_s1_rms,
        "last_real_s2_rms": last_real_s2_rms,
        "last_real_record_age_seconds": last_real_age,
        "last_websocket_broadcast_timestamp": last_websocket_broadcast_timestamp,
        "current_demo_mode": demo_mode,
        "last_processing_error": serial_mgr.last_processing_error if serial_mgr else None,
        "last_diagnostic_line": serial_mgr.last_diagnostic_line if serial_mgr else None
    }


@app.get("/api/wireless/latest")
def get_wireless_latest_endpoint():
    if serial_mgr:
        w_status = serial_mgr.get_wireless_status()
        if w_status:
            return w_status
    db_rec = get_latest_wireless_record()
    if db_rec:
        return db_rec
    if demo_mode:
        return demo_generator.generate_wireless()
    return {"status_str": "DATA UNAVAILABLE", "communication_source": "ARDUINO_UNO_NRF24"}


@app.get("/api/wireless/history")
def get_wireless_history_endpoint(limit: int = 100):
    return get_wireless_history(limit=limit)


@app.get("/api/localization/latest")
def get_localization_latest_endpoint():
    if serial_mgr:
        loc = serial_mgr.get_localization_status()
        if loc:
            return loc
    db_event = get_latest_localization_event()
    if db_event:
        return db_event
    if demo_mode:
        return demo_generator.generate_localization().model_dump()
    return {"status": "LOCATION UNAVAILABLE", "loc_valid": False, "flow_confirmed_leak": False}


@app.get("/api/localization/history")
def get_localization_history_endpoint(limit: int = 50):
    return get_localization_events(limit=limit)


@app.get("/api/debug/serial-raw")
def debug_serial_raw_endpoint():
    if not serial_mgr:
        return {"port": "NONE", "connected": False, "output_mode": "UNKNOWN", "last_10_lines": [], "diagnostic_messages": []}
    
    with serial_mgr.lock:
        raw_lines = list(serial_mgr.raw_line_buffer)
        diag_lines = list(serial_mgr.diagnostic_messages)
        port = serial_mgr.port or "NONE"
        connected = serial_mgr.is_connected
        mode = serial_mgr.output_mode

    return {
        "port": port,
        "connected": connected,
        "output_mode": mode,
        "last_10_lines": raw_lines,
        "diagnostic_messages": diag_lines
    }


@app.get("/api/serial/adc-diagnostics")
def get_adc_diagnostics_endpoint():
    if demo_mode or not serial_mgr:
        return {
            "s1_min": 1600,
            "s1_max": 2500,
            "s1_mean": 2048.0,
            "s1_clips": 0,
            "s1_clip_pct": 0.0,
            "s2_min": 1580,
            "s2_max": 2520,
            "s2_mean": 2048.0,
            "s2_clips": 0,
            "s2_clip_pct": 0.0,
            "is_clipping": False,
            "status": "OK",
            "last_updated": time.time()
        }
    return serial_mgr.get_adc_diagnostics()


def build_telemetry_payload() -> TelemetryStreamPayload:
    """Build current TelemetryStreamPayload object from real or demo telemetry."""
    global demo_mode, recent_telemetry_buffer, current_window_records, latest_window_decision
    if serial_mgr and serial_mgr.is_connected:
        if demo_mode:
            recent_telemetry_buffer = [r for r in recent_telemetry_buffer if not r.is_demo]
            current_window_records = [r for r in current_window_records if not r.is_demo]
            decision_engine.history_window = [r for r in decision_engine.history_window if not r.is_demo]
            latest_window_decision = None
        demo_mode = False

    record: Optional[TelemetryRecord] = None
    if demo_mode:
        # Generate synthetic demo telemetry ONLY when demo_mode is explicitly True
        record = demo_generator.generate_next_second(
            s1_thresh=decision_engine.baseline.s1_thresh,
            s2_thresh=decision_engine.baseline.s2_thresh
        )
        handle_new_record(record)
    else:
        # In Live Mode, select the latest real hardware record with is_demo=False
        real_records = [r for r in recent_telemetry_buffer if not r.is_demo]
        if real_records:
            record = real_records[-1]

    ser_status = serial_mgr.get_status() if serial_mgr else None
    now_ts = time.time()

    if demo_mode:
        conn_str = "DEMO_MODE"
    elif ser_status and ser_status.connected:
        if record is None:
            conn_str = "WAITING_FOR_DATA"
        else:
            try:
                rec_dt = datetime.datetime.fromisoformat(record.pc_timestamp)
                age_sec = now_ts - rec_dt.timestamp()
            except Exception:
                age_sec = 0.0

            conn_str = "STALE" if age_sec > 5.0 else "CONNECTED"
    else:
        conn_str = "DISCONNECTED"

    if serial_mgr and serial_mgr.last_error and ("Access is denied" in serial_mgr.last_error or "PermissionError" in serial_mgr.last_error):
        conn_str = "PORT_LOCKED"

    last_csv_ts = serial_mgr.last_csv_receive_timestamp if serial_mgr else 0.0
    last_rf24_ts = serial_mgr.last_rf24_receive_timestamp if serial_mgr else 0.0
    last_data_ts = max(last_csv_ts, last_rf24_ts)
    last_age = round(now_ts - last_data_ts, 1) if (last_data_ts > 0 and not demo_mode) else 0.0

    if demo_mode:
        freshness_str = "LIVE"
    elif not ser_status or not ser_status.connected:
        freshness_str = "DISCONNECTED"
    elif last_age <= 3.0:
        freshness_str = "LIVE"
    elif last_age <= 5.0:
        freshness_str = "DELAYED"
    else:
        freshness_str = "COMMUNICATION LOST" if last_rf24_ts > 0 else "STALE"

    adc_dict = serial_mgr.get_adc_diagnostics() if (serial_mgr and not demo_mode) else {
        "s1_min": 1600,
        "s1_max": 2500,
        "s1_mean": 2048.0,
        "s1_clips": 0,
        "s1_clip_pct": 0.0,
        "s2_min": 1580,
        "s2_max": 2520,
        "s2_mean": 2048.0,
        "s2_clips": 0,
        "s2_clip_pct": 0.0,
        "is_clipping": False,
        "status": "OK",
        "last_updated": now_ts
    }

    diagnostics = HardwareDiagnosticsModel(
        serial_port=ser_status.port if ser_status else "NONE",
        baud_rate=ser_status.baud_rate if ser_status else 115200,
        connection_status=conn_str,
        esp32_uptime_sec=serial_mgr.last_packet_sequence if (serial_mgr and serial_mgr.valid_rf24_count > 0) else (record.second_index if record else 0),
        sample_rate_hz=SAMPLE_RATE_HZ,
        timing_overruns=0,
        s1_adc_offset_ok=(adc_dict.get("s1_mean", 2048.0) > 1000 and adc_dict.get("s1_mean", 2048.0) < 3000),
        s2_adc_offset_ok=(adc_dict.get("s2_mean", 2048.0) > 1000 and adc_dict.get("s2_mean", 2048.0) < 3000),
        pipe_length_m=PIPE_LENGTH_METERS,
        s1_position_m=SENSOR_1_POSITION,
        s2_position_m=SENSOR_2_POSITION,
        last_error=serial_mgr.last_error if serial_mgr else None,
        data_freshness=freshness_str,
        last_record_timestamp=last_data_ts,
        last_record_age_sec=last_age,
        telemetry_hz=serial_mgr.telemetry_hz if (serial_mgr and not demo_mode) else 1.0,
        s1_min=adc_dict.get("s1_min", 0),
        s1_max=adc_dict.get("s1_max", 4095),
        s1_mean=adc_dict.get("s1_mean", 2048.0),
        s1_clips=adc_dict.get("s1_clips", 0),
        s1_clip_pct=adc_dict.get("s1_clip_pct", 0.0),
        s2_min=adc_dict.get("s2_min", 0),
        s2_max=adc_dict.get("s2_max", 4095),
        s2_mean=adc_dict.get("s2_mean", 2048.0),
        s2_clips=adc_dict.get("s2_clips", 0),
        s2_clip_pct=adc_dict.get("s2_clip_pct", 0.0)
    )

    gps_payload: Optional[GPSDataModel] = None
    if demo_mode:
        gps_payload = GPSDataModel(
            latitude=6.927079,
            longitude=79.861244,
            satellites=9,
            hdop=0.9,
            fix_age_ms=120,
            fix_status="FIX",
            is_stale=False,
            is_demo=True,
            last_updated=now_ts
        )
    elif serial_mgr:
        gps_dict = serial_mgr.get_gps_status()
        gps_payload = GPSDataModel(**gps_dict)

    flow_payload: Optional[FlowTelemetryModel] = None
    if demo_mode:
        flow_payload = demo_generator.generate_flow()
        decision_engine.update_flow_telemetry(flow_payload.model_dump())
    elif serial_mgr:
        flow_dict = serial_mgr.get_flow_status()
        flow_payload = FlowTelemetryModel(**flow_dict)
        decision_engine.update_flow_telemetry(flow_dict)

    loc_payload: Optional[HighResLocalizationModel] = None
    if demo_mode:
        loc_payload = demo_generator.generate_localization()
    elif serial_mgr:
        loc_dict = serial_mgr.get_localization_status()
        loc_payload = HighResLocalizationModel(**loc_dict)

    adc_payload = ADCDiagnosticsModel(**adc_dict)

    wireless_payload: Optional[WirelessTelemetryModel] = None
    if demo_mode:
        wireless_payload = demo_generator.generate_wireless()
    elif serial_mgr:
        w_dict = serial_mgr.get_wireless_status()
        if w_dict:
            wireless_payload = WirelessTelemetryModel(**w_dict)

    return TelemetryStreamPayload(
        type="telemetry_update",
        system_state=decision_engine.system_state,
        demo_mode=demo_mode,
        demo_scenario=demo_scenario,
        telemetry=record,
        baseline=decision_engine.baseline,
        current_window_sec=len(current_window_records),
        window_decision=latest_window_decision,
        diagnostics=diagnostics,
        gps=gps_payload,
        localization=loc_payload,
        adc=adc_payload,
        flow=flow_payload,
        wireless=wireless_payload
    )


@app.get("/api/serial/flow")
def get_serial_flow_endpoint():
    if demo_mode or not serial_mgr:
        return demo_generator.generate_flow()
    return serial_mgr.get_flow_status()



@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    print(f"[WS] Client connected. Total active clients: {len(active_websockets)}")
    
    # Send immediate initial state frame on connection
    try:
        payload = build_telemetry_payload()
        await websocket.send_text(payload.model_dump_json())
    except Exception as e:
        print(f"[WS] Failed to send initial payload: {e}")

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "set_scenario":
                        sc = msg.get("scenario", "normal")
                        demo_generator.set_scenario(sc)
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
        print(f"[WS] Client disconnected. Total active clients: {len(active_websockets)}")
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


async def telemetry_broadcast_loop():
    """1-second timer loop for pushing live telemetry & system state to WebSocket clients."""
    global last_websocket_broadcast_timestamp
    loop_count = 0
    while True:
        try:
            await asyncio.sleep(1.0)
            loop_count += 1

            payload = build_telemetry_payload()

            # Update Firestore sensor health document every 10 seconds asynchronously in thread pool
            if loop_count % 10 == 0:
                asyncio.create_task(asyncio.to_thread(firebase_mgr.update_sensor_health, payload.diagnostics, decision_engine.baseline))

            if not active_websockets:
                continue

            payload_json = payload.model_dump_json()

            # Broadcast to all connected clients
            disconnected_clients = set()
            for ws in active_websockets:
                try:
                    await ws.send_text(payload_json)
                    last_websocket_broadcast_timestamp = time.time()
                except Exception:
                    disconnected_clients.add(ws)

            for ws in disconnected_clients:
                active_websockets.remove(ws)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[BROADCAST LOOP ERROR] {e}")
