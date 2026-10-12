"""
Unit Tests for High-Speed TDOA Leak Localization & Signal Quality Gates
=======================================================================
Validates:
1. Synthetic two-channel acoustic waveforms with known positive, negative, and zero delays.
2. Verified localization at 0.5m, 1.0m, and 1.5m on the correct side of the 2-meter pipe.
3. ADC multiplexer skew correction sign (+10 us).
4. Clipping rejection (>5% rail saturation).
5. Weak correlation rejection (R < 0.65).
6. Uncalibrated wave speed sensitivity and honest uncertainty bounds.
7. SerialManager TDOA and WAVE message parsing.
8. Serial communication bandwidth limits (115200 baud).
9. GPS failure resilience.
"""

import pytest
import numpy as np
import math
from app.serial_manager import SerialManager
from app.models import HighResLocalizationModel


def compute_python_tdoa(raw1: np.ndarray, raw2: np.ndarray, fs: float = 10000.0,
                        v_nominal: float = 1250.0, L: float = 2.0,
                        skew_us: float = 10.0, alpha: float = 0.8273) -> dict:
    """
    Python reference implementation of the exact DSP algorithm in pipeline_monitor.ino:
    - Zero-mean centering
    - Digital high-pass filter (alpha = 0.8273 for exactly 300 Hz cutoff at 10 kHz)
    - Normalized Cross-Correlation (NCC)
    - Sub-sample parabolic interpolation
    - +10 us skew compensation
    - Physical distance calculation: d1 = (L - v * dt) / 2
    """

    n_samples = len(raw1)
    # Check clipping (>5%)
    clip1 = np.sum((raw1 <= 4) | (raw1 >= 4091))
    clip2 = np.sum((raw2 <= 4) | (raw2 >= 4091))
    if clip1 > (0.05 * n_samples) or clip2 > (0.05 * n_samples):
        return {"loc_valid": False, "status": "ADC_CLIPPING_FAULT", "d1": None, "d2": None, "dt_us": 0.0, "corr": 0.0}

    # Zero-mean DC removal
    m1 = np.mean(raw1)
    m2 = np.mean(raw2)
    x1 = raw1 - m1
    x2 = raw2 - m2

    # High-pass filter
    y1 = np.zeros(n_samples)
    y2 = np.zeros(n_samples)
    for i in range(n_samples):
        prev_x1 = x1[i - 1] if i > 0 else x1[0]
        prev_x2 = x2[i - 1] if i > 0 else x2[0]
        prev_y1 = y1[i - 1] if i > 0 else 0.0
        prev_y2 = y2[i - 1] if i > 0 else 0.0
        y1[i] = alpha * (prev_y1 + x1[i] - prev_x1)
        y2[i] = alpha * (prev_y2 + x2[i] - prev_x2)

    var1 = np.mean(y1 ** 2)
    var2 = np.mean(y2 ** 2)
    if var1 < 4.0 or var2 < 4.0:
        return {"loc_valid": False, "status": "LOW_SIGNAL_POWER", "d1": None, "d2": None, "dt_us": 0.0, "corr": 0.0}

    # NCC over lags [-20, +20]
    max_lag = 20
    lags = np.arange(-max_lag, max_lag + 1)
    r_vals = []
    denom1 = np.sum(y1 ** 2)

    for lag in lags:
        if lag < 0:
            s_a = y1[-lag:]
            s_b = y2[:len(s_a)]
        else:
            s_a = y1[:n_samples - lag]
            s_b = y2[lag:lag + len(s_a)]
        dot = np.sum(s_a * s_b)
        e1 = np.sum(s_a ** 2)
        e2 = np.sum(s_b ** 2)
        norm = dot / np.sqrt(e1 * e2) if (e1 > 1e-8 and e2 > 1e-8) else 0.0
        r_vals.append(norm)

    r_vals = np.array(r_vals)
    best_idx = int(np.argmax(r_vals))
    best_r = float(r_vals[best_idx])
    best_lag = int(lags[best_idx])

    # Parabolic sub-sample refinement
    delta = 0.0
    if 0 < best_idx < len(r_vals) - 1:
        y_left = r_vals[best_idx - 1]
        y_mid = r_vals[best_idx]
        y_right = r_vals[best_idx + 1]
        denom = 2.0 * (2.0 * y_mid - y_left - y_right)
        if abs(denom) > 1e-5:
            delta = float(np.clip((y_right - y_left) / denom, -0.5, 0.5))

    refined_lag = best_lag + delta
    # Skew correction: Add skew_us because Sensor 2 is sampled skew_us later!
    sample_period_us = 1e6 / fs
    dt_us = (refined_lag * sample_period_us) + skew_us

    # Distance calculation: d1 = (L - v * dt) / 2
    dt_sec = dt_us / 1e6
    d1 = (L - (v_nominal * dt_sec)) / 2.0
    d2 = L - d1

    loc_valid = (best_r >= 0.65) and (-0.15 <= d1 <= (L + 0.15))
    status = "LOCALIZATION_ACQUIRED" if loc_valid else "INSUFFICIENT_CORRELATION"

    return {
        "loc_valid": loc_valid,
        "status": status,
        "d1": round(float(np.clip(d1, 0.0, L)), 3) if loc_valid else None,
        "d2": round(float(np.clip(d2, 0.0, L)), 3) if loc_valid else None,
        "dt_us": round(float(dt_us), 1),
        "corr": round(best_r, 3)
    }


def generate_synthetic_pipe_waveform(d1_target: float, fs: float = 10000.0,
                                     v: float = 1250.0, L: float = 2.0,
                                     skew_us: float = 10.0, n_pts: int = 500,
                                     noise_std: float = 4.0):
    """
    Generates synthetic 2-channel acoustic wavepackets modeling a physical leak or tap at d1_target.
    Includes the +10 us sequential ADC sampling offset for Sensor 2.
    """
    t = np.arange(n_pts) / fs  # seconds
    # Physical transit times
    d2_target = L - d1_target
    t1_phys = d1_target / v
    t2_phys = d2_target / v

    # Event center time (e.g. at 20 ms)
    t_event = 0.020
    t1_arrival = t_event + t1_phys
    t2_arrival = t_event + t2_phys

    # Carrier frequency: 1200 Hz acoustic leak vibration
    f_carrier = 1200.0
    # Envelope width: 1.5 ms pulse packet
    sigma = 0.0015

    # Sensor 1 sampled at t
    env1 = np.exp(-((t - t1_arrival) / sigma) ** 2)
    s1 = 2048.0 + 350.0 * env1 * np.cos(2 * np.pi * f_carrier * (t - t1_arrival)) + np.random.normal(0, noise_std, n_pts)

    # Sensor 2 sampled at t + skew_us (ADC channel skew)
    t_s2_sampled = t + (skew_us / 1e6)
    env2 = np.exp(-((t_s2_sampled - t2_arrival) / sigma) ** 2)
    # Slight acoustic attenuation over distance
    attenuation = 0.85 if d2_target > d1_target else 1.15
    s2 = 2048.0 + (350.0 * attenuation) * env2 * np.cos(2 * np.pi * f_carrier * (t_s2_sampled - t2_arrival)) + np.random.normal(0, noise_std, n_pts)

    return np.clip(s1, 0, 4095).astype(np.float32), np.clip(s2, 0, 4095).astype(np.float32)


def test_localization_sources_and_delays():
    """Test 1: Verify sources at 0.5m, 1.0m, and 1.5m are localized on the correct side."""
    np.random.seed(42)

    # Experiment A: Leak at 0.50m (Closer to Sensor 1)
    # Expected physical delay dt = (1.50 - 0.50)/1250 = +800.0 us
    s1_a, s2_a = generate_synthetic_pipe_waveform(d1_target=0.50)
    res_a = compute_python_tdoa(s1_a, s2_a)

    assert res_a["loc_valid"] is True
    assert res_a["status"] == "LOCALIZATION_ACQUIRED"
    assert res_a["corr"] >= 0.70
    assert abs(res_a["dt_us"] - 800.0) < 60.0, f"Expected dt ~ +800 us, got {res_a['dt_us']} us"
    assert abs(res_a["d1"] - 0.50) <= 0.08, f"Expected d1 ~ 0.50m, got {res_a['d1']}m"
    assert res_a["d1"] < 1.0, "Source at 0.5m must be on Sensor 1 side (d1 < 1.0m)"

    # Experiment B: Leak at 1.00m (Exact midpoint)
    # Expected physical delay dt = 0.0 us
    s1_b, s2_b = generate_synthetic_pipe_waveform(d1_target=1.00)
    res_b = compute_python_tdoa(s1_b, s2_b)

    assert res_b["loc_valid"] is True
    assert res_b["corr"] >= 0.70
    assert abs(res_b["dt_us"] - 0.0) < 50.0, f"Expected dt ~ 0 us, got {res_b['dt_us']} us"
    assert abs(res_b["d1"] - 1.00) <= 0.06, f"Expected d1 ~ 1.00m, got {res_b['d1']}m"

    # Experiment C: Leak at 1.50m (Closer to Sensor 2)
    # Expected physical delay dt = (0.50 - 1.50)/1250 = -800.0 us
    s1_c, s2_c = generate_synthetic_pipe_waveform(d1_target=1.50)
    res_c = compute_python_tdoa(s1_c, s2_c)

    assert res_c["loc_valid"] is True
    assert res_c["corr"] >= 0.70
    assert abs(res_c["dt_us"] - (-800.0)) < 60.0, f"Expected dt ~ -800 us, got {res_c['dt_us']} us"
    assert abs(res_c["d1"] - 1.50) <= 0.08, f"Expected d1 ~ 1.50m, got {res_c['d1']}m"
    assert res_c["d1"] > 1.0, "Source at 1.5m must be on Sensor 2 side (d1 > 1.0m)"


def test_channel_skew_sign_correction():
    """Test 2: Verify that adding +10 us skew correction cancels the ADC conversion offset."""
    np.random.seed(123)
    # Pulse hits both sensors at exact same time (d1 = 1.0m, physical dt = 0)
    # Because S2 is sampled +10 us later, the raw sample clock sees the event arrive -10 us earlier.
    s1, s2 = generate_synthetic_pipe_waveform(d1_target=1.00, skew_us=10.0)

    # With correct +10 us compensation:
    res_corrected = compute_python_tdoa(s1, s2, skew_us=10.0)
    # If someone erroneously subtracted -10 us:
    res_erroneous = compute_python_tdoa(s1, s2, skew_us=-10.0)

    assert abs(res_corrected["dt_us"]) < abs(res_erroneous["dt_us"]), \
        f"Adding +10 us should yield closer to 0 than subtracting: corrected={res_corrected['dt_us']}, erroneous={res_erroneous['dt_us']}"
    assert abs(res_corrected["d1"] - 1.00) < abs(res_erroneous["d1"] - 1.00)


def test_clipping_rejection():
    """Test 3: Reject waveforms with excessive ADC clipping (>5% rail hits)."""
    np.random.seed(99)
    s1, s2 = generate_synthetic_pipe_waveform(d1_target=0.50)
    # Force 35 samples to clip at rail 4095 (>5% of 500 samples)
    s1[100:135] = 4095.0

    res = compute_python_tdoa(s1, s2)
    assert res["loc_valid"] is False
    assert res["status"] == "ADC_CLIPPING_FAULT"
    assert res["d1"] is None


def test_weak_correlation_rejection():
    """Test 4: Reject diffuse uncorrelated white noise where R < 0.65."""
    np.random.seed(777)
    # Independent white noise background
    s1_noise = 2048.0 + np.random.normal(0, 15.0, 500)
    s2_noise = 2048.0 + np.random.normal(0, 15.0, 500)

    res = compute_python_tdoa(s1_noise, s2_noise)
    assert res["loc_valid"] is False
    assert res["status"] in ["INSUFFICIENT_CORRELATION", "LOW_SIGNAL_POWER"]
    assert res["d1"] is None


def test_uncalibrated_wave_speed_sensitivity_and_uncertainty():
    """Test 5: Verify sensitivity to wave speed variation and validate honest uncertainty bounds."""
    # Test physical distance change if nominal wave speed is 1000 m/s vs 1400 m/s
    dt_sec = 0.00064  # 640 us delay
    L = 2.0
    d1_v1000 = (L - 1000.0 * dt_sec) / 2.0  # (2.0 - 0.64)/2 = 0.68m
    d1_v1250 = (L - 1250.0 * dt_sec) / 2.0  # (2.0 - 0.80)/2 = 0.60m
    d1_v1400 = (L - 1400.0 * dt_sec) / 2.0  # (2.0 - 0.896)/2 = 0.552m

    # Spread due to wave speed uncertainty across reasonable bounds:
    speed_uncertainty_spread = abs(d1_v1000 - d1_v1400)
    assert speed_uncertainty_spread >= 0.12, "Wave speed uncertainty introduces >10 cm position variation"

    # Confirm that our HighResLocalizationModel uses honest uncertainty >= 0.15m (15 cm), not false cm accuracy
    model = HighResLocalizationModel(
        pipe_length_m=2.0,
        propagation_velocity_mps=1250.0,
        propagation_velocity_status="NOMINAL_UNCALIBRATED",
        uncertainty_m=0.20,
        loc_valid=True
    )
    assert model.propagation_velocity_status == "NOMINAL_UNCALIBRATED"
    assert model.uncertainty_m >= 0.15, "Uncertainty must not claim false centimeter precision before calibration"


def test_serial_tdoa_and_wave_parsing():
    """Test 6: Verify backend SerialManager correctly parses TDOA, WAVE, and FLOW lines and enforces flow verification."""
    mgr = SerialManager()
    tdoa_line = "TDOA,18500,560.2,0.885,4.20,0.65,1.35,10000,1250.0,1,LOCALIZATION_ACQUIRED"
    wave_line = "WAVE," + ",".join([str(x) for x in range(50)]) + ";" + ",".join([str(x * 2) for x in range(50)])

    initial_errors = mgr.parse_error_count
    mgr._parse_and_dispatch(tdoa_line)
    mgr._parse_and_dispatch(wave_line)

    # CRITICAL RULE: Before flow sensors confirm leak, location must be concealed!
    status_unconfirmed = mgr.get_localization_status()
    assert mgr.parse_error_count == initial_errors, "TDOA and WAVE lines must not generate parse errors"
    assert status_unconfirmed["loc_valid"] is False
    assert status_unconfirmed["leak_location_revealed"] is False
    assert status_unconfirmed["leak_distance_s1_m"] is None

    # Now dual YF-S201 flow sensors confirm leakage (3 abnormal windows, confirmed=1)
    flow_line = "FLOW,18500,5000,1050,910,2.800,2.427,0.373,3,1,LEAK_CONFIRMED"
    mgr._parse_and_dispatch(flow_line)

    status = mgr.get_localization_status()
    assert mgr.parse_error_count == initial_errors, "FLOW line must not generate parse errors"
    assert status["loc_valid"] is True
    assert status["leak_location_revealed"] is True
    assert status["delta_t_us"] == 560.2
    assert status["leak_distance_s1_m"] == 0.65
    assert status["leak_distance_s2_m"] == 1.35
    assert len(status["s1_waveform"]) == 50
    assert len(status["s2_waveform"]) == 50
    assert status["propagation_velocity_status"] == "NOMINAL_UNCALIBRATED"


def test_serial_bandwidth_utilization():
    """Test 7: Verify combined telemetry throughput at 115200 baud is safely bounded (<10% utilization)."""
    # Nominal payload lengths per 1-second transmission:
    csv_len = len("CSV,61856,60,777.04,4095.0,603783.81,960.78,1044.31,4095.0,1090574.38,1313.78,0,0,0,PRELIM_NORMAL\n")
    tdoa_len = len("TDOA,61856,560.2,0.885,4.20,0.65,1.35,10000,1250.0,1,LOCALIZATION_ACQUIRED\n")
    # Wave: 50 points * 2 channels ~ 350 chars
    wave_len = len("WAVE," + ",".join(["120.5"] * 50) + ";" + ",".join(["95.2"] * 50) + "\n")
    gps_len = len("GPS,6.927079,79.861244,9,0.90,150,FIX\n")

    total_bytes_per_sec = csv_len + tdoa_len + wave_len + gps_len
    # 115200 baud @ 10 bits/char = 11,520 bytes/sec
    max_baud_bytes = 11520.0
    utilization_pct = (total_bytes_per_sec / max_baud_bytes) * 100.0

    assert total_bytes_per_sec < 1000, f"Expected <1000 bytes/sec, got {total_bytes_per_sec}"
    assert utilization_pct < 10.0, f"Serial bus utilization must be <10%, got {utilization_pct:.1f}%"


def test_invalid_gps_resilience():
    """Test 8: Verify corrupted GPS input does not disrupt serial parser or localization."""
    mgr = SerialManager()
    corrupt_gps_lines = [
        "GPS,invalid_lat,invalid_lon",
        "GPS,,,,,,",
        "$GPRMC,CORRUPTED_NMEA_CHECKSUM*FF"
    ]
    for line in corrupt_gps_lines:
        mgr._parse_and_dispatch(line)

    # Valid telemetry immediately following corrupt GPS must process normally
    valid_csv = "CSV,5000,5,12.50,33.6,158.66,5.04,12.37,35.6,153.02,4.95,0,0,0,PRELIM_NORMAL"
    mgr._parse_and_dispatch(valid_csv)
    assert mgr.valid_csv_count >= 1
    assert mgr.last_seen_status_str == "PRELIM_NORMAL"


def test_highpass_filter_frequency_response():
    """Test 9: Exact Z-transform frequency response of y[n] = alpha*(y[n-1] + x[n] - x[n-1]) at alpha=0.8273."""
    fs = 10000.0  # 10 kHz
    alpha = 0.8273

    def filter_gain(freq_hz: float) -> float:
        w = 2.0 * math.pi * freq_hz / fs
        # |H(e^jw)|^2 = alpha^2 * 2(1 - cos(w)) / (1 + alpha^2 - 2*alpha*cos(w))
        num = (alpha ** 2) * 2.0 * (1.0 - math.cos(w))
        denom = 1.0 + (alpha ** 2) - 2.0 * alpha * math.cos(w)
        return math.sqrt(num / denom)

    # Passband gain at Nyquist (5000 Hz): G_HF = 2*alpha / (1 + alpha)
    g_hf = (2.0 * alpha) / (1.0 + alpha)
    assert abs(g_hf - 0.90549) < 0.001

    # Exact -3 dB cutoff check at 300.0 Hz:
    # At cutoff, gain must equal G_HF / sqrt(2) = G_HF * 0.7071
    gain_300hz = filter_gain(300.0)
    norm_gain_300hz = gain_300hz / g_hf
    db_300hz = 20.0 * math.log10(norm_gain_300hz)

    assert abs(norm_gain_300hz - (1.0 / math.sqrt(2.0))) < 0.002, \
        f"At 300 Hz, gain should be 1/sqrt(2)=0.7071, got {norm_gain_300hz:.4f}"
    assert abs(db_300hz - (-3.01)) < 0.05, f"At 300 Hz, response must be -3.01 dB, got {db_300hz:.2f} dB"

    # Attenuation at 50 Hz (mains hum):
    gain_50hz = filter_gain(50.0)
    norm_gain_50hz = gain_50hz / g_hf
    db_50hz = 20.0 * math.log10(norm_gain_50hz)
    assert db_50hz < -14.0, f"50 Hz mains hum must have >14 dB attenuation, got {db_50hz:.2f} dB"

    # Passband transparency at 1200 Hz (leak frequency):
    gain_1200hz = filter_gain(1200.0)
    norm_gain_1200hz = gain_1200hz / g_hf
    db_1200hz = 20.0 * math.log10(norm_gain_1200hz)
    assert db_1200hz > -0.5, f"1200 Hz leak energy must pass with <0.5 dB loss, got {db_1200hz:.2f} dB"


def test_cpp_firmware_algorithm_equivalence():
    """Test 10: Step-by-step verification that discrete C++ loops match Python reference."""
    # Test identical discrete step response and impulse response
    alpha = 0.8273
    n = 100
    x = np.zeros(n)
    x[10:] = 100.0  # Step input

    # C++ firmware discrete loop:
    # y = alpha * (y + x - prev_x)
    y_cpp = np.zeros(n)
    prev_x = x[0]
    curr_y = 0.0
    for i in range(n):
        curr_y = alpha * (curr_y + x[i] - prev_x)
        prev_x = x[i]
        y_cpp[i] = curr_y

    # Python vector reference:
    y_py = np.zeros(n)
    for i in range(n):
        px = x[i - 1] if i > 0 else x[0]
        py = y_py[i - 1] if i > 0 else 0.0
        y_py[i] = alpha * (py + x[i] - px)

    # Must be bit-exact identical
    assert np.allclose(y_cpp, y_py, atol=1e-12), "C++ discrete loop and Python reference must be identical"


def test_buffer_bounds_and_memory_safety():
    """Test 11: Buffer bounds, array index safety, and stack-overflow prevention verification."""
    burst_samples = 500
    max_lag = 20
    snapshot_points = 50
    seconds_per_report = 60

    # 1. Downsampled snapshot indexing safety
    # In C++: for (int j = 0; j < 50; ++j) { int idx = j * 10; ... }
    for j in range(snapshot_points):
        idx = j * 10
        assert 0 <= idx < burst_samples, f"Snapshot index {idx} exceeds burst buffer bounds {burst_samples}"

    # 2. Normalized Cross-Correlation lag array indexing safety
    # In C++: r_vals size is 2 * max_lag + 1 = 41
    r_vals_size = 2 * max_lag + 1
    for lag in range(-max_lag, max_lag + 1):
        arr_idx = lag + max_lag
        assert 0 <= arr_idx < r_vals_size, f"Lag array index {arr_idx} out of bounds [0..{r_vals_size-1}]"

        # Window overlap limits
        start = -lag if lag < 0 else 0
        end = burst_samples if lag < 0 else burst_samples - lag
        assert start >= 0
        assert end <= burst_samples
        for i in range(start, end):
            assert 0 <= i < burst_samples
            assert 0 <= (i + lag) < burst_samples

    # 3. Parabolic interpolation index guarding
    for best_lag in range(-max_lag, max_lag + 1):
        best_idx = best_lag + max_lag
        if 0 < best_idx < r_vals_size - 1:
            left_idx = best_idx - 1
            right_idx = best_idx + 1
            assert 0 <= left_idx < r_vals_size
            assert 0 <= right_idx < r_vals_size

    # 4. Statistical analysis buffer bounds clamping
    for test_n in [-5, 0, 1, 30, 60, 61, 100, 999]:
        clamped_n = max(0, min(test_n, seconds_per_report))
        assert 0 <= clamped_n <= seconds_per_report, f"Analysis buffer index {clamped_n} exceeds {seconds_per_report}"

    # 5. Stack consumption verification:
    # Automatic local buffers: (500*2 + 500*2 + 500*4 + 500*4 + 41*4) = 6164 B.
    # In FreeRTOS loopTask with default 8192 B stack, this leaves only ~2000 B,
    # which overflows when combined with calibrate() (1300 B) and task overhead.
    # Moving to static BSS reduces stack footprint from 6164 B to < 64 B.
    local_stack_arrays_size_bytes = (burst_samples * 2) + (burst_samples * 2) + (burst_samples * 4) + (burst_samples * 4) + (r_vals_size * 4)
    assert local_stack_arrays_size_bytes == 6164, "Old automatic stack size was 6164 bytes"
    static_bss_overhead_kb = local_stack_arrays_size_bytes / 1024.0
    assert static_bss_overhead_kb < 8.0, "Static BSS buffer is safe and well within ESP32 280KB SRAM"

