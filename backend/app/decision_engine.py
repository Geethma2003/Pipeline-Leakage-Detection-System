"""
AquaGuard AI Decision Engine
============================
Python implementation of the 60-second window multi-criteria pipeline monitoring algorithm.
Mirrors the exact firmware rules in pipeline_monitor.ino.
"""
import numpy as np
import datetime
from typing import List, Tuple, Optional
from app.config import (
    DEFAULT_PERSISTENCE_REQ, MIN_CONSECUTIVE_ABN, MAD_MULTIPLIER,
    RMS_FACTOR_MULTIPLIER, MIN_RMS_ABSOLUTE_FLOOR, MAX_VARIABILITY_RATIO,
    PIPE_LENGTH_METERS, ACOUSTIC_SPEED_MPS, MIN_CORRELATION_PEAK
)
from app.models import BaselineProfileModel, WindowDecisionModel, TelemetryRecord


class DecisionEngine:
    def __init__(self, persistence_req: int = DEFAULT_PERSISTENCE_REQ):
        self.persistence_req = persistence_req
        self.min_consec = MIN_CONSECUTIVE_ABN
        self.max_var_ratio = MAX_VARIABILITY_RATIO
        self.system_state = "INITIALIZING"  # "INITIALIZING", "NORMAL", "SUSPECTED_ANOMALY", "CONFIRMED_LEAK", "SENSOR_FAULT"
        self.normal_windows_in_alarm = 0
        self.flow_leak_confirmed: bool = False
        self.flow_leak_progress: int = 0
        self.latest_flow_record: Optional[dict] = None
        self.baseline = BaselineProfileModel()
        self.history_window: List[TelemetryRecord] = []
        self.window_counter = 0

    def update_flow_telemetry(self, flow_data: dict):
        self.latest_flow_record = flow_data
        self.flow_leak_confirmed = flow_data.get("leak_confirmed", False)
        self.flow_leak_progress = flow_data.get("leak_progress", 0)
        status = flow_data.get("status", "")
        if status in ["COMMUNICATION LOST", "COMMUNICATION_LOST", "DATA UNAVAILABLE"]:
            self.system_state = "COMMUNICATION_LOST"
        elif status == "LOW_OR_NO_FLOW":
            self.system_state = "LOW_OR_NO_FLOW"
        elif self.flow_leak_confirmed:
            self.system_state = "CONFIRMED_LEAK"
        elif self.system_state in ["CONFIRMED_LEAK", "COMMUNICATION_LOST", "LOW_OR_NO_FLOW"] and not self.flow_leak_confirmed:
            self.system_state = "NORMAL"

    def set_baseline(self, baseline: BaselineProfileModel):
        self.baseline = baseline

    def calibrate_from_window(self, records: List[TelemetryRecord]) -> BaselineProfileModel:
        if not records:
            return self.baseline

        s1_rms = np.array([r.s1_rms for r in records])
        s2_rms = np.array([r.s2_rms for r in records])

        s1_med = float(np.median(s1_rms))
        s1_mad = float(np.median(np.abs(s1_rms - s1_med)))
        s1_t1 = s1_med + (MAD_MULTIPLIER * s1_mad)
        s1_t2 = s1_med * RMS_FACTOR_MULTIPLIER
        s1_thresh = float(max(max(s1_t1, s1_t2), MIN_RMS_ABSOLUTE_FLOOR))

        s2_med = float(np.median(s2_rms))
        s2_mad = float(np.median(np.abs(s2_rms - s2_med)))
        s2_t1 = s2_med + (MAD_MULTIPLIER * s2_mad)
        s2_t2 = s2_med * RMS_FACTOR_MULTIPLIER
        s2_thresh = float(max(max(s2_t1, s2_t2), MIN_RMS_ABSOLUTE_FLOOR))

        self.baseline = BaselineProfileModel(
            s1_rms_median=s1_med,
            s1_rms_mad=s1_mad,
            s1_thresh=s1_thresh,
            s2_rms_median=s2_med,
            s2_rms_mad=s2_mad,
            s2_thresh=s2_thresh,
            is_calibrated=True,
            calibrated_at=datetime.datetime.now().isoformat()
        )
        return self.baseline

    def add_second_record(self, record: TelemetryRecord) -> Optional[WindowDecisionModel]:
        # Update preliminary abnormal flags based on baseline thresholds
        record.s1_abnormal = 1 if record.s1_rms > self.baseline.s1_thresh else 0
        record.s2_abnormal = 1 if record.s2_rms > self.baseline.s2_thresh else 0

        self.history_window.append(record)
        if len(self.history_window) > 60:
            self.history_window.pop(0)

        # Evaluate window when 60 seconds of records are collected
        if len(self.history_window) == 60:
            self.window_counter += 1
            decision = self.evaluate_60s_window(self.history_window, self.window_counter)
            return decision

        return None

    def evaluate_60s_window(self, records: List[TelemetryRecord], window_idx: int) -> WindowDecisionModel:
        s1_rms_arr = np.array([r.s1_rms for r in records])
        s2_rms_arr = np.array([r.s2_rms for r in records])

        s1_abn_count = int(sum([r.s1_abnormal for r in records]))
        s2_abn_count = int(sum([r.s2_abnormal for r in records]))
        transient_count = int(sum([r.is_transient for r in records]))

        # Calculate max consecutive run length
        def get_max_consecutive(flags: List[int]) -> int:
            max_c = 0
            curr_c = 0
            for f in flags:
                if f:
                    curr_c += 1
                    if curr_c > max_c:
                        max_c = curr_c
                else:
                    curr_c = 0
            return max_c

        s1_max_seq = get_max_consecutive([r.s1_abnormal for r in records])
        s2_max_seq = get_max_consecutive([r.s2_abnormal for r in records])

        s1_med_rms = float(np.median(s1_rms_arr))
        s2_med_rms = float(np.median(s2_rms_arr))

        s1_mean = float(np.mean(s1_rms_arr))
        s2_mean = float(np.mean(s2_rms_arr))

        s1_std = float(np.std(s1_rms_arr))
        s2_std = float(np.std(s2_rms_arr))

        s1_var_ratio = (s1_std / s1_mean) if s1_mean > 0 else 0.0
        s2_var_ratio = (s2_std / s2_mean) if s2_mean > 0 else 0.0

        # Check Hardware DC Fault (0.32V .. 2.98V range equivalent in ADC counts)
        is_hardware_fault = any(r.status_str == "FAULT" for r in records)

        # Cross correlation estimate (simulated or computed)
        tdoa_sec, peak_corr, loc_valid, est_dist = self._compute_localization(s1_rms_arr, s2_rms_arr)

        timestamp = datetime.datetime.now().isoformat()
        is_demo = any(r.is_demo for r in records)

        # Decision Matrix
        if is_hardware_fault:
            self.system_state = "SENSOR_FAULT"
            return WindowDecisionModel(
                window_index=window_idx,
                timestamp=timestamp,
                decision="SENSOR OR CALIBRATION FAULT",
                reasoning="ADC voltage rail short/disconnection or flatline variance detected on hardware.",
                s1_abnormal_count=s1_abn_count,
                s2_abnormal_count=s2_abn_count,
                s1_max_seq=s1_max_seq,
                s2_max_seq=s2_max_seq,
                s1_med_rms=s1_med_rms,
                s2_med_rms=s2_med_rms,
                s1_var_ratio=s1_var_ratio,
                s2_var_ratio=s2_var_ratio,
                tdoa_sec=tdoa_sec,
                peak_corr=peak_corr,
                loc_valid=False,
                estimated_distance_m=None,
                is_demo=is_demo
            )

        # Either sensor rule for sustained anomaly
        s1_sustained = (s1_abn_count >= self.persistence_req) and (s1_max_seq >= self.min_consec) and (s1_var_ratio <= self.max_var_ratio)
        s2_sustained = (s2_abn_count >= self.persistence_req) and (s2_max_seq >= self.min_consec) and (s2_var_ratio <= self.max_var_ratio)

        # Flow verification status
        flow_confirmed = self.flow_leak_confirmed

        if s1_sustained or s2_sustained:
            self.normal_windows_in_alarm = 0
            reasoning = "SUSTAINED ANOMALY DETECTED: "
            if s1_sustained and s2_sustained:
                reasoning += f"Both S1 and S2 show continuous vibration elevation (>= {self.persistence_req}/60s)."
            elif s1_sustained:
                ratio = int(s1_med_rms / self.baseline.s1_rms_median) if self.baseline.s1_rms_median > 0 else 1
                reasoning += f"Sensor 1 elevated ({s1_abn_count}/60s, {ratio}x increase) while Sensor 2 near baseline. Consistent with high acoustic attenuation."
            else:
                ratio = int(s2_med_rms / self.baseline.s2_rms_median) if self.baseline.s2_rms_median > 0 else 1
                reasoning += f"Sensor 2 elevated ({s2_abn_count}/60s, {ratio}x increase) while Sensor 1 near baseline."

            # CRITICAL RULE: ONLY flow sensors determine whether a leak is confirmed.
            # The vibration sensors must ONLY determine the estimated leak location.
            # The website must NOT reveal an official leak location until the flow sensors confirm leakage.
            if flow_confirmed:
                self.system_state = "CONFIRMED_LEAK"
                decision_str = "CONFIRMED LEAK (FLOW VERIFIED & ACOUSTICALLY LOCALIZED)"
                reasoning += " Flow sensors confirmed leakage. Official leak location verified and revealed."
                loc_revealed = loc_valid
                est_dist_final = est_dist if loc_valid else None
            else:
                self.system_state = "SUSPECTED_ANOMALY"
                decision_str = "SUSTAINED VIBRATION ANOMALY (AWAITING FLOW CONFIRMATION)"
                reasoning += " Flow sensors have NOT confirmed leakage. Official leak location concealed until flow verification."
                loc_revealed = False
                est_dist_final = None

            return WindowDecisionModel(
                window_index=window_idx,
                timestamp=timestamp,
                decision=decision_str,
                reasoning=reasoning,
                s1_abnormal_count=s1_abn_count,
                s2_abnormal_count=s2_abn_count,
                s1_max_seq=s1_max_seq,
                s2_max_seq=s2_max_seq,
                s1_med_rms=s1_med_rms,
                s2_med_rms=s2_med_rms,
                s1_var_ratio=s1_var_ratio,
                s2_var_ratio=s2_var_ratio,
                tdoa_sec=tdoa_sec,
                peak_corr=peak_corr,
                loc_valid=loc_revealed,
                estimated_distance_m=est_dist_final,
                is_demo=is_demo
            )

        elif flow_confirmed:
            self.system_state = "CONFIRMED_LEAK"
            self.normal_windows_in_alarm = 0
            reasoning = "FLOW SENSORS CONFIRMED LEAKAGE: Dual YF-S201 meters confirm persistent flow imbalance >= 0.10 L/min across 3 consecutive windows."
            return WindowDecisionModel(
                window_index=window_idx,
                timestamp=timestamp,
                decision="CONFIRMED LEAK (VERIFIED BY FLOW METERS)",
                reasoning=reasoning,
                s1_abnormal_count=s1_abn_count,
                s2_abnormal_count=s2_abn_count,
                s1_max_seq=s1_max_seq,
                s2_max_seq=s2_max_seq,
                s1_med_rms=s1_med_rms,
                s2_med_rms=s2_med_rms,
                s1_var_ratio=s1_var_ratio,
                s2_var_ratio=s2_var_ratio,
                tdoa_sec=tdoa_sec,
                peak_corr=peak_corr,
                loc_valid=loc_valid,
                estimated_distance_m=est_dist if loc_valid else None,
                is_demo=is_demo
            )

        elif (s1_abn_count >= 10 or s2_abn_count >= 10) or transient_count > 12 or \
             s1_var_ratio > self.max_var_ratio or s2_var_ratio > self.max_var_ratio:

            if self.system_state == "CONFIRMED_LEAK":
                self.normal_windows_in_alarm += 1
                if self.normal_windows_in_alarm >= 2:
                    self.system_state = "NORMAL"

            reasoning = "TRANSIENT DISTURBANCE: "
            if s1_var_ratio > self.max_var_ratio or s2_var_ratio > self.max_var_ratio:
                reasoning += f"High vibration variability (std/mean > {self.max_var_ratio:.2f}) indicates pump speed change or valve operation."
            else:
                reasoning += f"Short-duration spikes ({transient_count} transient seconds) without 60s sustained persistence."

            return WindowDecisionModel(
                window_index=window_idx,
                timestamp=timestamp,
                decision="TRANSIENT DISTURBANCE",
                reasoning=reasoning,
                s1_abnormal_count=s1_abn_count,
                s2_abnormal_count=s2_abn_count,
                s1_max_seq=s1_max_seq,
                s2_max_seq=s2_max_seq,
                s1_med_rms=s1_med_rms,
                s2_med_rms=s2_med_rms,
                s1_var_ratio=s1_var_ratio,
                s2_var_ratio=s2_var_ratio,
                tdoa_sec=tdoa_sec,
                peak_corr=peak_corr,
                loc_valid=False,
                estimated_distance_m=None,
                is_demo=is_demo
            )

        else:
            if self.system_state == "CONFIRMED_LEAK":
                self.normal_windows_in_alarm += 1
                if self.normal_windows_in_alarm >= 2:
                    self.system_state = "NORMAL"
            else:
                self.system_state = "NORMAL"

            return WindowDecisionModel(
                window_index=window_idx,
                timestamp=timestamp,
                decision="NORMAL",
                reasoning="Vibration levels within baseline statistical bounds across full 60s window.",
                s1_abnormal_count=s1_abn_count,
                s2_abnormal_count=s2_abn_count,
                s1_max_seq=s1_max_seq,
                s2_max_seq=s2_max_seq,
                s1_med_rms=s1_med_rms,
                s2_med_rms=s2_med_rms,
                s1_var_ratio=s1_var_ratio,
                s2_var_ratio=s2_var_ratio,
                tdoa_sec=tdoa_sec,
                peak_corr=peak_corr,
                loc_valid=False,
                estimated_distance_m=None,
                is_demo=is_demo
            )

    def _compute_localization(self, s1_rms: np.ndarray, s2_rms: np.ndarray) -> Tuple[float, float, bool, Optional[float]]:
        """
        Calculates cross-correlation quality check.
        Honest Uncertainty Enforcement: Returns loc_valid=True only if peak_corr >= 0.65.
        """
        # Cross correlation on normalized envelope signals
        s1_norm = s1_rms - np.mean(s1_rms)
        s2_norm = s2_rms - np.mean(s2_rms)
        norm_factor = np.sqrt(np.sum(s1_norm ** 2) * np.sum(s2_norm ** 2))

        if norm_factor < 1e-4:
            return 0.0, 0.0, False, None

        corr = np.correlate(s1_norm, s2_norm, mode='full') / norm_factor
        lags = np.arange(-len(s1_rms) + 1, len(s1_rms))
        max_idx = np.argmax(corr)
        peak_corr = float(corr[max_idx])
        best_lag = float(lags[max_idx])

        # Convert lag (seconds in per-second signal) to TDOA estimate
        tdoa_sec = best_lag * 0.001  # scale factor for acoustic delay

        if peak_corr >= MIN_CORRELATION_PEAK:
            # Estimate position along 2m pipe: x = (L + v * tdoa) / 2
            est_dist = (PIPE_LENGTH_METERS + (ACOUSTIC_SPEED_MPS * tdoa_sec)) / 2.0
            est_dist = max(0.0, min(PIPE_LENGTH_METERS, est_dist))
            return tdoa_sec, peak_corr, True, round(est_dist, 2)

        return tdoa_sec, peak_corr, False, None
