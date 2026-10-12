"""
SQLite Database Storage Manager for AquaGuard AI
"""
import sqlite3
import datetime
from typing import List, Optional, Dict, Any
from app.config import DB_PATH
from app.models import TelemetryRecord, WindowDecisionModel, EventRecordModel


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Telemetry records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pc_timestamp TEXT NOT NULL,
        esp32_ms INTEGER,
        second_index INTEGER,
        s1_rms REAL,
        s1_p2p REAL,
        s1_variance REAL,
        s1_stvar REAL,
        s2_rms REAL,
        s2_p2p REAL,
        s2_variance REAL,
        s2_stvar REAL,
        s1_abnormal INTEGER,
        s2_abnormal INTEGER,
        is_transient INTEGER,
        status_str TEXT,
        is_demo INTEGER DEFAULT 0
    )
    """)

    # 60-second window decisions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS window_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        window_index INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        decision TEXT NOT NULL,
        reasoning TEXT NOT NULL,
        s1_abnormal_count INTEGER,
        s2_abnormal_count INTEGER,
        s1_max_seq INTEGER,
        s2_max_seq INTEGER,
        s1_med_rms REAL,
        s2_med_rms REAL,
        s1_var_ratio REAL,
        s2_var_ratio REAL,
        tdoa_sec REAL,
        peak_corr REAL,
        loc_valid INTEGER,
        estimated_distance_m REAL,
        is_demo INTEGER DEFAULT 0
    )
    """)

    # Historical Events
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        s1_abnormal_sec INTEGER,
        s2_abnormal_sec INTEGER,
        s1_med_rms REAL,
        s2_med_rms REAL,
        reasoning TEXT NOT NULL,
        operator_status TEXT DEFAULT 'UNCONFIRMED',
        operator_note TEXT,
        is_demo INTEGER DEFAULT 0
    )
    """)

    # Calibration logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibration_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        s1_rms_median REAL,
        s1_rms_mad REAL,
        s1_thresh REAL,
        s2_rms_median REAL,
        s2_rms_mad REAL,
        s2_thresh REAL
    )
    """)

    # Arduino Uno nRF24 Wireless Telemetry Records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wireless_telemetry_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utc_timestamp TEXT NOT NULL,
        node_id INTEGER NOT NULL,
        packet_sequence INTEGER NOT NULL,
        flow_in_lpm REAL NOT NULL,
        flow_out_lpm REAL NOT NULL,
        flow_diff_lpm REAL NOT NULL,
        leak_alarm INTEGER NOT NULL,
        rms1 REAL NOT NULL,
        p2p1 INTEGER NOT NULL,
        rms2 REAL NOT NULL,
        p2p2 INTEGER NOT NULL,
        s1_clipped INTEGER NOT NULL,
        s2_clipped INTEGER NOT NULL,
        vibration_valid INTEGER NOT NULL,
        gps_valid INTEGER NOT NULL,
        latitude REAL,
        longitude REAL,
        satellites INTEGER DEFAULT 0,
        hdop REAL DEFAULT 99.9,
        gps_time TEXT,
        missed_packets INTEGER DEFAULT 0,
        sequence_reset INTEGER DEFAULT 0,
        communication_source TEXT DEFAULT 'ARDUINO_UNO_NRF24',
        is_demo INTEGER DEFAULT 0
    )
    """)

    # Arduino Uno TDOA Acoustic Localization Events
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS arduino_localization_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utc_timestamp TEXT NOT NULL,
        node_id INTEGER NOT NULL,
        event_id INTEGER NOT NULL,
        transmitter_timestamp_ms INTEGER NOT NULL,
        delta_t_us REAL NOT NULL,
        estimated_distance_m REAL,
        distance_sensor2_m REAL,
        correlation_peak REAL NOT NULL,
        psr REAL NOT NULL,
        is_valid INTEGER NOT NULL,
        failure_code INTEGER NOT NULL,
        failure_reason TEXT,
        flow_confirmed INTEGER NOT NULL DEFAULT 0,
        pipeline_length_m REAL DEFAULT 2.0,
        calibrated_velocity_mps REAL DEFAULT 1250.0
    )
    """)

    conn.commit()
    conn.close()


def save_telemetry_record(rec: TelemetryRecord):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO telemetry_records (
            pc_timestamp, esp32_ms, second_index,
            s1_rms, s1_p2p, s1_variance, s1_stvar,
            s2_rms, s2_p2p, s2_variance, s2_stvar,
            s1_abnormal, s2_abnormal, is_transient, status_str, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec.pc_timestamp, rec.esp32_ms, rec.second_index,
            rec.s1_rms, rec.s1_p2p, rec.s1_variance, rec.s1_stvar,
            rec.s2_rms, rec.s2_p2p, rec.s2_variance, rec.s2_stvar,
            rec.s1_abnormal, rec.s2_abnormal, rec.is_transient, rec.status_str,
            1 if rec.is_demo else 0
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to save telemetry: {e}")


def save_window_decision(decision: WindowDecisionModel) -> int:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO window_decisions (
            window_index, timestamp, decision, reasoning,
            s1_abnormal_count, s2_abnormal_count, s1_max_seq, s2_max_seq,
            s1_med_rms, s2_med_rms, s1_var_ratio, s2_var_ratio,
            tdoa_sec, peak_corr, loc_valid, estimated_distance_m, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision.window_index, decision.timestamp, decision.decision, decision.reasoning,
            decision.s1_abnormal_count, decision.s2_abnormal_count, decision.s1_max_seq, decision.s2_max_seq,
            decision.s1_med_rms, decision.s2_med_rms, decision.s1_var_ratio, decision.s2_var_ratio,
            decision.tdoa_sec, decision.peak_corr, 1 if decision.loc_valid else 0,
            decision.estimated_distance_m, 1 if decision.is_demo else 0
        ))
        row_id = cursor.lastrowid
        conn.commit()

        # If decision is sustained anomaly or fault, save an event
        if "SUSTAINED VIBRATION ANOMALY" in decision.decision or "FAULT" in decision.decision:
            severity = "CRITICAL" if "SUSTAINED" in decision.decision else "HIGH"
            cursor.execute("""
            INSERT INTO events (
                timestamp, status, severity, s1_abnormal_sec, s2_abnormal_sec,
                s1_med_rms, s2_med_rms, reasoning, is_demo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.timestamp, decision.decision, severity,
                decision.s1_abnormal_count, decision.s2_abnormal_count,
                decision.s1_med_rms, decision.s2_med_rms, decision.reasoning,
                1 if decision.is_demo else 0
            ))
            conn.commit()

        conn.close()
        return row_id or 0
    except Exception as e:
        print(f"[DB ERROR] Failed to save decision: {e}")
        return 0


def get_recent_events(limit: int = 50, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if status_filter:
        cursor.execute("SELECT * FROM events WHERE status LIKE ? ORDER BY id DESC LIMIT ?", (f"%{status_filter}%", limit))
    else:
        cursor.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_event_operator_status(event_id: int, status: str, note: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET operator_status = ?, operator_note = ? WHERE id = ?", (status, note, event_id))
    conn.commit()
    conn.close()


def clear_events(demo_only: bool = False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if demo_only:
        cursor.execute("DELETE FROM events WHERE is_demo = 1")
    else:
        cursor.execute("DELETE FROM events")
    conn.commit()
    conn.close()


def get_telemetry_history(limit: int = 500) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telemetry_records ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    result.reverse()  # Chronological order
    return result


def save_wireless_record(rec: dict) -> int:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO wireless_telemetry_records (
            utc_timestamp, node_id, packet_sequence,
            flow_in_lpm, flow_out_lpm, flow_diff_lpm,
            leak_alarm, rms1, p2p1, rms2, p2p2,
            s1_clipped, s2_clipped, vibration_valid, gps_valid,
            latitude, longitude, satellites, hdop, gps_time,
            missed_packets, sequence_reset, communication_source, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec.get("utc_timestamp", datetime.datetime.now().isoformat()),
            rec.get("node_id", 1),
            rec.get("packet_sequence", 0),
            rec.get("flow_in_lpm", 0.0),
            rec.get("flow_out_lpm", 0.0),
            rec.get("flow_diff_lpm", 0.0),
            1 if rec.get("leak_alarm") else 0,
            rec.get("rms1", 0.0),
            rec.get("p2p1", 0),
            rec.get("rms2", 0.0),
            rec.get("p2p2", 0),
            1 if rec.get("s1_clipped") else 0,
            1 if rec.get("s2_clipped") else 0,
            0 if rec.get("vibration_invalid") else 1,
            1 if rec.get("gps_valid") else 0,
            rec.get("latitude"),
            rec.get("longitude"),
            rec.get("satellites", 0),
            rec.get("hdop", 99.9),
            rec.get("gps_time"),
            rec.get("missed_packets", 0),
            rec.get("sequence_reset", 0),
            rec.get("communication_source", "ARDUINO_UNO_NRF24"),
            1 if rec.get("is_demo") else 0
        ))
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id or 0
    except Exception as e:
        print(f"[DB ERROR] Failed to save wireless telemetry: {e}")
        return 0


def get_latest_wireless_record() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wireless_telemetry_records ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_wireless_history(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wireless_telemetry_records ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    result.reverse()  # Chronological order
    return result


def record_leak_transition(transition_type: str, details: dict):
    """Stores leak-alarm transitions (0->1 or 1->0) as separate historical events."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_iso = datetime.datetime.now().isoformat()
        if transition_type == "LEAK_CONFIRMED":
            status = "CONFIRMED LEAK (WIRELESS FLOW ALARM)"
            severity = "CRITICAL"
            reasoning = (
                f"Arduino Uno transmitter node {details.get('node_id', 1)} signaled flow leak alarm. "
                f"Inlet={details.get('flow_in_lpm', 0.0):.2f} L/min, "
                f"Outlet={details.get('flow_out_lpm', 0.0):.2f} L/min, "
                f"Diff={details.get('flow_diff_lpm', 0.0):.2f} L/min."
            )
        else:
            status = "LEAK RESOLVED (WIRELESS FLOW BALANCED)"
            severity = "LOW"
            reasoning = (
                f"Arduino Uno transmitter node {details.get('node_id', 1)} flow returned to balance. "
                f"Inlet={details.get('flow_in_lpm', 0.0):.2f} L/min, "
                f"Outlet={details.get('flow_out_lpm', 0.0):.2f} L/min."
            )

        cursor.execute("""
        INSERT INTO events (
            timestamp, status, severity, s1_abnormal_sec, s2_abnormal_sec,
            s1_med_rms, s2_med_rms, reasoning, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso, status, severity,
            0, 0,
            details.get("rms1", 0.0),
            details.get("rms2", 0.0),
            reasoning,
            1 if details.get("is_demo") else 0
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to record leak transition event: {e}")


def save_arduino_localization_event(event: dict) -> int:
    """Stores an Arduino Uno acoustic TDOA localization event."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO arduino_localization_events (
            utc_timestamp, node_id, event_id, transmitter_timestamp_ms,
            delta_t_us, estimated_distance_m, distance_sensor2_m,
            correlation_peak, psr, is_valid, failure_code, failure_reason,
            flow_confirmed, pipeline_length_m, calibrated_velocity_mps
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.get("utc_timestamp", datetime.datetime.now().isoformat()),
            event.get("node_id", 1),
            event.get("event_id", 0),
            event.get("transmitter_timestamp_ms", 0),
            event.get("delta_t_us", 0.0),
            event.get("estimated_distance_m"),
            event.get("distance_sensor2_m"),
            event.get("correlation_peak", 0.0),
            event.get("psr", 0.0),
            1 if event.get("is_valid") else 0,
            event.get("failure_code", 0),
            event.get("failure_reason", "VALID"),
            1 if event.get("flow_confirmed") else 0,
            event.get("pipeline_length_m", 2.0),
            event.get("calibrated_velocity_mps", 1250.0)
        ))
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id or 0
    except Exception as e:
        print(f"[DB ERROR] Failed to save localization event: {e}")
        return 0


def get_latest_localization_event() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM arduino_localization_events ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_localization_events(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM arduino_localization_events ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    result.reverse()
    return result

