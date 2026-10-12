"""
AquaGuard AI Experimental CSV Data Analyzer
===========================================
Integrates Pandas & NumPy for analyzing and comparing experiment CSV datasets.
Preserves existing CSV files and computes statistics matching analyze_experiments.py.
"""
import os
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple
from app.models import ExperimentMetricsModel, ExperimentAnalysisResponse


def calculate_mad(series: pd.Series) -> float:
    median = series.median()
    return float((series - median).abs().median())


def analyze_csv_dataframe(df: pd.DataFrame, label: str, file_name: str, is_simulated: bool = True) -> ExperimentMetricsModel:
    df.columns = [c.strip() for c in df.columns]

    numeric_cols = ["s1_rms", "s1_p2p", "s1_variance", "s1_stvar",
                    "s2_rms", "s2_p2p", "s2_variance", "s2_stvar",
                    "s1_abnormal", "s2_abnormal", "is_transient"]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    total_seconds = len(df)
    if total_seconds == 0:
        return ExperimentMetricsModel(
            label=label,
            file_name=file_name,
            duration_sec=0,
            s1_rms_median=0.0, s1_rms_mad=0.0, s1_abn_pct=0.0, s1_max_seq=0, s1_var_ratio=0.0,
            s2_rms_median=0.0, s2_rms_mad=0.0, s2_abn_pct=0.0, s2_max_seq=0, s2_var_ratio=0.0,
            transient_count=0, is_simulated=is_simulated
        )

    # Sensor 1 Metrics
    s1_rms_med = float(df["s1_rms"].median()) if "s1_rms" in df.columns else 0.0
    s1_rms_mad = calculate_mad(df["s1_rms"]) if "s1_rms" in df.columns else 0.0
    s1_rms_mean = float(df["s1_rms"].mean()) if "s1_rms" in df.columns else 0.0
    s1_rms_std = float(df["s1_rms"].std()) if "s1_rms" in df.columns else 0.0
    s1_var_ratio = float(s1_rms_std / s1_rms_mean) if s1_rms_mean > 0 else 0.0

    s1_abn_count = int(df["s1_abnormal"].sum()) if "s1_abnormal" in df.columns else 0
    s1_abn_pct = float((s1_abn_count / total_seconds) * 100.0)

    s1_max_seq = 0
    if "s1_abnormal" in df.columns and s1_abn_count > 0:
        s1_runs = (df["s1_abnormal"] != df["s1_abnormal"].shift()).cumsum()
        s1_max_seq = int(df[df["s1_abnormal"] == 1].groupby(s1_runs).size().max())

    # Sensor 2 Metrics
    s2_rms_med = float(df["s2_rms"].median()) if "s2_rms" in df.columns else 0.0
    s2_rms_mad = calculate_mad(df["s2_rms"]) if "s2_rms" in df.columns else 0.0
    s2_rms_mean = float(df["s2_rms"].mean()) if "s2_rms" in df.columns else 0.0
    s2_rms_std = float(df["s2_rms"].std()) if "s2_rms" in df.columns else 0.0
    s2_var_ratio = float(s2_rms_std / s2_rms_mean) if s2_rms_mean > 0 else 0.0

    s2_abn_count = int(df["s2_abnormal"].sum()) if "s2_abnormal" in df.columns else 0
    s2_abn_pct = float((s2_abn_count / total_seconds) * 100.0)

    s2_max_seq = 0
    if "s2_abnormal" in df.columns and s2_abn_count > 0:
        s2_runs = (df["s2_abnormal"] != df["s2_abnormal"].shift()).cumsum()
        s2_max_seq = int(df[df["s2_abnormal"] == 1].groupby(s2_runs).size().max())

    transient_count = int(df["is_transient"].sum()) if "is_transient" in df.columns else 0

    return ExperimentMetricsModel(
        label=label,
        file_name=file_name,
        duration_sec=total_seconds,
        s1_rms_median=round(s1_rms_med, 2),
        s1_rms_mad=round(s1_rms_mad, 2),
        s1_abn_pct=round(s1_abn_pct, 1),
        s1_max_seq=s1_max_seq,
        s1_var_ratio=round(s1_var_ratio, 2),
        s2_rms_median=round(s2_rms_med, 2),
        s2_rms_mad=round(s2_rms_mad, 2),
        s2_abn_pct=round(s2_abn_pct, 1),
        s2_max_seq=s2_max_seq,
        s2_var_ratio=round(s2_var_ratio, 2),
        transient_count=transient_count,
        is_simulated=is_simulated
    )


def process_default_experiments(base_dir: str) -> ExperimentAnalysisResponse:
    files_to_check = [
        ("exp_normal.csv", "Normal Baseline", True),
        ("exp_pump_disturbance.csv", "Pump Disturbance", True),
        ("exp_confirmed_leak.csv", "Confirmed Leakage", True),
        ("real_normal.csv", "Real ESP32 Logged", False)
    ]

    summaries: List[ExperimentMetricsModel] = []
    previews: Dict[str, List[Dict[str, Any]]] = {}

    for file_name, label, default_sim in files_to_check:
        full_path = os.path.join(base_dir, file_name)
        if os.path.exists(full_path):
            try:
                df = pd.read_csv(full_path)
                metrics = analyze_csv_dataframe(df, label, file_name, is_simulated=default_sim)
                summaries.append(metrics)

                # Return time-series preview data for frontend plotting
                preview_rows = df.head(120).to_dict(orient="records")
                previews[file_name] = preview_rows
            except Exception as e:
                print(f"[ANALYSIS ERROR] Error processing {file_name}: {e}")

    return ExperimentAnalysisResponse(summaries=summaries, datasets_preview=previews)
