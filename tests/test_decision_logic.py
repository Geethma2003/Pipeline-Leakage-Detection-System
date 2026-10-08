"""
Unit Tests for ESP32 Pipeline Leakage Detection Decision Engine
==============================================================
Tests decision matrix classification logic across 7 physical scenarios:
1. Normal operation (no leak)
2. Short transient spikes (dropped tool, valve tap)
3. Sustained single-sensor anomaly (Sensor 1 20x increase, Sensor 2 normal)
4. Sustained dual-sensor anomaly
5. Pump speed change / global noise shift with high variability
6. Recovery with alarm hysteresis
7. Hardware / Sensor calibration fault
"""

import pytest
import numpy as np


class DecisionEngineSimulator:
    """
    Python implementation of the ESP32 60-second multi-criteria decision engine.
    Mirrors the exact rules in pipeline_monitor.ino.
    """
    def __init__(self, persistence_req=42, min_consec=15, max_var_ratio=0.48):
        self.persistence_req = persistence_req
        self.min_consec = min_consec
        self.max_var_ratio = max_var_ratio
        self.state = "STATE_MONITORING_NORMAL"
        self.normal_windows_in_alarm = 0

    def evaluate_60s_window(self, s1_rms_arr, s2_rms_arr, s1_thresh, s2_thresh, 
                            s1_raw_means=None, s2_raw_means=None, transient_flags=None):
        assert len(s1_rms_arr) == 60, "Window must contain exactly 60 one-second feature records."
        assert len(s2_rms_arr) == 60, "Window must contain exactly 60 one-second feature records."

        if s1_raw_means is None: s1_raw_means = [2048.0] * 60
        if s2_raw_means is None: s2_raw_means = [2048.0] * 60
        if transient_flags is None: transient_flags = [False] * 60

        # Hardware Fault Check
        for i in range(60):
            if s1_raw_means[i] < 400 or s1_raw_means[i] > 3700 or \
               s2_raw_means[i] < 400 or s2_raw_means[i] > 3700:
                self.state = "STATE_SENSOR_FAULT"
                return "SENSOR OR CALIBRATION FAULT", "Hardware DC offset out of bounds."

        # Compute abnormal counts and consecutive runs
        s1_abn = [rms > s1_thresh for rms in s1_rms_arr]
        s2_abn = [rms > s2_thresh for rms in s2_rms_arr]

        s1_abn_count = sum(s1_abn)
        s2_abn_count = sum(s2_abn)
        transient_count = sum(transient_flags)

        def max_consecutive(flags):
            max_c = 0
            curr_c = 0
            for f in flags:
                if f:
                    curr_c += 1
                    if curr_c > max_c: max_c = curr_c
                else:
                    curr_c = 0
            return max_c

        s1_max_seq = max_consecutive(s1_abn)
        s2_max_seq = max_consecutive(s2_abn)

        # Compute Noise Variability (std / mean)
        s1_mean = np.mean(s1_rms_arr)
        s2_mean = np.mean(s2_rms_arr)

        s1_var_ratio = (np.std(s1_rms_arr) / s1_mean) if s1_mean > 0 else 0.0
        s2_var_ratio = (np.std(s2_rms_arr) / s2_mean) if s2_mean > 0 else 0.0

        # Check sustained criteria (Either Sensor Rule)
        s1_sustained = (s1_abn_count >= self.persistence_req) and (s1_max_seq >= self.min_consec) and (s1_var_ratio <= self.max_var_ratio)
        s2_sustained = (s2_abn_count >= self.persistence_req) and (s2_max_seq >= self.min_consec) and (s2_var_ratio <= self.max_var_ratio)

        if s1_sustained or s2_sustained:
            self.state = "STATE_CONFIRMED_LEAK_ALARM"
            self.normal_windows_in_alarm = 0
            return "SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK", "Sustained elevation meeting persistence criteria."

        elif (s1_abn_count >= 10 or s2_abn_count >= 10) or transient_count > 12 or \
             s1_var_ratio > self.max_var_ratio or s2_var_ratio > self.max_var_ratio:
            
            if self.state == "STATE_CONFIRMED_LEAK_ALARM":
                self.normal_windows_in_alarm += 1
                if self.normal_windows_in_alarm >= 2:
                    self.state = "STATE_MONITORING_NORMAL"
            return "TRANSIENT DISTURBANCE", "High variability or short-duration spikes without 60s sustained duration."

        else:
            if self.state == "STATE_CONFIRMED_LEAK_ALARM":
                self.normal_windows_in_alarm += 1
                if self.normal_windows_in_alarm >= 2:
                    self.state = "STATE_MONITORING_NORMAL"
            else:
                self.state = "STATE_MONITORING_NORMAL"

            return "NORMAL", "Vibration levels within baseline statistical bounds."


# ============================================================================
# UNIT TESTS
# ============================================================================

def test_scenario_1_no_leak_normal():
    """Test 1: Normal steady pipeline vibration returns NORMAL."""
    sim = DecisionEngineSimulator()
    s1_rms = np.random.normal(12.0, 1.0, 60)
    s2_rms = np.random.normal(11.5, 1.0, 60)
    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0)
    assert decision == "NORMAL"


def test_scenario_2_short_transient_spikes():
    """Test 2: Short 3-second impulse spikes return TRANSIENT DISTURBANCE."""
    sim = DecisionEngineSimulator()
    s1_rms = np.full(60, 12.0)
    s2_rms = np.full(60, 11.5)
    # 3 second spike
    s1_rms[10:13] = 150.0
    transient_flags = [False] * 60
    for i in range(10, 13): transient_flags[i] = True

    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0, transient_flags=transient_flags)
    assert decision == "TRANSIENT DISTURBANCE"


def test_scenario_3_sustained_single_sensor_leak():
    """Test 3: Sensor 1 increases 20x for 50 seconds while Sensor 2 stays baseline. MUST detect anomaly!"""
    sim = DecisionEngineSimulator()
    s1_rms = np.full(60, 12.0)
    s2_rms = np.full(60, 11.5)
    # Sensor 1 elevated 20x (240.0 counts) for 50 out of 60 seconds
    s1_rms[5:55] = np.random.normal(240.0, 5.0, 50)

    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0)
    assert decision == "SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK"


def test_scenario_4_sustained_two_sensor_leak():
    """Test 4: Both sensors exhibit continuous elevation returns SUSTAINED ANOMALY."""
    sim = DecisionEngineSimulator()
    s1_rms = np.random.normal(180.0, 4.0, 60)
    s2_rms = np.random.normal(150.0, 4.0, 60)

    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0)
    assert decision == "SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK"


def test_scenario_5_pump_speed_change_variability():
    """Test 5: Pump speed change causing high RMS noise variability (std/mean > 0.48) returns TRANSIENT DISTURBANCE."""
    sim = DecisionEngineSimulator()
    # Fluctuate wildly between low (10) and high (200) representing pump acceleration/deceleration
    s1_rms = np.array([10.0 if i % 2 == 0 else 200.0 for i in range(60)])
    s2_rms = np.array([10.0 if i % 2 == 0 else 180.0 for i in range(60)])

    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0)
    assert decision == "TRANSIENT DISTURBANCE"



def test_scenario_6_alarm_recovery_with_hysteresis():
    """Test 6: Alarm enters on leak, requires two clean windows before clearing to NORMAL."""
    sim = DecisionEngineSimulator()

    # Window 1: Leak active
    s1_leak = np.random.normal(220.0, 5.0, 60)
    s2_norm = np.full(60, 11.5)
    d1, r1 = sim.evaluate_60s_window(s1_leak, s2_norm, s1_thresh=25.0, s2_thresh=24.0)
    assert d1 == "SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK"
    assert sim.state == "STATE_CONFIRMED_LEAK_ALARM"

    # Window 2: Clean window 1 (Hysteresis count = 1, still in ALARM state)
    s1_clean1 = np.random.normal(12.0, 1.0, 60)
    d2, r2 = sim.evaluate_60s_window(s1_clean1, s2_norm, s1_thresh=25.0, s2_thresh=24.0)
    assert d2 == "NORMAL"
    assert sim.state == "STATE_CONFIRMED_LEAK_ALARM" # Not cleared yet!

    # Window 3: Clean window 2 (Hysteresis count = 2, clears to NORMAL)
    s1_clean2 = np.random.normal(12.0, 1.0, 60)
    d3, r3 = sim.evaluate_60s_window(s1_clean2, s2_norm, s1_thresh=25.0, s2_thresh=24.0)
    assert d3 == "NORMAL"
    assert sim.state == "STATE_MONITORING_NORMAL" # Alarm cleared!


def test_scenario_7_hardware_sensor_fault():
    """Test 7: ADC DC rail short (mean < 400 or > 3700) returns SENSOR OR CALIBRATION FAULT."""
    sim = DecisionEngineSimulator()
    s1_rms = np.full(60, 12.0)
    s2_rms = np.full(60, 11.5)
    s1_means = [100.0] * 60 # DC rail shorted to ground

    decision, reason = sim.evaluate_60s_window(s1_rms, s2_rms, s1_thresh=25.0, s2_thresh=24.0, s1_raw_means=s1_means)
    assert decision == "SENSOR OR CALIBRATION FAULT"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
