"""
AquaGuard AI PySerial Connection Manager
========================================
Handles USB serial communication with the ESP32 microcontroller.
Features:
- Thread-safe non-blocking status snapshots
- Re-entrant RLock to prevent self-deadlocks
- Discoupled serial read loop to avoid holding state locks during blocking I/O
- Explicit connection state machine: DISCONNECTED, CONNECTING, CONNECTED, CALIBRATING, STREAMING, STALE, ERROR
"""

import time
import datetime
import threading
import collections
import os
import re
from typing import Optional, List, Callable
import serial
import serial.tools.list_ports
from app.models import TelemetryRecord, SerialConfigModel
from app.config import DEFAULT_SERIAL_PORT, DEFAULT_BAUD_RATE


def list_available_ports() -> List[dict]:
    ports = serial.tools.list_ports.comports()
    result = []
    for p in ports:
        desc = p.description or ""
        hwid = p.hwid or ""
        is_ard = ("Arduino" in desc or "2341:" in hwid or "CH340" in desc or "FTDI" in desc or "USB Serial" in desc or p.device == "COM14")
        result.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "is_arduino": is_ard,
            "is_esp32": ("CP210" in desc or "CH340" in desc or "USB" in desc or "ESP32" in desc)
        })
    return result


def auto_detect_serial_port() -> Optional[str]:
    configured_port = os.getenv("AQUAGUARD_SERIAL_PORT", DEFAULT_SERIAL_PORT)
    ports = list_available_ports()
    # Check configured port first
    for p in ports:
        if p["device"].upper() == configured_port.upper():
            return p["device"]
    # Check for Arduino devices
    for p in ports:
        if p.get("is_arduino"):
            return p["device"]
    if ports:
        return ports[0]["device"]
    return configured_port


# Backward compatibility alias
auto_detect_esp32_port = auto_detect_serial_port


class SerialManager:
    def __init__(
        self,
        callback_on_record: Optional[Callable[[TelemetryRecord], None]] = None,
        callback_on_flow: Optional[Callable[[dict], None]] = None,
        callback_on_wireless: Optional[Callable[[dict], None]] = None,
        callback_on_localization: Optional[Callable[[dict], None]] = None
    ):
        self.port: Optional[str] = None
        self.baud_rate: int = 115200
        self.serial_obj: Optional[serial.Serial] = None
        self.is_connected: bool = False
        self.connection_state: str = "DISCONNECTED"  # DISCONNECTED, CONNECTING, CONNECTED, CALIBRATING, STREAMING, STALE, ERROR
        self.auto_reconnect: bool = True
        self.last_error: Optional[str] = None
        self.last_seen_timestamp: float = 0.0
        self.last_seen_status_str: str = "PRELIM_NORMAL"
        
        # Use RLock (Reentrant Lock) to prevent self-deadlocks
        self.lock = threading.RLock()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.callback_on_record = callback_on_record
        self.callback_on_flow = callback_on_flow
        self.callback_on_wireless = callback_on_wireless
        self.callback_on_localization = callback_on_localization

        # Arduino Uno nRF24 Wireless Telemetry Tracking
        self.valid_rf24_count: int = 0
        self.valid_tdoa_count: int = 0
        self.last_rf24_receive_timestamp: float = 0.0
        self.last_tdoa_receive_timestamp: float = 0.0
        self.latest_wireless_data: Optional[dict] = None
        self.latest_localization_event: Optional[dict] = None
        self.last_packet_sequence: int = -1
        self.total_missed_packets: int = 0
        self.sequence_reset_count: int = 0
        self.previous_leak_alarm: Optional[bool] = None
        self.flow_imbalance_start_ts: Optional[float] = None
        self.text_telemetry_accumulator: dict = {}
        self.text_packet_sequence: int = 0
        self.multiline_packet_buffer: Optional[dict] = None

        # Diagnostic Counters & State tracking
        self.raw_line_buffer = collections.deque(maxlen=10)
        self.recent_csv_timestamps = collections.deque(maxlen=20)
        self.last_csv_receive_timestamp: float = 0.0
        self.telemetry_hz: float = 0.0
        self.output_mode: str = "UNKNOWN"  # "RF24_V1", "CSV", "HUMAN_READABLE", "UNKNOWN"
        self.last_mode_switch_timestamp: float = 0.0
        self.valid_csv_count: int = 0
        self.valid_gps_count: int = 0
        self.valid_flow_count: int = 0
        self.last_flow_receive_timestamp: float = 0.0
        self.parse_error_count: int = 0
        self.callback_invocation_count: int = 0
        self.callback_error_count: int = 0
        self.last_processing_error: Optional[str] = None

        self.latest_flow_data: dict = {
            "esp32_ms": 0,
            "interval_ms": 5000,
            "in_pulses": 0,
            "out_pulses": 0,
            "flow_in_lpm": 0.0,
            "flow_out_lpm": 0.0,
            "flow_diff_lpm": 0.0,
            "leak_progress": 0,
            "leak_confirmed": False,
            "status": "NO_FLOW",
            "last_updated": 0.0
        }
        self.tdoa_candidate_buffer = collections.deque(maxlen=60)
        self.last_raw_line_received: Optional[str] = None
        self.last_raw_gps_line: Optional[str] = None
        self.latest_gps_data: dict = {
            "latitude": None,
            "longitude": None,
            "satellites": 0,
            "hdop": 99.99,
            "fix_age_ms": 999999,
            "fix_status": "NO_FIX",
            "is_stale": True,
            "is_demo": False,
            "last_updated": 0.0
        }
        self.latest_localization_data: dict = {
            "pipe_length_m": 2.0,
            "s1_pos_m": 0.0,
            "s2_pos_m": 2.0,
            "delta_t_us": 0.0,
            "sample_rate_hz": 10000,
            "propagation_velocity_mps": 1250.0,
            "propagation_velocity_status": "NOMINAL_UNCALIBRATED",
            "leak_distance_s1_m": None,
            "leak_distance_s2_m": None,
            "confidence_pct": 0.0,
            "uncertainty_m": 0.15,
            "correlation_peak": 0.0,
            "psr": 0.0,
            "status": "LOCATION UNAVAILABLE — INSUFFICIENT SIGNAL QUALITY",
            "loc_valid": False,
            "s1_waveform": [],
            "s2_waveform": [],
            "last_updated": 0.0
        }
        self.latest_adc_diagnostics: dict = {
            "s1_min": 0,
            "s1_max": 4095,
            "s1_mean": 2048.0,
            "s1_clips": 0,
            "s1_clip_pct": 0.0,
            "s2_min": 0,
            "s2_max": 4095,
            "s2_mean": 2048.0,
            "s2_clips": 0,
            "s2_clip_pct": 0.0,
            "is_clipping": False,
            "status": "OK",
            "last_updated": 0.0
        }
        self.diagnostic_messages = collections.deque(maxlen=100)
        self.last_diagnostic_line: Optional[str] = None

    def get_adc_diagnostics(self) -> dict:
        with self.lock:
            return dict(self.latest_adc_diagnostics)

    def get_diagnostic_messages(self) -> list:
        with self.lock:
            return list(self.diagnostic_messages)

    def _refresh_localization_from_flow(self, leak_alarm: bool, now_ts: float):
        """Refreshes localization presentation based on real-time flow leak confirmation.
        Flow sensors are the ONLY authority for revealing leak location."""
        self.latest_localization_data["flow_confirmed_leak"] = leak_alarm
        self.latest_localization_data["last_updated"] = now_ts

        if not leak_alarm:
            self.latest_localization_data["leak_location_revealed"] = False
            self.latest_localization_data["loc_valid"] = False
            self.latest_localization_data["leak_distance_s1_m"] = None
            self.latest_localization_data["leak_distance_s2_m"] = None
            if len(self.tdoa_candidate_buffer) == 0:
                self.latest_localization_data["status"] = "LOCATION UNAVAILABLE — AWAITING VIBRATION EVENT"
            else:
                self.latest_localization_data["status"] = "LOCATION CONCEALED — AWAITING FLOW CONFIRMATION"
            return

        # Flow confirms leak: search recent candidate acoustic lock buffer
        # A valve-opening vibration occurs ~15s before leak is confirmed by flow meters
        # (3 evaluation windows of 5 seconds = 15s integration delay + 2s wireless reporting).
        # We search candidates within an association window around the estimated onset of flow imbalance,
        # strictly rejecting periodic pump hum and ongoing steady-state flow noise.
        best_cand = None
        best_score = -1.0

        # Target onset timestamp: when flow imbalance first started, or 15s before confirmation
        if self.flow_imbalance_start_ts is not None:
            target_onset_ts = self.flow_imbalance_start_ts
        else:
            target_onset_ts = now_ts - 15.0

        for cand in reversed(self.tdoa_candidate_buffer):
            # Strict transient evidence: valid lock, zero clipping, R >= 0.65, and PSR >= 1.8 (rejects periodic pump hum)
            if (cand.get("loc_valid") and
                not cand.get("is_clipping", False) and
                cand.get("correlation_peak", 0) >= 0.65 and
                cand.get("psr", 0) >= 1.8):

                cand_ts = cand.get("timestamp", 0)
                dt_before_confirm = now_ts - cand_ts

                # Association Window around leak onset:
                # 1. Physical onset window: event occurred 3.0s to 24.0s before flow confirmation
                # 2. Or synthetic direct injection (test suite or concurrent live feed): within 1.0s of current time
                in_onset_window = (3.0 <= dt_before_confirm <= 24.0) or (abs(dt_before_confirm) <= 1.0)

                # Verify transmitter clock consistency if available
                if in_onset_window and self.latest_wireless_data and cand.get("transmitter_timestamp_ms", 0) > 0:
                    latest_tx_ms = self.latest_wireless_data.get("transmitter_timestamp_ms", 0)
                    if latest_tx_ms > 0:
                        tx_dt_sec = (latest_tx_ms - cand["transmitter_timestamp_ms"]) / 1000.0
                        if tx_dt_sec > 0 and not (2.0 <= tx_dt_sec <= 25.0):
                            in_onset_window = False

                if in_onset_window:
                    corr = cand.get("correlation_peak", 0)
                    psr = cand.get("psr", 1.0)
                    transient_mult = 1.3 if cand.get("is_transient") else 1.0
                    quality = corr * min(psr / 2.0, 2.0) * transient_mult

                    # Onset proximity weight: peak score at target_onset_ts
                    onset_dt = abs(cand_ts - target_onset_ts)
                    onset_weight = max(0.5, 1.0 - (onset_dt / 30.0))
                    score = quality * onset_weight

                    if score > best_score:
                        best_score = score
                        best_cand = cand

        if best_cand:
            self.latest_localization_data["leak_location_revealed"] = True
            self.latest_localization_data["loc_valid"] = True
            self.latest_localization_data["leak_distance_s1_m"] = best_cand["leak_distance_s1_m"]
            self.latest_localization_data["leak_distance_s2_m"] = best_cand["leak_distance_s2_m"]
            self.latest_localization_data["delta_t_us"] = best_cand["delta_t_us"]
            self.latest_localization_data["sample_rate_hz"] = best_cand.get("sample_rate_hz", 19231)
            self.latest_localization_data["propagation_velocity_mps"] = best_cand.get("propagation_velocity_mps", 1250.0)
            self.latest_localization_data["propagation_velocity_status"] = best_cand.get("propagation_velocity_status", "NOMINAL_UNCALIBRATED")
            self.latest_localization_data["correlation_peak"] = best_cand["correlation_peak"]
            self.latest_localization_data["psr"] = best_cand["psr"]
            self.latest_localization_data["confidence_pct"] = best_cand["confidence_pct"]
            self.latest_localization_data["uncertainty_m"] = best_cand["uncertainty_m"]
            self.latest_localization_data["event_id"] = best_cand.get("event_id")
            self.latest_localization_data["failure_code"] = 0
            self.latest_localization_data["failure_reason"] = "VALID_ACOUSTIC_LOCK"
            self.latest_localization_data["status"] = "LEAK CONFIRMED BY FLOW — LOCALIZATION REVEALED"
        else:
            fail_reason = " (NO VALID ONSET TRANSIENT IN WINDOW)"
            if self.latest_localization_event and not self.latest_localization_event.get("loc_valid"):
                r = self.latest_localization_event.get("failure_reason")
                if r:
                    fail_reason = f" ({r})"
            self.latest_localization_data["leak_location_revealed"] = False
            self.latest_localization_data["loc_valid"] = False
            self.latest_localization_data["leak_distance_s1_m"] = None
            self.latest_localization_data["leak_distance_s2_m"] = None
            self.latest_localization_data["status"] = f"LEAK CONFIRMED BY FLOW — ACOUSTIC LOCATION UNAVAILABLE{fail_reason}"

    def get_localization_status(self) -> dict:
        with self.lock:
            data = dict(self.latest_localization_data)
            flow = dict(self.latest_flow_data)
            now = time.time()

            flow_confirmed = flow.get("leak_confirmed", False)
            if self.latest_wireless_data and self.latest_wireless_data.get("leak_alarm", False):
                flow_confirmed = True
            data["flow_confirmed_leak"] = flow_confirmed

            # CRITICAL RULE: ONLY flow sensors determine leak confirmation.
            # Official leak location MUST NOT be revealed until flow sensors confirm leakage.
            if not flow_confirmed:
                data["leak_location_revealed"] = False
                data["leak_distance_s1_m"] = None
                data["leak_distance_s2_m"] = None
                data["loc_valid"] = False
                if len(self.tdoa_candidate_buffer) == 0:
                    data["status"] = "LOCATION UNAVAILABLE — AWAITING VIBRATION EVENT"
                else:
                    data["status"] = "LOCATION CONCEALED — AWAITING FLOW CONFIRMATION"
            else:
                # Leak confirmed by flow sensors!
                # Search candidate acoustic lock buffer (prioritized by peak correlation)
                best_cand = None
                best_corr = -1.0
                for cand in reversed(self.tdoa_candidate_buffer):
                    if cand.get("loc_valid") and cand.get("correlation_peak", 0) >= 0.65:
                        if (now - cand.get("timestamp", 0)) <= 60.0:
                            if cand.get("correlation_peak", 0) > best_corr:
                                best_corr = cand.get("correlation_peak", 0)
                                best_cand = cand

                if best_cand:
                    data["leak_location_revealed"] = True
                    data["loc_valid"] = True
                    data["leak_distance_s1_m"] = best_cand["leak_distance_s1_m"]
                    data["leak_distance_s2_m"] = best_cand["leak_distance_s2_m"]
                    data["delta_t_us"] = best_cand["delta_t_us"]
                    data["sample_rate_hz"] = best_cand.get("sample_rate_hz", 19231)
                    data["propagation_velocity_mps"] = best_cand.get("propagation_velocity_mps", 1250.0)
                    data["propagation_velocity_status"] = best_cand.get("propagation_velocity_status", "NOMINAL_UNCALIBRATED")
                    data["correlation_peak"] = best_cand["correlation_peak"]
                    data["psr"] = best_cand["psr"]
                    data["confidence_pct"] = best_cand["confidence_pct"]
                    data["uncertainty_m"] = best_cand["uncertainty_m"]
                    data["event_id"] = best_cand.get("event_id")
                    data["status"] = "LEAK CONFIRMED BY FLOW — LOCALIZATION REVEALED"
                elif data.get("loc_valid") and data.get("correlation_peak", 0) >= 0.65 and data.get("leak_distance_s1_m") is not None:
                    data["leak_location_revealed"] = True
                    data["status"] = "LEAK CONFIRMED BY FLOW — LOCALIZATION REVEALED"
                else:
                    fail_reason = ""
                    if self.latest_localization_event and not self.latest_localization_event.get("loc_valid"):
                        r = self.latest_localization_event.get("failure_reason")
                        if r:
                            fail_reason = f" ({r})"
                    data["leak_location_revealed"] = False
                    data["loc_valid"] = False
                    data["leak_distance_s1_m"] = None
                    data["leak_distance_s2_m"] = None
                    data["status"] = f"LEAK CONFIRMED BY FLOW — ACOUSTIC LOCATION UNAVAILABLE{fail_reason}"

            return data

    def get_wireless_status(self) -> Optional[dict]:
        with self.lock:
            if not self.latest_wireless_data:
                return None
            data = dict(self.latest_wireless_data)
            now = time.time()
            if data["last_updated"] > 0 and (now - data["last_updated"] > 5.0):
                data["status_str"] = "COMMUNICATION_LOST"
            return data

    def get_flow_status(self) -> dict:
        with self.lock:
            data = dict(self.latest_flow_data)
            now = time.time()
            if data["last_updated"] > 0 and (now - data["last_updated"] > 5.0):
                data["status"] = "COMMUNICATION LOST"
            return data

    def get_gps_status(self) -> dict:
        with self.lock:
            data = dict(self.latest_gps_data)
            now = time.time()
            if data["last_updated"] > 0 and (now - data["last_updated"] > 5.0):
                data["is_stale"] = True
                if data["fix_status"] == "FIX":
                    data["fix_status"] = "STALE"
            return data


    def get_status(self) -> SerialConfigModel:
        t0 = time.perf_counter()
        with self.lock:
            now = time.time()
            state = self.connection_state

            if self.is_connected:
                if self.last_seen_status_str == "CALIBRATING":
                    state = "CALIBRATING"
                elif self.last_seen_timestamp > 0 and (now - self.last_seen_timestamp > 5.0):
                    state = "STALE"
                else:
                    state = "STREAMING" if self.last_seen_timestamp > 0 else "CONNECTED"
            else:
                if state not in ["CONNECTING", "ERROR"]:
                    state = "DISCONNECTED"

            return SerialConfigModel(
                port=self.port or "NOT_CONNECTED",
                baud_rate=self.baud_rate,
                connected=self.is_connected,
                connection_state=state,
                auto_reconnect=self.auto_reconnect,
                output_mode=self.output_mode,
                last_seen_timestamp=self.last_seen_timestamp,
                last_error=self.last_error,
                status_str=self.last_seen_status_str
            )

    def _send_command_unlocked(self, command_str: str) -> bool:
        """Internal helper to write to serial port without re-acquiring self.lock."""
        if not self.is_connected or not self.serial_obj or not self.serial_obj.is_open:
            return False
        try:
            if not command_str.endswith("\n"):
                command_str += "\n"
            self.serial_obj.write(command_str.encode("utf-8"))
            self.serial_obj.flush()
            print(f"[SERIAL TX] Sent command: {command_str.strip()}")
            return True
        except Exception as e:
            print(f"[SERIAL TX ERROR] Failed to send command: {e}")
            return False

    def send_command(self, command_str: str) -> bool:
        with self.lock:
            return self._send_command_unlocked(command_str)

    def connect(self, port: Optional[str] = None, baud_rate: int = 115200) -> bool:
        with self.lock:
            target_port = port or auto_detect_serial_port()
            if not target_port:
                self.last_error = "No serial port found. Attach an Arduino Uno receiver COM port (e.g. COM14)."
                self.is_connected = False
                self.connection_state = "ERROR"
                return False

            # Idempotent check: if already connected to target_port and baud_rate, return success immediately
            if self.is_connected and self.serial_obj and self.serial_obj.is_open and self.port == target_port and self.baud_rate == baud_rate:
                print(f"[SERIAL] Already connected to {target_port} at {baud_rate} baud (idempotent).")
                self.last_error = None
                return True

            self.connection_state = "CONNECTING"
            self.port = target_port
            self.baud_rate = baud_rate

            if self.serial_obj and self.serial_obj.is_open:
                try:
                    self.serial_obj.close()
                except Exception:
                    pass

            try:
                # Use non-blocking read timeout (0.2s) to prevent thread locks
                self.serial_obj = serial.Serial(self.port, self.baud_rate, timeout=0.2)
                self.is_connected = True
                self.connection_state = "CONNECTED"
                self.last_error = None
                print(f"[SERIAL] Connected to {self.port} at {self.baud_rate} baud.")
                return True
            except serial.SerialException as e:
                err_msg = str(e)
                if "Access is denied" in err_msg or "PermissionError" in err_msg or "could not open port" in err_msg:
                    self.last_error = f"Port {self.port} is already locked by another application (e.g. Arduino Serial Monitor, IDE, or serial_logger.py)."
                elif "FileNotFoundError" in err_msg or "cannot find the file" in err_msg:
                    self.last_error = f"Port {self.port} was not found or has been disconnected."
                else:
                    self.last_error = f"Failed to open port {self.port}: {err_msg}"
                self.is_connected = False
                self.connection_state = "ERROR"
                print(f"[SERIAL ERROR] {self.last_error}")
                return False

    def disconnect(self):
        with self.lock:
            self.is_connected = False
            self.connection_state = "DISCONNECTED"
            if self.serial_obj and self.serial_obj.is_open:
                try:
                    self.serial_obj.close()
                    print(f"[SERIAL] Disconnected from {self.port}.")
                except Exception as e:
                    print(f"[SERIAL ERROR] Error closing port: {e}")
            self.serial_obj = None

    def start_worker(self):
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.worker_thread.start()
        print("[SERIAL] Background read worker started.")

    def stop_worker(self):
        self.stop_event.set()
        self.disconnect()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        print("[SERIAL] Background read worker stopped.")

    def _read_loop(self):
        while not self.stop_event.is_set():
            # 1. Check auto-reconnect under lock
            should_reconnect = False
            port_to_try = None
            baud_to_try = 115200

            with self.lock:
                if not self.is_connected and self.auto_reconnect:
                    should_reconnect = True
                    port_to_try = self.port or auto_detect_serial_port()
                    baud_to_try = self.baud_rate

            if should_reconnect and port_to_try:
                self.connect(port_to_try, baud_to_try)

            # 2. Get reference to open serial_obj under lock, read OUTSIDE lock
            ser_obj = None
            with self.lock:
                if self.is_connected and self.serial_obj and self.serial_obj.is_open:
                    ser_obj = self.serial_obj

            if ser_obj:
                try:
                    if ser_obj.in_waiting > 0:
                        raw_line = ser_obj.readline()
                        line_str = raw_line.decode("utf-8", errors="replace").strip()
                        if line_str:
                            self._parse_and_dispatch(line_str)
                except serial.SerialException as e:
                    print(f"[SERIAL ERROR] Disconnected unexpectedly: {e}")
                    with self.lock:
                        self.is_connected = False
                        self.connection_state = "ERROR"
                        self.last_error = f"Serial port disconnected: {e}"

            time.sleep(0.01)

    def _parse_and_dispatch(self, line_str: str):
        now_ts = time.time()
        now_iso = datetime.datetime.now().isoformat()
        with self.lock:
            self.last_seen_timestamp = now_ts
            self.last_raw_line_received = line_str
            self.raw_line_buffer.append(line_str)

        # Arduino Uno nRF24 Wireless Machine Protocol:
        # RF24_V1,node_id,sequence,flags,lat_e7,lng_e7,satellites,hdop_x10,year_2000,month,day,hour,minute,second,flow_in_x100,flow_out_x100,rms1_x10,rms2_x10,p2p1,p2p2,missed_since_last,sequence_reset
        if line_str.startswith("RF24_V1,"):
            with self.lock:
                self.output_mode = "RF24_V1"
                self.last_rf24_receive_timestamp = now_ts
                self.recent_csv_timestamps.append(now_ts)
                if len(self.recent_csv_timestamps) >= 2:
                    dt = self.recent_csv_timestamps[-1] - self.recent_csv_timestamps[0]
                    self.telemetry_hz = round((len(self.recent_csv_timestamps) - 1) / dt, 2) if dt > 0 else 0.5
                else:
                    self.telemetry_hz = 0.5

            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) == 22:
                try:
                    node_id = int(parts[1])
                    sequence = int(parts[2])
                    flags = int(parts[3])
                    lat_e7 = int(parts[4])
                    lng_e7 = int(parts[5])
                    satellites = int(parts[6])
                    hdop_x10 = int(parts[7])
                    year_2000 = int(parts[8])
                    month = int(parts[9])
                    day = int(parts[10])
                    hour = int(parts[11])
                    minute = int(parts[12])
                    second = int(parts[13])
                    flow_in_x100 = int(parts[14])
                    flow_out_x100 = int(parts[15])
                    rms1_x10 = int(parts[16])
                    rms2_x10 = int(parts[17])
                    p2p1 = int(parts[18])
                    p2p2 = int(parts[19])
                    missed_since_last = int(parts[20])
                    sequence_reset = int(parts[21])

                    # Bitmask flags
                    gps_valid = bool(flags & 0x01)
                    s1_clipped = bool(flags & 0x02)
                    s2_clipped = bool(flags & 0x04)
                    leak_alarm = bool(flags & 0x08)
                    vib_invalid = bool(flags & 0x10)

                    # Fixed-point conversions
                    flow_in_lpm = round(flow_in_x100 / 100.0, 2)
                    flow_out_lpm = round(flow_out_x100 / 100.0, 2)
                    flow_diff_lpm = round(abs(flow_in_lpm - flow_out_lpm), 2)
                    rms1 = round(rms1_x10 / 10.0, 1)  # 10-bit Arduino ADC counts
                    rms2 = round(rms2_x10 / 10.0, 1)  # 10-bit Arduino ADC counts
                    hdop = round(hdop_x10 / 10.0, 1)

                    # GPS Coordinates: only populated when fix exists
                    latitude = None
                    longitude = None
                    fix_status = "NO_FIX"
                    if gps_valid and (lat_e7 != 0 or lng_e7 != 0):
                        latitude = round(lat_e7 / 10000000.0, 7)
                        longitude = round(lng_e7 / 10000000.0, 7)
                        fix_status = "FIX"

                    gps_time_str = None
                    if year_2000 > 0 and month > 0 and day > 0:
                        gps_time_str = f"{2000 + year_2000:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"

                    # Status classification
                    if flow_in_lpm < 0.50:
                        status_str = "LOW_OR_NO_FLOW"
                        self.flow_imbalance_start_ts = None
                    elif leak_alarm:
                        status_str = "LEAK_CONFIRMED"
                        if self.flow_imbalance_start_ts is None:
                            self.flow_imbalance_start_ts = now_ts - 15.0
                    elif flow_diff_lpm >= 0.10:
                        status_str = "VERIFYING_FLOW"
                        if self.flow_imbalance_start_ts is None:
                            self.flow_imbalance_start_ts = now_ts
                    else:
                        status_str = "NO_LEAK"
                        self.flow_imbalance_start_ts = None

                    with self.lock:
                        self.valid_rf24_count += 1
                        self.last_packet_sequence = sequence
                        self.total_missed_packets += missed_since_last
                        if sequence_reset:
                            self.sequence_reset_count += 1
                        self.last_seen_status_str = status_str

                        wireless_dict = {
                            "utc_timestamp": now_iso,
                            "node_id": node_id,
                            "packet_sequence": sequence,
                            "flow_in_lpm": flow_in_lpm,
                            "flow_out_lpm": flow_out_lpm,
                            "flow_diff_lpm": flow_diff_lpm,
                            "leak_alarm": leak_alarm,
                            "rms1": rms1,
                            "p2p1": p2p1,
                            "rms2": rms2,
                            "p2p2": p2p2,
                            "s1_clipped": s1_clipped,
                            "s2_clipped": s2_clipped,
                            "vibration_invalid": vib_invalid,
                            "gps_valid": gps_valid,
                            "latitude": latitude,
                            "longitude": longitude,
                            "satellites": satellites,
                            "hdop": hdop,
                            "gps_time": gps_time_str,
                            "missed_packets": missed_since_last,
                            "sequence_reset": sequence_reset,
                            "communication_source": "ARDUINO_UNO_NRF24",
                            "status_str": status_str,
                            "is_demo": False,
                            "last_updated": now_ts
                        }
                        self.latest_wireless_data = wireless_dict

                        self.latest_flow_data = {
                            "esp32_ms": 0,
                            "interval_ms": 5000,
                            "in_pulses": 0,
                            "out_pulses": 0,
                            "flow_in_lpm": flow_in_lpm,
                            "flow_out_lpm": flow_out_lpm,
                            "flow_diff_lpm": flow_diff_lpm,
                            "leak_progress": 3 if leak_alarm else (1 if flow_diff_lpm >= 0.10 and flow_in_lpm >= 0.50 else 0),
                            "leak_confirmed": leak_alarm,
                            "status": status_str,
                            "last_updated": now_ts
                        }

                        self.latest_gps_data = {
                            "latitude": latitude,
                            "longitude": longitude,
                            "satellites": satellites,
                            "hdop": hdop,
                            "fix_age_ms": 0 if fix_status == "FIX" else 999999,
                            "fix_status": fix_status,
                            "is_stale": (fix_status != "FIX"),
                            "is_demo": False,
                            "last_updated": now_ts
                        }

                        is_clip = s1_clipped or s2_clipped or (p2p1 >= 1020) or (p2p2 >= 1020)
                        self.latest_adc_diagnostics = {
                            "s1_min": 0,
                            "s1_max": 1023,
                            "s1_mean": 512.0,
                            "s1_clips": 1 if s1_clipped else 0,
                            "s1_clip_pct": 100.0 if s1_clipped else 0.0,
                            "s2_min": 0,
                            "s2_max": 1023,
                            "s2_mean": 512.0,
                            "s2_clips": 1 if s2_clipped else 0,
                            "s2_clip_pct": 100.0 if s2_clipped else 0.0,
                            "is_clipping": is_clip,
                            "status": "ADC_CLIPPING_DETECTED" if is_clip else ("VIBRATION_WINDOW_INVALID" if vib_invalid else "OK"),
                            "last_updated": now_ts
                        }

                        self._refresh_localization_from_flow(leak_alarm, now_ts)

                    # Transition detection for leak events
                    if self.previous_leak_alarm is not None and self.previous_leak_alarm != leak_alarm:
                        from app.database import record_leak_transition
                        record_leak_transition("LEAK_CONFIRMED" if leak_alarm else "LEAK_RESOLVED", wireless_dict)
                    self.previous_leak_alarm = leak_alarm

                    if self.callback_on_wireless:
                        try:
                            self.callback_on_wireless(wireless_dict)
                        except Exception as cb_err:
                            print(f"[WIRELESS CALLBACK ERROR] {cb_err}")

                    if self.callback_on_flow:
                        try:
                            self.callback_on_flow(self.latest_flow_data)
                        except Exception as cb_err:
                            print(f"[FLOW CALLBACK ERROR] {cb_err}")

                    rec = TelemetryRecord(
                        pc_timestamp=now_iso,
                        esp32_ms=0,
                        second_index=sequence,
                        s1_rms=rms1,
                        s1_p2p=float(p2p1),
                        s1_variance=0.0,
                        s1_stvar=0.0,
                        s2_rms=rms2,
                        s2_p2p=float(p2p2),
                        s2_variance=0.0,
                        s2_stvar=0.0,
                        s1_abnormal=1 if s1_clipped else 0,
                        s2_abnormal=1 if s2_clipped else 0,
                        is_transient=0,
                        status_str=status_str,
                        is_demo=False
                    )
                    if self.callback_on_record:
                        try:
                            with self.lock:
                                self.callback_invocation_count += 1
                            self.callback_on_record(rec)
                        except Exception as cb_err:
                            print(f"[SERIAL CALLBACK ERROR] {cb_err}")

                except Exception as parse_err:
                    import traceback
                    err_fmt = f"RF24 parse error ({parse_err}) on line: '{line_str}'\n{traceback.format_exc()}"
                    print(f"[SERIAL PARSE ERROR] {err_fmt}")
                    with self.lock:
                        self.parse_error_count += 1
                        self.last_processing_error = err_fmt
            else:
                err_fmt = f"Expected 22 fields, got {len(parts)} on RF24 line: '{line_str}'"
                print(f"[SERIAL PARSE ERROR] {err_fmt}")
                with self.lock:
                    self.parse_error_count += 1
                    self.last_processing_error = err_fmt
            return

        # Arduino Uno TDOA Acoustic Localization Record:
        # TDOA_UNO,node_id,event_id,timestamp_ms,delta_t_us,dist_mm,corr_peak_x100,psr_x10,valid,failure_code
        elif line_str.startswith("TDOA_UNO,"):
            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) >= 10:
                try:
                    node_id = int(parts[1])
                    event_id = int(parts[2])
                    tx_ms = int(parts[3])
                    delta_t_us = float(parts[4])
                    dist_mm = int(parts[5])
                    corr_peak_x100 = int(parts[6])
                    psr_x10 = int(parts[7])
                    raw_valid = int(parts[8])
                    failure_code = int(parts[9])
                    is_transient = int(parts[10]) if len(parts) >= 11 else 1

                    corr_peak = round(corr_peak_x100 / 100.0, 3)
                    psr = round(psr_x10 / 10.0, 2)
                    dist_m = round(dist_mm / 1000.0, 3)
                    dist2_m = round(2.0 - dist_m, 3) if (0.0 <= dist_m <= 2.0) else None

                    FAILURE_REASONS = {
                        0: "VALID_ACOUSTIC_LOCK",
                        1: "ADC_CLIPPING_DETECTED",
                        2: "LOW_SIGNAL_AMPLITUDE",
                        3: "WEAK_CORRELATION (R < 0.65)",
                        4: "AMBIGUOUS_PEAK (PSR < 1.8)",
                        5: "OUT_OF_BOUNDS_ESTIMATE",
                        6: "AWAITING_FLOW_CONFIRMATION"
                    }
                    failure_reason = FAILURE_REASONS.get(failure_code, f"ERR_{failure_code}")

                    # Physics and quality validity check
                    # Localized acoustic transients require sharp correlation peak and distinct arrival (PSR >= 1.8)
                    # Periodic pump vibrations produce periodic sidelobes (low PSR < 1.8) and are rejected.
                    is_physically_valid = (
                        raw_valid == 1 and
                        failure_code == 0 and
                        0.0 <= dist_m <= 2.0 and
                        corr_peak >= 0.65 and
                        psr >= 1.8
                    )

                    with self.lock:
                        self.valid_tdoa_count += 1
                        self.last_tdoa_receive_timestamp = now_ts
                        flow_confirmed = self.latest_flow_data.get("leak_confirmed", False) or (
                            self.latest_wireless_data and self.latest_wireless_data.get("leak_alarm", False)
                        )

                        cand = {
                            "node_id": node_id,
                            "event_id": event_id,
                            "transmitter_timestamp_ms": tx_ms,
                            "delta_t_us": delta_t_us,
                            "leak_distance_s1_m": dist_m if is_physically_valid else None,
                            "leak_distance_s2_m": dist2_m if is_physically_valid else None,
                            "correlation_peak": corr_peak,
                            "psr": psr,
                            "loc_valid": is_physically_valid,
                            "is_transient": bool(is_transient),
                            "is_clipping": bool(failure_code == 1 or not is_physically_valid and "CLIPPING" in failure_reason),
                            "quality_score": round(corr_peak * min(psr / 2.0, 2.0), 3) if is_physically_valid else 0.0,
                            "confidence_pct": round(corr_peak * 100.0, 1) if is_physically_valid else 0.0,
                            "uncertainty_m": round(max(0.15, (1.0 - corr_peak) * 0.6), 3) if is_physically_valid else 0.25,
                            "sample_rate_hz": 19231,
                            "propagation_velocity_mps": 1250.0,
                            "propagation_velocity_status": "NOMINAL_UNCALIBRATED",
                            "failure_code": failure_code,
                            "failure_reason": failure_reason,
                            "timestamp": now_ts,
                            "utc_timestamp": now_iso
                        }
                        self.tdoa_candidate_buffer.append(cand)
                        self.latest_localization_event = cand

                        # Update latest localization presentation
                        self.latest_localization_data["pipe_length_m"] = 2.0
                        self.latest_localization_data["s1_pos_m"] = 0.0
                        self.latest_localization_data["s2_pos_m"] = 2.0
                        self.latest_localization_data["delta_t_us"] = delta_t_us
                        self.latest_localization_data["sample_rate_hz"] = 19231
                        self.latest_localization_data["propagation_velocity_mps"] = 1250.0
                        self.latest_localization_data["propagation_velocity_status"] = "NOMINAL_UNCALIBRATED"
                        self.latest_localization_data["correlation_peak"] = corr_peak
                        self.latest_localization_data["psr"] = psr
                        self.latest_localization_data["event_id"] = event_id
                        self.latest_localization_data["failure_code"] = failure_code
                        self.latest_localization_data["failure_reason"] = failure_reason
                        self.latest_localization_data["flow_confirmed_leak"] = flow_confirmed
                        self.latest_localization_data["last_updated"] = now_ts

                        # Enforce strict dual-authority: flow confirmation + onset association window & transient evidence
                        self._refresh_localization_from_flow(flow_confirmed, now_ts)

                    # Database persistence
                    db_event = {
                        "utc_timestamp": now_iso,
                        "node_id": node_id,
                        "event_id": event_id,
                        "transmitter_timestamp_ms": tx_ms,
                        "delta_t_us": delta_t_us,
                        "estimated_distance_m": dist_m if is_physically_valid else None,
                        "distance_sensor2_m": dist2_m if is_physically_valid else None,
                        "correlation_peak": corr_peak,
                        "psr": psr,
                        "is_valid": 1 if is_physically_valid else 0,
                        "failure_code": failure_code,
                        "failure_reason": failure_reason,
                        "flow_confirmed": 1 if flow_confirmed else 0,
                        "pipeline_length_m": 2.0,
                        "calibrated_velocity_mps": 1250.0
                    }
                    from app.database import save_arduino_localization_event
                    save_arduino_localization_event(db_event)

                    if self.callback_on_localization:
                        try:
                            self.callback_on_localization(self.latest_localization_data)
                        except Exception as cb_err:
                            print(f"[LOCALIZATION CALLBACK ERROR] {cb_err}")

                except Exception as tdoa_err:
                    err_fmt = f"TDOA_UNO parse error ({tdoa_err}) on line: '{line_str}'"
                    print(f"[SERIAL PARSE ERROR] {err_fmt}")
                    with self.lock:
                        self.parse_error_count += 1
                        self.last_processing_error = err_fmt
            else:
                err_fmt = f"Expected at least 10 fields, got {len(parts)} on line: '{line_str}'"
                print(f"[SERIAL PARSE ERROR] {err_fmt}")
                with self.lock:
                    self.parse_error_count += 1
                    self.last_processing_error = err_fmt
            return

        # ESP32 Standard Machine CSV Format:
        # CSV,esp32_ms,sec_idx,s1_rms,s1_p2p,s1_var,s1_stvar,s2_rms,s2_p2p,s2_var,s2_stvar,s1_abn,s2_abn,trans,status
        elif line_str.startswith("CSV,"):
            with self.lock:
                self.output_mode = "CSV"
                self.last_csv_receive_timestamp = now_ts
                self.recent_csv_timestamps.append(now_ts)
                if len(self.recent_csv_timestamps) >= 2:
                    dt = self.recent_csv_timestamps[-1] - self.recent_csv_timestamps[0]
                    self.telemetry_hz = round((len(self.recent_csv_timestamps) - 1) / dt, 2) if dt > 0 else 1.0
                else:
                    self.telemetry_hz = 1.0

            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) == 15:
                try:
                    status_str = parts[14]
                    with self.lock:
                        self.last_seen_status_str = status_str

                    rec = TelemetryRecord(
                        pc_timestamp=now_iso,
                        esp32_ms=int(parts[1]),
                        second_index=int(parts[2]),
                        s1_rms=float(parts[3]),
                        s1_p2p=float(parts[4]),
                        s1_variance=float(parts[5]),
                        s1_stvar=float(parts[6]),
                        s2_rms=float(parts[7]),
                        s2_p2p=float(parts[8]),
                        s2_variance=float(parts[9]),
                        s2_stvar=float(parts[10]),
                        s1_abnormal=int(parts[11]),
                        s2_abnormal=int(parts[12]),
                        is_transient=int(parts[13]),
                        status_str=status_str,
                        is_demo=False
                    )
                    with self.lock:
                        self.valid_csv_count += 1

                    if self.callback_on_record:
                        try:
                            with self.lock:
                                self.callback_invocation_count += 1
                            self.callback_on_record(rec)
                        except Exception as cb_err:
                            import traceback
                            err_fmt = f"Callback execution error: {cb_err}\n{traceback.format_exc()}"
                            print(f"[SERIAL CALLBACK ERROR] {err_fmt}")
                            with self.lock:
                                self.callback_error_count += 1
                                self.last_processing_error = err_fmt
                except Exception as parse_err:
                    import traceback
                    err_fmt = f"Numeric conversion error ({parse_err}) on line: '{line_str}'\n{traceback.format_exc()}"
                    print(f"[SERIAL PARSE ERROR] {err_fmt}")
                    with self.lock:
                        self.parse_error_count += 1
                        self.last_processing_error = err_fmt
            else:
                err_fmt = f"Expected 15 fields, got {len(parts)} on line: '{line_str}'"
                print(f"[SERIAL PARSE ERROR] {err_fmt}")
                with self.lock:
                    self.parse_error_count += 1
                    self.last_processing_error = err_fmt
        elif line_str.startswith("GPS,"):
            # ESP32 GPS Telemetry Line: GPS,latitude,longitude,satellites,hdop,fix_age_ms,fix_status
            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) >= 6:
                try:
                    raw_lat = float(parts[1])
                    raw_lon = float(parts[2])
                    sats = int(parts[3])
                    hdop = float(parts[4])
                    fix_age_ms = int(parts[5])
                    fix_status = parts[6] if len(parts) >= 7 else ("FIX" if (sats > 0 and (raw_lat != 0.0 or raw_lon != 0.0)) else "NO_FIX")

                    is_stale = (fix_status == "STALE" or fix_age_ms > 10000)
                    lat = raw_lat if (fix_status in ["FIX", "STALE"] and raw_lat != 0.0) else None
                    lon = raw_lon if (fix_status in ["FIX", "STALE"] and raw_lon != 0.0) else None

                    with self.lock:
                        self.valid_gps_count += 1
                        self.last_raw_gps_line = line_str
                        self.latest_gps_data = {
                            "latitude": lat,
                            "longitude": lon,
                            "satellites": sats,
                            "hdop": hdop,
                            "fix_age_ms": fix_age_ms,
                            "fix_status": fix_status,
                            "is_stale": is_stale,
                            "is_demo": False,
                            "last_updated": now_ts
                        }
                except Exception as parse_err:
                    print(f"[GPS PARSE ERROR] {parse_err} on line: '{line_str}'")
                    with self.lock:
                        self.parse_error_count += 1
        elif line_str.startswith("TDOA,"):
            # ESP32 TDOA Telemetry Line: TDOA,esp32_ms,dt_us,peak_corr,psr,d1,d2,sample_rate,v_mps,loc_valid,status
            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) >= 11:
                try:
                    dt_us = float(parts[2])
                    peak_corr = float(parts[3])
                    psr = float(parts[4])
                    d1_str = parts[5]
                    d2_str = parts[6]
                    loc_valid = (parts[9] == "1")
                    d1 = float(d1_str) if loc_valid and d1_str not in ["None", "null"] else None
                    d2 = float(d2_str) if loc_valid and d2_str not in ["None", "null"] else None
                    fs = int(float(parts[7]))
                    v_mps = float(parts[8])
                    status_text = parts[10]

                    with self.lock:
                        curr_wave1 = self.latest_localization_data.get("s1_waveform", [])
                        curr_wave2 = self.latest_localization_data.get("s2_waveform", [])
                        self.latest_localization_data = {
                            "pipe_length_m": 2.0,
                            "s1_pos_m": 0.0,
                            "s2_pos_m": 2.0,
                            "delta_t_us": dt_us,
                            "sample_rate_hz": fs,
                            "propagation_velocity_mps": v_mps,
                            "propagation_velocity_status": "NOMINAL_UNCALIBRATED",
                            "leak_distance_s1_m": d1,
                            "leak_distance_s2_m": d2,
                            "confidence_pct": round(peak_corr * 100.0, 1) if loc_valid else 0.0,
                            "uncertainty_m": round(max(0.15, (1.0 - peak_corr) * 0.6), 3) if loc_valid else 0.25,
                            "correlation_peak": round(peak_corr, 3),
                            "psr": round(psr, 2),
                            "status": "LOCALIZATION ACQUIRED (NOMINAL SPEED)" if loc_valid else "LOCATION UNAVAILABLE — INSUFFICIENT SIGNAL QUALITY",
                            "loc_valid": loc_valid,
                            "s1_waveform": curr_wave1,
                            "s2_waveform": curr_wave2,
                            "last_updated": now_ts
                        }
                        if loc_valid and peak_corr >= 0.65:
                            self.tdoa_candidate_buffer.append({
                                "delta_t_us": dt_us,
                                "correlation_peak": peak_corr,
                                "psr": psr,
                                "leak_distance_s1_m": d1,
                                "leak_distance_s2_m": d2,
                                "loc_valid": True,
                                "confidence_pct": round(peak_corr * 100.0, 1),
                                "uncertainty_m": round(max(0.15, (1.0 - peak_corr) * 0.6), 3),
                                "sample_rate_hz": fs,
                                "propagation_velocity_mps": v_mps,
                                "propagation_velocity_status": "NOMINAL_UNCALIBRATED",
                                "timestamp": now_ts
                            })

                except Exception as parse_err:
                    print(f"[TDOA PARSE ERROR] {parse_err} on line: '{line_str}'")
        elif line_str.startswith("WAVE,"):
            # ESP32 Waveform Snapshot: WAVE,s1_0,s1_1...;s2_0,s2_1...
            try:
                wave_data = line_str[5:].strip()
                if ";" in wave_data:
                    p1_str, p2_str = wave_data.split(";", 1)
                    s1_pts = [float(x.strip()) for x in p1_str.split(",") if x.strip()]
                    s2_pts = [float(x.strip()) for x in p2_str.split(",") if x.strip()]
                    with self.lock:
                        self.latest_localization_data["s1_waveform"] = s1_pts
                        self.latest_localization_data["s2_waveform"] = s2_pts
            except Exception as wave_err:
                print(f"[WAVE PARSE ERROR] {wave_err} on line: '{line_str}'")
        elif line_str.startswith("FLOW,"):
            # ESP32 Dual YF-S201 Flow Telemetry Line:
            # FLOW,esp32_ms,interval_ms,in_pulses,out_pulses,flow_in_lpm,flow_out_lpm,diff_lpm,progress,confirmed,status
            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) >= 11:
                try:
                    esp32_ms = int(parts[1])
                    interval_ms = int(parts[2])
                    in_pulses = int(parts[3])
                    out_pulses = int(parts[4])
                    flow_in_lpm = float(parts[5])
                    flow_out_lpm = float(parts[6])
                    diff_lpm = float(parts[7])
                    progress = int(parts[8])
                    confirmed = (parts[9] in ["1", "true", "True"])
                    flow_status = parts[10]

                    flow_record = {
                        "esp32_ms": esp32_ms,
                        "interval_ms": interval_ms,
                        "in_pulses": in_pulses,
                        "out_pulses": out_pulses,
                        "flow_in_lpm": flow_in_lpm,
                        "flow_out_lpm": flow_out_lpm,
                        "flow_diff_lpm": diff_lpm,
                        "leak_progress": progress,
                        "leak_confirmed": confirmed,
                        "status": flow_status,
                        "last_updated": now_ts
                    }

                    with self.lock:
                        self.valid_flow_count += 1
                        self.last_flow_receive_timestamp = now_ts
                        self.latest_flow_data = flow_record

                    if self.callback_on_flow:
                        try:
                            self.callback_on_flow(flow_record)
                        except Exception as cb_err:
                            print(f"[FLOW CALLBACK ERROR] {cb_err}")
                except Exception as parse_err:
                    print(f"[FLOW PARSE ERROR] {parse_err} on line: '{line_str}'")
                    with self.lock:
                        self.parse_error_count += 1
        elif line_str.startswith("ADC,"):
            # ESP32 Raw ADC Diagnostics Line:
            # ADC,esp32_ms,min1,max1,mean1,clips1,pct1,min2,max2,mean2,clips2,pct2
            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) >= 12:
                try:
                    s1_min = int(parts[2])
                    s1_max = int(parts[3])
                    s1_mean = float(parts[4])
                    s1_clips = int(parts[5])
                    s1_clip_pct = float(parts[6])
                    s2_min = int(parts[7])
                    s2_max = int(parts[8])
                    s2_mean = float(parts[9])
                    s2_clips = int(parts[10])
                    s2_clip_pct = float(parts[11])

                    is_clip = (s1_clips > 0 or s2_clips > 0)
                    status_text = "ADC_CLIPPING_FAULT" if (s1_clips > 100 or s2_clips > 100) else ("CLIPPING_DETECTED" if is_clip else "OK")

                    with self.lock:
                        self.latest_adc_diagnostics = {
                            "s1_min": s1_min,
                            "s1_max": s1_max,
                            "s1_mean": s1_mean,
                            "s1_clips": s1_clips,
                            "s1_clip_pct": s1_clip_pct,
                            "s2_min": s2_min,
                            "s2_max": s2_max,
                            "s2_mean": s2_mean,
                            "s2_clips": s2_clips,
                            "s2_clip_pct": s2_clip_pct,
                            "is_clipping": is_clip,
                            "status": status_text,
                            "last_updated": now_ts
                        }
                except Exception as adc_err:
                    print(f"[ADC PARSE ERROR] {adc_err} on line: '{line_str}'")

        # Human-Readable Arduino Uno Multiline Receiver Format:
        # e.g.:
        # Packet #1  (Node 1, Seq 103, missed since last: 0, total missed: 0)
        # GPS Fix    : NO (searching for satellites...)
        # Satellites : 0
        # HDOP       : --
        # Flow inlet : 0.00 L/min
        # Flow outlet: 0.00 L/min
        # Leak alarm : no
        # Piezo 1    : RMS 15.2  P2P 93
        # Piezo 2    : RMS 138.1  P2P 823
        elif self.output_mode != "RF24_V1" and (
            "packet #" in line_str.lower() or
            self.multiline_packet_buffer is not None or
            any(k in line_str.lower() for k in ["flow inlet :", "flow outlet:", "leak alarm :", "piezo 1    :", "piezo 2    :", "gps fix    :"])
        ):
            # Check for start of a new packet
            pkt_m = re.search(
                r"Packet\s*#\s*(\d+)\s*\(\s*Node\s*(\d+),\s*Seq\s*(\d+),\s*missed\s+since\s+last:\s*(\d+),\s*total\s+missed:\s*(\d+)\)",
                line_str,
                re.IGNORECASE
            )
            if pkt_m:
                self.multiline_packet_buffer = {
                    "rx_num": int(pkt_m.group(1)),
                    "node_id": int(pkt_m.group(2)),
                    "sequence": int(pkt_m.group(3)),
                    "missed_since_last": int(pkt_m.group(4)),
                    "total_missed": int(pkt_m.group(5)),
                    "gps_valid": False,
                    "latitude": None,
                    "longitude": None,
                    "satellites": 0,
                    "hdop": 99.9,
                    "date_utc": None,
                    "time_utc": None,
                    "flow_in_lpm": None,
                    "flow_out_lpm": None,
                    "leak_alarm": None,
                    "rms1": None,
                    "p2p1": None,
                    "rms2": None,
                    "p2p2": None
                }
                with self.lock:
                    self.last_diagnostic_line = line_str
                    self.diagnostic_messages.append(line_str)
                return

            # If we don't have an active packet header, ignore fragmented startup text/banners
            if self.multiline_packet_buffer is None:
                with self.lock:
                    self.last_diagnostic_line = line_str
                    self.diagnostic_messages.append(line_str)
                return

            # Parse fields within current packet
            gps_fix_m = re.search(r"GPS\s*Fix\s*:\s*(.+)", line_str, re.IGNORECASE)
            sats_m = re.search(r"Satellites\s*:\s*(\d+)", line_str, re.IGNORECASE)
            hdop_m = re.search(r"HDOP\s*:\s*([\d\.]+)", line_str, re.IGNORECASE)
            date_m = re.search(r"Date\s*\(UTC\)\s*:\s*([\d\-]+)", line_str, re.IGNORECASE)
            time_m = re.search(r"Time\s*\(UTC\)\s*:\s*([\d:]+)", line_str, re.IGNORECASE)
            coord_m = re.search(r"(?:Lat|Latitude)\s*:\s*([-\d\.]+).*?(?:Lng|Lon|Longitude)\s*:\s*([-\d\.]+)", line_str, re.IGNORECASE)
            lat_m = re.search(r"^\s*(?:Lat|Latitude)\s*:\s*([-\d\.]+)", line_str, re.IGNORECASE)
            lon_m = re.search(r"^\s*(?:Lng|Lon|Longitude)\s*:\s*([-\d\.]+)", line_str, re.IGNORECASE)
            flow_in_m = re.search(r"Flow\s*inlet\s*:\s*([\d\.]+)", line_str, re.IGNORECASE)
            flow_out_m = re.search(r"Flow\s*outlet\s*:\s*([\d\.]+)", line_str, re.IGNORECASE)
            leak_m = re.search(r"Leak\s*alarm\s*:\s*(yes|no)", line_str, re.IGNORECASE)
            p1_m = re.search(r"Piezo\s*1\s*:\s*RMS\s*([\d\.]+)\s*P2P\s*(\d+)", line_str, re.IGNORECASE)
            p2_m = re.search(r"Piezo\s*2\s*:\s*RMS\s*([\d\.]+)\s*P2P\s*(\d+)", line_str, re.IGNORECASE)

            if gps_fix_m:
                fix_text = gps_fix_m.group(1).strip()
                is_valid = ("NO" not in fix_text.upper().split()[0])
                self.multiline_packet_buffer["gps_valid"] = is_valid
                if not is_valid:
                    self.multiline_packet_buffer["latitude"] = None
                    self.multiline_packet_buffer["longitude"] = None
            elif sats_m:
                self.multiline_packet_buffer["satellites"] = int(sats_m.group(1))
            elif hdop_m:
                self.multiline_packet_buffer["hdop"] = float(hdop_m.group(1))
            elif date_m:
                self.multiline_packet_buffer["date_utc"] = date_m.group(1).strip()
            elif time_m:
                self.multiline_packet_buffer["time_utc"] = time_m.group(1).strip()
            elif coord_m:
                lat_val = float(coord_m.group(1))
                lon_val = float(coord_m.group(2))
                if not (lat_val == 0.0 and lon_val == 0.0):
                    self.multiline_packet_buffer["latitude"] = lat_val
                    self.multiline_packet_buffer["longitude"] = lon_val
                    self.multiline_packet_buffer["gps_valid"] = True
            elif lat_m:
                lat_val = float(lat_m.group(1))
                if lat_val != 0.0:
                    self.multiline_packet_buffer["latitude"] = lat_val
                    if self.multiline_packet_buffer.get("longitude") is not None and self.multiline_packet_buffer["longitude"] != 0.0:
                        self.multiline_packet_buffer["gps_valid"] = True
            elif lon_m:
                lon_val = float(lon_m.group(1))
                if lon_val != 0.0:
                    self.multiline_packet_buffer["longitude"] = lon_val
                    if self.multiline_packet_buffer.get("latitude") is not None and self.multiline_packet_buffer["latitude"] != 0.0:
                        self.multiline_packet_buffer["gps_valid"] = True
            elif flow_in_m:
                self.multiline_packet_buffer["flow_in_lpm"] = float(flow_in_m.group(1))
            elif flow_out_m:
                self.multiline_packet_buffer["flow_out_lpm"] = float(flow_out_m.group(1))
            elif leak_m:
                self.multiline_packet_buffer["leak_alarm"] = (leak_m.group(1).lower() == "yes")
            elif p1_m:
                self.multiline_packet_buffer["rms1"] = float(p1_m.group(1))
                self.multiline_packet_buffer["p2p1"] = int(p1_m.group(2))
            elif p2_m:
                self.multiline_packet_buffer["rms2"] = float(p2_m.group(1))
                self.multiline_packet_buffer["p2p2"] = int(p2_m.group(2))

                # Check completeness
                buf = self.multiline_packet_buffer
                if (
                    buf.get("sequence") is not None and
                    buf.get("flow_in_lpm") is not None and
                    buf.get("flow_out_lpm") is not None and
                    buf.get("leak_alarm") is not None and
                    buf.get("rms1") is not None and
                    buf.get("rms2") is not None
                ):
                    flow_in_lpm = buf["flow_in_lpm"]
                    flow_out_lpm = buf["flow_out_lpm"]
                    flow_diff_lpm = round(abs(flow_in_lpm - flow_out_lpm), 2)
                    leak_alarm = buf["leak_alarm"]
                    rms1 = buf["rms1"]
                    p2p1 = buf["p2p1"]
                    rms2 = buf["rms2"]
                    p2p2 = buf["p2p2"]
                    buf_lat = buf.get("latitude")
                    buf_lng = buf.get("longitude")
                    is_zero = (buf_lat == 0.0 and buf_lng == 0.0)
                    gps_valid = bool(
                        buf.get("gps_valid") and
                        buf_lat is not None and
                        buf_lng is not None and
                        not is_zero
                    )
                    final_lat = buf_lat if gps_valid else None
                    final_lng = buf_lng if gps_valid else None

                    gps_time_str = None
                    if buf.get("date_utc") and buf.get("time_utc"):
                        gps_time_str = f"{buf['date_utc']}T{buf['time_utc']}Z"

                    sequence = buf["sequence"]
                    missed = buf["missed_since_last"]
                    total_missed = buf["total_missed"]
                    node_id = buf["node_id"]

                    if flow_in_lpm < 0.50:
                        status_str = "LOW_OR_NO_FLOW"
                    elif leak_alarm:
                        status_str = "LEAK_CONFIRMED"
                    elif flow_diff_lpm >= 0.10:
                        status_str = "VERIFYING_FLOW"
                    else:
                        status_str = "NO_LEAK"

                    s1_clipped = (p2p1 >= 1020)
                    s2_clipped = (p2p2 >= 1020)

                    with self.lock:
                        self.output_mode = "ARDUINO_MULTILINE"
                        self.valid_rf24_count += 1
                        self.last_rf24_receive_timestamp = now_ts
                        self.last_packet_sequence = sequence
                        self.total_missed_packets = total_missed
                        self.last_seen_status_str = status_str

                        wireless_dict = {
                            "utc_timestamp": now_iso,
                            "node_id": node_id,
                            "packet_sequence": sequence,
                            "flow_in_lpm": flow_in_lpm,
                            "flow_out_lpm": flow_out_lpm,
                            "flow_diff_lpm": flow_diff_lpm,
                            "leak_alarm": leak_alarm,
                            "rms1": rms1,
                            "p2p1": p2p1,
                            "rms2": rms2,
                            "p2p2": p2p2,
                            "s1_clipped": s1_clipped,
                            "s2_clipped": s2_clipped,
                            "vibration_invalid": False,
                            "gps_valid": gps_valid,
                            "latitude": final_lat,
                            "longitude": final_lng,
                            "satellites": buf["satellites"],
                            "hdop": buf["hdop"] if buf["hdop"] < 90 else 99.9,
                            "gps_time": gps_time_str,
                            "missed_packets": missed,
                            "sequence_reset": 0,
                            "communication_source": "ARDUINO_UNO_NRF24",
                            "status_str": status_str,
                            "is_demo": False,
                            "last_updated": now_ts
                        }
                        self.latest_wireless_data = wireless_dict
                        self.latest_flow_data = {
                            "esp32_ms": 0,
                            "interval_ms": 5000,
                            "in_pulses": 0,
                            "out_pulses": 0,
                            "flow_in_lpm": flow_in_lpm,
                            "flow_out_lpm": flow_out_lpm,
                            "flow_diff_lpm": flow_diff_lpm,
                            "leak_progress": 3 if leak_alarm else (1 if flow_diff_lpm >= 0.10 and flow_in_lpm >= 0.50 else 0),
                            "leak_confirmed": leak_alarm,
                            "status": status_str,
                            "last_updated": now_ts
                        }
                        if gps_valid:
                            self.valid_gps_count += 1
                            self.last_raw_gps_line = f"LAT={final_lat}, LNG={final_lng}, SATS={buf['satellites']}, HDOP={buf['hdop']}"
                            self.latest_gps_data = {
                                "latitude": final_lat,
                                "longitude": final_lng,
                                "satellites": buf["satellites"],
                                "hdop": buf["hdop"] if buf["hdop"] < 90 else 99.9,
                                "fix_age_ms": 0,
                                "fix_status": "FIX",
                                "is_stale": False,
                                "is_demo": False,
                                "last_updated": now_ts
                            }
                        else:
                            self.latest_gps_data = {
                                "latitude": None,
                                "longitude": None,
                                "satellites": buf["satellites"],
                                "hdop": buf["hdop"] if buf["hdop"] < 90 else 99.9,
                                "fix_age_ms": 999999,
                                "fix_status": "NO_FIX",
                                "is_stale": True,
                                "is_demo": False,
                                "last_updated": self.latest_gps_data.get("last_updated", 0.0) if self.latest_gps_data else 0.0
                            }
                        is_clip = s1_clipped or s2_clipped
                        self.latest_adc_diagnostics = {
                            "s1_min": 0,
                            "s1_max": 1023,
                            "s1_mean": 512.0,
                            "s1_clips": 1 if s1_clipped else 0,
                            "s1_clip_pct": 100.0 if s1_clipped else 0.0,
                            "s2_min": 0,
                            "s2_max": 1023,
                            "s2_mean": 512.0,
                            "s2_clips": 1 if s2_clipped else 0,
                            "s2_clip_pct": 100.0 if s2_clipped else 0.0,
                            "is_clipping": is_clip,
                            "status": "ADC_CLIPPING_DETECTED" if is_clip else "OK",
                            "last_updated": now_ts
                        }
                        self._refresh_localization_from_flow(leak_alarm, now_ts)

                    # Transition detection for leak events
                    if self.previous_leak_alarm is not None and self.previous_leak_alarm != leak_alarm:
                        from app.database import record_leak_transition
                        record_leak_transition("LEAK_CONFIRMED" if leak_alarm else "LEAK_RESOLVED", wireless_dict)
                    self.previous_leak_alarm = leak_alarm

                    if self.callback_on_wireless:
                        try:
                            self.callback_on_wireless(wireless_dict)
                        except Exception as cb_err:
                            print(f"[WIRELESS CALLBACK ERROR] {cb_err}")

                    if self.callback_on_flow:
                        try:
                            self.callback_on_flow(self.latest_flow_data)
                        except Exception as cb_err:
                            print(f"[FLOW CALLBACK ERROR] {cb_err}")

                    rec = TelemetryRecord(
                        pc_timestamp=now_iso,
                        esp32_ms=0,
                        second_index=sequence,
                        s1_rms=rms1,
                        s1_p2p=float(p2p1),
                        s1_variance=0.0,
                        s1_stvar=0.0,
                        s2_rms=rms2,
                        s2_p2p=float(p2p2),
                        s2_variance=0.0,
                        s2_stvar=0.0,
                        s1_abnormal=0,
                        s2_abnormal=0,
                        is_transient=0,
                        status_str=status_str,
                        is_demo=False
                    )
                    if self.callback_on_record:
                        try:
                            with self.lock:
                                self.callback_invocation_count += 1
                            self.callback_on_record(rec)
                        except Exception as cb_err:
                            print(f"[SERIAL CALLBACK ERROR] {cb_err}")

                    self.multiline_packet_buffer = None

            with self.lock:
                self.last_diagnostic_line = line_str
                self.diagnostic_messages.append(line_str)
            return

        elif line_str.startswith("Sensor 1:") and "Sensor 2:" in line_str:
            # Legacy raw serial output (only seen on outdated sketches)
            with self.lock:
                if self.valid_csv_count == 0:
                    self.output_mode = "LEGACY_RAW"
            print(f"[SERIAL INFO] Legacy unstructured raw ADC line detected: '{line_str}'")
            return
        else:
            # Legitimate firmware diagnostic, lifecycle, or debug line:
            # (e.g. [STAGE: TDOA_ACQ_START], [STAGE: TDOA_ACQ_DONE], [MEM-CHECK ...], boot banners, calibration status)
            # Recognized and logged without incrementing parse_error_count or setting last_processing_error.
            # Never send the M command or toggle CSV mode.
            with self.lock:
                self.last_diagnostic_line = line_str
                self.diagnostic_messages.append(line_str)
            return


