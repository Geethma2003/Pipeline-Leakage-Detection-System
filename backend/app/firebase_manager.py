"""
AquaGuard AI Firebase Cloud Firestore Manager
=============================================
Manages Firebase Admin SDK connection to project `aquaguard-pipeline`.

Features:
- Secure initialization via service account JSON key path loaded from environment variables
  (FIREBASE_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS) or local fallback.
- Reduced frequency measurement logging (every 5 seconds or on anomaly) to avoid Firestore write quota limits.
- Persists:
  1. `measurements` (Reduced-frequency ESP32 telemetry records)
  2. `window_reports` (Completed 60-second vibration analysis reports)
  3. `sensor_health` (Sensor diagnostics & dynamic baseline thresholds)
  4. `leak_events` (Suspected leak alarms & operator confirmation status)
- Offline buffering and graceful exception handling when network or Firestore is unavailable.
"""

import os
import time
import datetime
from typing import List, Optional, Dict, Any, Tuple
import firebase_admin
from firebase_admin import credentials, firestore

from app.config import BASE_DIR
from app.models import TelemetryRecord, WindowDecisionModel, BaselineProfileModel, HardwareDiagnosticsModel


class FirebaseManager:
    def __init__(self):
        self.app: Optional[firebase_admin.App] = None
        self.db: Optional[firestore.Client] = None
        self.is_initialized: bool = False
        self.project_id: str = "aquaguard-pipeline"
        self.last_error: Optional[str] = None
        self.last_measurement_saved_time: float = 0.0
        self.measurement_interval_sec: float = 5.0  # Reduced frequency (1 record per 5s)
        self.offline_queue: List[Dict[str, Any]] = []

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        # Check environment variables for service account path
        cred_path = (
            os.getenv("FIREBASE_CREDENTIALS_PATH")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or os.path.join(BASE_DIR, "firebase_service_account.json")
        )

        if not os.path.exists(cred_path):
            self.last_error = f"Firebase credentials file not found at: {cred_path}"
            print(f"[FIREBASE WARNING] {self.last_error}")
            return False

        try:
            cred = credentials.Certificate(cred_path)
            # Avoid duplicate initialization
            if not firebase_admin._apps:
                self.app = firebase_admin.initialize_app(cred, {
                    'projectId': self.project_id
                })
            else:
                self.app = firebase_admin.get_app()

            self.db = firestore.client()
            self.is_initialized = True
            self.last_error = None
            print(f"[FIREBASE] Successfully initialized Admin SDK for project '{self.project_id}'.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[FIREBASE ERROR] Initialization failed: {e}")
            self.is_initialized = False
            return False

    def check_cloud_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Actively checks online connectivity to Cloud Firestore by probing document status.
        Returns (is_online: bool, last_error: Optional[str]).
        """
        if not self.is_initialized or not self.db:
            return False, self.last_error or "Firebase Admin SDK not initialized."

        try:
            # Lightweight cloud Firestore probe
            self.db.collection("sensor_health").document("current_status").get(timeout=3.0)
            return True, None
        except Exception as e:
            err_msg = f"Firestore Cloud Unreachable: {e}"
            self.last_error = err_msg
            return False, err_msg

    def save_measurement_reduced_frequency(self, rec: TelemetryRecord, force: bool = False) -> bool:
        """
        Stores reduced frequency measurement records (e.g. every 5 seconds or immediately if abnormal)
        to prevent excessive database writes.
        """
        if not self.is_initialized or not self.db:
            return False

        now = time.time()
        is_abnormal = (rec.s1_abnormal == 1 or rec.s2_abnormal == 1 or rec.is_transient == 1)

        # Write if interval elapsed OR if forced OR if anomalous second
        if force or is_abnormal or (now - self.last_measurement_saved_time >= self.measurement_interval_sec):
            self.last_measurement_saved_time = now
            doc_data = {
                "pc_timestamp": rec.pc_timestamp,
                "esp32_ms": rec.esp32_ms,
                "second_index": rec.second_index,
                "s1_rms": float(rec.s1_rms),
                "s1_p2p": float(rec.s1_p2p),
                "s1_variance": float(rec.s1_variance),
                "s1_stvar": float(rec.s1_stvar),
                "s2_rms": float(rec.s2_rms),
                "s2_p2p": float(rec.s2_p2p),
                "s2_variance": float(rec.s2_variance),
                "s2_stvar": float(rec.s2_stvar),
                "s1_abnormal": int(rec.s1_abnormal),
                "s2_abnormal": int(rec.s2_abnormal),
                "is_transient": int(rec.is_transient),
                "status_str": rec.status_str,
                "is_demo": bool(rec.is_demo),
                "created_at": firestore.SERVER_TIMESTAMP
            }

            try:
                self.db.collection("measurements").add(doc_data)
                return True
            except Exception as e:
                print(f"[FIREBASE ERROR] Failed to add measurement: {e}")
                return False
        return False

    def save_wireless_measurement(self, data: dict, force: bool = False) -> bool:
        """
        Stores reduced frequency wireless measurements to Firestore to prevent excessive writes.
        Syncs every 10 seconds, or immediately if leak_alarm is active or forced.
        """
        if not self.is_initialized or not self.db:
            return False

        now = time.time()
        has_alarm = bool(data.get("leak_alarm", False))

        if force or has_alarm or (now - self.last_measurement_saved_time >= 10.0):
            self.last_measurement_saved_time = now
            doc_data = {
                "utc_timestamp": data.get("utc_timestamp"),
                "node_id": data.get("node_id", 1),
                "packet_sequence": data.get("packet_sequence", 0),
                "flow_in_lpm": float(data.get("flow_in_lpm", 0.0)),
                "flow_out_lpm": float(data.get("flow_out_lpm", 0.0)),
                "flow_diff_lpm": float(data.get("flow_diff_lpm", 0.0)),
                "leak_alarm": has_alarm,
                "rms1": float(data.get("rms1", 0.0)),
                "p2p1": int(data.get("p2p1", 0)),
                "rms2": float(data.get("rms2", 0.0)),
                "p2p2": int(data.get("p2p2", 0)),
                "status_str": data.get("status_str", "NORMAL"),
                "communication_source": data.get("communication_source", "ARDUINO_UNO_NRF24"),
                "created_at": firestore.SERVER_TIMESTAMP
            }
            if data.get("latitude") is not None and data.get("longitude") is not None:
                doc_data["latitude"] = float(data["latitude"])
                doc_data["longitude"] = float(data["longitude"])

            try:
                self.db.collection("wireless_measurements").add(doc_data)
                return True
            except Exception as e:
                print(f"[FIREBASE ERROR] Failed to add wireless measurement: {e}")
                return False
        return False

    def save_window_report(self, decision: WindowDecisionModel) -> bool:
        """Saves a completed 60-second vibration analysis report to Firestore `window_reports`."""
        if not self.is_initialized or not self.db:
            return False

        doc_data = {
            "window_index": decision.window_index,
            "timestamp": decision.timestamp,
            "decision": decision.decision,
            "reasoning": decision.reasoning,
            "s1_abnormal_count": decision.s1_abnormal_count,
            "s2_abnormal_count": decision.s2_abnormal_count,
            "s1_max_seq": decision.s1_max_seq,
            "s2_max_seq": decision.s2_max_seq,
            "s1_med_rms": float(decision.s1_med_rms),
            "s2_med_rms": float(decision.s2_med_rms),
            "s1_var_ratio": float(decision.s1_var_ratio),
            "s2_var_ratio": float(decision.s2_var_ratio),
            "tdoa_sec": float(decision.tdoa_sec),
            "peak_corr": float(decision.peak_corr),
            "loc_valid": bool(decision.loc_valid),
            "estimated_distance_m": float(decision.estimated_distance_m) if decision.estimated_distance_m is not None else None,
            "is_demo": bool(decision.is_demo),
            "created_at": firestore.SERVER_TIMESTAMP
        }

        try:
            self.db.collection("window_reports").add(doc_data)

            # If sustained anomaly or fault, save to `leak_events`
            if "SUSTAINED" in decision.decision or "FAULT" in decision.decision:
                severity = "CRITICAL" if "SUSTAINED" in decision.decision else "HIGH"
                event_data = {
                    "timestamp": decision.timestamp,
                    "status": decision.decision,
                    "severity": severity,
                    "s1_abnormal_sec": decision.s1_abnormal_count,
                    "s2_abnormal_sec": decision.s2_abnormal_count,
                    "s1_med_rms": float(decision.s1_med_rms),
                    "s2_med_rms": float(decision.s2_med_rms),
                    "reasoning": decision.reasoning,
                    "operator_status": "UNCONFIRMED",
                    "operator_note": "",
                    "is_demo": bool(decision.is_demo),
                    "created_at": firestore.SERVER_TIMESTAMP
                }
                self.db.collection("leak_events").add(event_data)

            return True
        except Exception as e:
            print(f"[FIREBASE ERROR] Failed to save window report: {e}")
            return False

    def update_sensor_health(self, diagnostics: HardwareDiagnosticsModel, baseline: BaselineProfileModel) -> bool:
        """Updates sensor health & baseline state in Firestore `sensor_health` collection."""
        if not self.is_initialized or not self.db:
            return False

        doc_data = {
            "serial_port": diagnostics.serial_port,
            "baud_rate": diagnostics.baud_rate,
            "connection_status": diagnostics.connection_status,
            "esp32_uptime_sec": diagnostics.esp32_uptime_sec,
            "sample_rate_hz": diagnostics.sample_rate_hz,
            "s1_baseline_median": float(baseline.s1_rms_median),
            "s1_thresh": float(baseline.s1_thresh),
            "s2_baseline_median": float(baseline.s2_rms_median),
            "s2_thresh": float(baseline.s2_thresh),
            "is_calibrated": bool(baseline.is_calibrated),
            "last_updated": datetime.datetime.now().isoformat()
        }

        try:
            # Set single doc "current_status"
            self.db.collection("sensor_health").document("current_status").set(doc_data)
            return True
        except Exception as e:
            print(f"[FIREBASE ERROR] Failed to update sensor health: {e}")
            return False

    def get_historical_measurements(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves recent measurement documents from Firestore `measurements`."""
        if not self.is_initialized or not self.db:
            return []

        try:
            docs = (
                self.db.collection("measurements")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            result = []
            for d in docs:
                data = d.to_dict()
                data["id"] = d.id
                result.append(data)
            return result
        except Exception as e:
            print(f"[FIREBASE QUERY ERROR] {e}")
            return []

    def get_window_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves 60-second window report documents from Firestore `window_reports`."""
        if not self.is_initialized or not self.db:
            return []

        try:
            docs = (
                self.db.collection("window_reports")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [d.to_dict() for d in docs]
        except Exception as e:
            print(f"[FIREBASE QUERY ERROR] {e}")
            return []

    def get_leak_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves leak events from Firestore `leak_events`."""
        if not self.is_initialized or not self.db:
            return []

        try:
            docs = (
                self.db.collection("leak_events")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            result = []
            for d in docs:
                data = d.to_dict()
                data["doc_id"] = d.id
                result.append(data)
            return result
        except Exception as e:
            print(f"[FIREBASE QUERY ERROR] {e}")
            return []


# Global Firebase Manager instance
firebase_mgr = FirebaseManager()
