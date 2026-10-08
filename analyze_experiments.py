#!/usr/bin/env python3
"""
ESP32 Pipeline Leakage Detection System - Experimental Data Analyzer
====================================================================
Uses Pandas and Matplotlib to analyze, compare, and plot vibration recordings from:
1. Normal operation (Pump running, no leak)
2. Transient disturbance (Pump speed change, dropped tool, valve tap)
3. Confirmed leakage (Sustained single-sensor or dual-sensor vibration elevation)

Calculates window statistics: Median RMS, MAD, Anomaly %, SNR (dB), Noise Variability,
and maximum consecutive abnormal run lengths.
"""

import argparse
import os
import sys
import numpy as np

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError as e:
    print(f"[ERROR] Missing required python package: {e}")
    print("Please install dependencies: pip install pandas matplotlib numpy")
    sys.exit(1)


def calculate_mad(series):
    """Calculate Median Absolute Deviation (MAD)."""
    median = series.median()
    return (series - median).abs().median()


def analyze_dataset(df, label="Dataset"):
    """
    Compute comprehensive DSP & statistical summary metrics for a given dataset.
    """
    # Filter CSV rows
    if "s1_rms" not in df.columns:
        # Try to clean CSV header if needed
        df.columns = [c.strip() for c in df.columns]

    # Convert numeric columns safely
    numeric_cols = ["s1_rms", "s1_p2p", "s1_variance", "s1_stvar",
                    "s2_rms", "s2_p2p", "s2_variance", "s2_stvar",
                    "s1_abnormal", "s2_abnormal", "is_transient"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    total_seconds = len(df)
    if total_seconds == 0:
        print(f"[WARNING] {label} has 0 records.")
        return {}

    # Sensor 1 Metrics
    s1_rms_med = df["s1_rms"].median()
    s1_rms_mad = calculate_mad(df["s1_rms"])
    s1_rms_mean = df["s1_rms"].mean()
    s1_rms_std = df["s1_rms"].std()
    s1_var_ratio = (s1_rms_std / s1_rms_mean) if s1_rms_mean > 0 else 0.0
    s1_abn_count = df["s1_abnormal"].sum()
    s1_abn_pct = (s1_abn_count / total_seconds) * 100.0

    # Consecutive run length for S1
    s1_runs = (df["s1_abnormal"] != df["s1_abnormal"].shift()).cumsum()
    s1_max_seq = df[df["s1_abnormal"] == 1].groupby(s1_runs).size().max() if s1_abn_count > 0 else 0

    # Sensor 2 Metrics
    s2_rms_med = df["s2_rms"].median()
    s2_rms_mad = calculate_mad(df["s2_rms"])
    s2_rms_mean = df["s2_rms"].mean()
    s2_rms_std = df["s2_rms"].std()
    s2_var_ratio = (s2_rms_std / s2_rms_mean) if s2_rms_mean > 0 else 0.0
    s2_abn_count = df["s2_abnormal"].sum()
    s2_abn_pct = (s2_abn_count / total_seconds) * 100.0

    # Consecutive run length for S2
    s2_runs = (df["s2_abnormal"] != df["s2_abnormal"].shift()).cumsum()
    s2_max_seq = df[df["s2_abnormal"] == 1].groupby(s2_runs).size().max() if s2_abn_count > 0 else 0

    transient_count = df["is_transient"].sum() if "is_transient" in df.columns else 0

    results = {
        "label": label,
        "duration_sec": total_seconds,
        "s1_rms_median": s1_rms_med,
        "s1_rms_mad": s1_rms_mad,
        "s1_abn_pct": s1_abn_pct,
        "s1_max_seq": s1_max_seq,
        "s1_var_ratio": s1_var_ratio,
        "s2_rms_median": s2_rms_med,
        "s2_rms_mad": s2_rms_mad,
        "s2_abn_pct": s2_abn_pct,
        "s2_max_seq": s2_max_seq,
        "s2_var_ratio": s2_var_ratio,
        "transient_count": transient_count
    }
    return results


def print_summary_table(summaries):
    """Print clean comparison table in ASCII markdown format."""
    print("\n=========================================================================================")
    print("                    EXPERIMENTAL ANALYSIS & COMPARISON SUMMARY                            ")
    print("=========================================================================================")
    header = f"{'Metric':<28} | {'Normal Baseline':<18} | {'Pump Disturbance':<18} | {'Confirmed Leak':<18}"
    print(header)
    print("-" * len(header))

    def get_val(key, fmt="%.2f"):
        vals = []
        for s in summaries:
            v = s.get(key, 0.0)
            if isinstance(v, float):
                vals.append(fmt % v)
            else:
                vals.append(str(v))
        while len(vals) < 3:
            vals.append("N/A")
        return vals

    metrics = [
        ("Duration (Seconds)", "duration_sec", "%d"),
        ("S1 RMS Median", "s1_rms_median", "%.2f"),
        ("S1 RMS MAD", "s1_rms_mad", "%.2f"),
        ("S1 Abnormal Sec (%)", "s1_abn_pct", "%.1f%%"),
        ("S1 Max Consec Seq (s)", "s1_max_seq", "%d"),
        ("S1 Noise Var (std/mean)", "s1_var_ratio", "%.2f"),
        ("S2 RMS Median", "s2_rms_median", "%.2f"),
        ("S2 RMS MAD", "s2_rms_mad", "%.2f"),
        ("S2 Abnormal Sec (%)", "s2_abn_pct", "%.1f%%"),
        ("S2 Max Consec Seq (s)", "s2_max_seq", "%d"),
        ("S2 Noise Var (std/mean)", "s2_var_ratio", "%.2f"),
        ("Transient Spikes Count", "transient_count", "%d"),
    ]

    for label, key, fmt in metrics:
        vals = get_val(key, fmt)
        print(f"{label:<28} | {vals[0]:<18} | {vals[1]:<18} | {vals[2]:<18}")

    print("=========================================================================================\n")


def plot_comparison_graphs(datasets, output_figure="experiment_analysis.png"):
    """
    Generate multi-panel diagnostic figure comparing vibration trends across conditions.
    """
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=False)
    fig.suptitle("ESP32 Pipeline Leakage Detection - Multi-Experiment Analysis", fontsize=14, fontweight="bold")

    colors = {"s1": "#1f77b4", "s2": "#ff7f0e", "thresh": "#d62728", "abn": "#2ca02c"}

    for idx, (df, name) in enumerate(datasets):
        col_idx = idx % 2
        row_offset = 0 if idx < 2 else 1

        time_axis = df["second_index"] if "second_index" in df.columns else np.arange(len(df))

        ax_rms = axes[row_offset, col_idx]
        ax_rms.plot(time_axis, df["s1_rms"], label="Sensor 1 RMS (GPIO 34)", color=colors["s1"], linewidth=1.5)
        ax_rms.plot(time_axis, df["s2_rms"], label="Sensor 2 RMS (GPIO 35)", color=colors["s2"], linewidth=1.5)

        # Baseline threshold estimate for plot
        s1_thresh = df["s1_rms"].median() * 2.2
        ax_rms.axhline(s1_thresh, color=colors["thresh"], linestyle="--", alpha=0.7, label=f"S1 Thresh ({s1_thresh:.1f})")

        ax_rms.set_title(f"Condition: {name}", fontsize=11, fontweight="bold")
        ax_rms.set_ylabel("RMS Amplitude (ADC Counts)")
        ax_rms.set_xlabel("Time (Seconds)")
        ax_rms.grid(True, linestyle=":", alpha=0.6)
        ax_rms.legend(loc="upper right", fontsize=8)

    # Plot peak-to-peak and anomaly timeline on remaining axes
    if len(datasets) >= 3:
        df_leak, name_leak = datasets[2]
        time_axis = df_leak["second_index"] if "second_index" in df_leak.columns else np.arange(len(df_leak))
        ax_p2p = axes[2, 0]
        ax_p2p.plot(time_axis, df_leak["s1_p2p"], label="S1 Peak-to-Peak", color="#9467bd")
        ax_p2p.plot(time_axis, df_leak["s2_p2p"], label="S2 Peak-to-Peak", color="#8c564b")
        ax_p2p.set_title(f"Peak-to-Peak Amplitude - {name_leak}", fontsize=11, fontweight="bold")
        ax_p2p.set_ylabel("P2P Amplitude")
        ax_p2p.set_xlabel("Time (Seconds)")
        ax_p2p.grid(True, linestyle=":", alpha=0.6)
        ax_p2p.legend(loc="upper right", fontsize=8)

        ax_abn = axes[2, 1]
        ax_abn.step(time_axis, df_leak["s1_abnormal"], label="S1 Abnormal Flag", color=colors["s1"], where="post")
        ax_abn.step(time_axis, df_leak["s2_abnormal"], label="S2 Abnormal Flag", color=colors["s2"], where="post")
        ax_abn.set_title(f"Per-Second Anomaly Timeline - {name_leak}", fontsize=11, fontweight="bold")
        ax_abn.set_ylabel("Abnormal Status (0/1)")
        ax_abn.set_xlabel("Time (Seconds)")
        ax_abn.set_ylim(-0.1, 1.2)
        ax_abn.grid(True, linestyle=":", alpha=0.6)
        ax_abn.legend(loc="upper right", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_figure, dpi=300)
    print(f"[INFO] Plot figure saved successfully to '{output_figure}'.")


def generate_demo_files():
    """Generate realistic synthetic CSV datasets for testing & demonstration."""
    print("[INFO] Generating synthetic experimental CSV files for testing...")
    np.random.seed(42)
    seconds = 120

    # 1. Normal Dataset
    t = np.arange(seconds)
    s1_norm_rms = 12.0 + np.random.normal(0, 1.2, seconds)
    s2_norm_rms = 11.5 + np.random.normal(0, 1.1, seconds)
    df_norm = pd.DataFrame({
        "esp32_ms": t * 1000,
        "second_index": t,
        "s1_rms": s1_norm_rms,
        "s1_p2p": s1_norm_rms * 2.8 + np.random.normal(0, 2, seconds),
        "s1_variance": s1_norm_rms ** 2,
        "s1_stvar": s1_norm_rms * 0.4,
        "s2_rms": s2_norm_rms,
        "s2_p2p": s2_norm_rms * 2.8 + np.random.normal(0, 2, seconds),
        "s2_variance": s2_norm_rms ** 2,
        "s2_stvar": s2_norm_rms * 0.4,
        "s1_abnormal": 0,
        "s2_abnormal": 0,
        "is_transient": 0,
        "status_str": "PRELIM_NORMAL"
    })
    df_norm.to_csv("exp_normal.csv", index=False)

    # 2. Pump Disturbance Dataset (High variability, transient spikes)
    s1_pump_rms = 12.0 + np.random.normal(0, 1.2, seconds)
    s2_pump_rms = 11.5 + np.random.normal(0, 1.1, seconds)
    # Add pump speed change at t=40..70 (High variance)
    s1_pump_rms[40:70] += np.random.uniform(10, 40, 30)
    s2_pump_rms[40:70] += np.random.uniform(8, 35, 30)
    # Add transient spikes
    transient = np.zeros(seconds, dtype=int)
    transient[[15, 25, 85]] = 1
    s1_pump_rms[[15, 25, 85]] += 50.0

    df_pump = pd.DataFrame({
        "esp32_ms": t * 1000,
        "second_index": t,
        "s1_rms": s1_pump_rms,
        "s1_p2p": s1_pump_rms * 3.5 + np.random.normal(0, 5, seconds),
        "s1_variance": s1_pump_rms ** 2,
        "s1_stvar": s1_pump_rms * 0.6,
        "s2_rms": s2_pump_rms,
        "s2_p2p": s2_pump_rms * 3.5 + np.random.normal(0, 5, seconds),
        "s2_variance": s2_pump_rms ** 2,
        "s2_stvar": s2_pump_rms * 0.6,
        "s1_abnormal": (s1_pump_rms > 25.0).astype(int),
        "s2_abnormal": (s2_pump_rms > 25.0).astype(int),
        "is_transient": transient,
        "status_str": "PRELIM_TRANSIENT"
    })
    df_pump.to_csv("exp_pump_disturbance.csv", index=False)

    # 3. Confirmed Leak Dataset (Sensor 1 20x sustained elevation, Sensor 2 slight elevation)
    s1_leak_rms = 12.0 + np.random.normal(0, 1.2, seconds)
    s2_leak_rms = 11.5 + np.random.normal(0, 1.1, seconds)
    # Micro-leak introduced at t=30 seconds onwards
    s1_leak_rms[30:] = 240.0 + np.random.normal(0, 8.0, seconds - 30) # 20x increase!
    s2_leak_rms[30:] = 18.0 + np.random.normal(0, 2.0, seconds - 30)  # Slight elevation due to attenuation

    s1_abn = (s1_leak_rms > 25.0).astype(int)
    s2_abn = (s2_leak_rms > 25.0).astype(int)

    df_leak = pd.DataFrame({
        "esp32_ms": t * 1000,
        "second_index": t,
        "s1_rms": s1_leak_rms,
        "s1_p2p": s1_leak_rms * 2.8 + np.random.normal(0, 3, seconds),
        "s1_variance": s1_leak_rms ** 2,
        "s1_stvar": s1_leak_rms * 0.4,
        "s2_rms": s2_leak_rms,
        "s2_p2p": s2_leak_rms * 2.8 + np.random.normal(0, 3, seconds),
        "s2_variance": s2_leak_rms ** 2,
        "s2_stvar": s2_leak_rms * 0.4,
        "s1_abnormal": s1_abn,
        "s2_abnormal": s2_abn,
        "is_transient": 0,
        "status_str": "PRELIM_ABNORMAL"
    })
    df_leak.to_csv("exp_confirmed_leak.csv", index=False)
    print("[INFO] Created 'exp_normal.csv', 'exp_pump_disturbance.csv', and 'exp_confirmed_leak.csv'.")


def main():
    parser = argparse.ArgumentParser(description="Analyze and Plot ESP32 Pipeline Leakage Experiments")
    parser.add_argument("--files", nargs="+", help="CSV data files to analyze (up to 3 files)")
    parser.add_argument("--generate-demo", action="store_true", help="Generate synthetic demo datasets and run comparison")
    parser.add_argument("--output-figure", type=str, default="experiment_analysis.png", help="Path for output PNG plot figure")
    args = parser.parse_args()

    if args.generate_demo or not args.files:
        generate_demo_files()
        file_paths = ["exp_normal.csv", "exp_pump_disturbance.csv", "exp_confirmed_leak.csv"]
    else:
        file_paths = args.files

    datasets = []
    summaries = []

    for fp in file_paths:
        if not os.path.exists(fp):
            print(f"[ERROR] File '{fp}' not found.")
            continue
        try:
            df = pd.read_csv(fp)
            label = os.path.basename(fp).replace(".csv", "").replace("exp_", "").replace("_", " ").title()
            datasets.append((df, label))
            summary = analyze_dataset(df, label=label)
            summaries.append(summary)
        except Exception as e:
            print(f"[ERROR] Could not read file '{fp}': {e}")

    if summaries:
        print_summary_table(summaries)

    if datasets:
        plot_comparison_graphs(datasets, output_figure=args.output_figure)


if __name__ == "__main__":
    main()
