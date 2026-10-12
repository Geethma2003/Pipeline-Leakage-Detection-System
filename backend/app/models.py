"""
Pydantic Models & Data Schemas for AquaGuard AI
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SensorFeaturesModel(BaseModel):
    rms: float = 0.0
    p2p: float = 0.0
    variance: float = 0.0
    st_var: float = 0.0


class TelemetryRecord(BaseModel):
    pc_timestamp: str
    esp32_ms: int = 0
    second_index: int = 0
    s1_rms: float = 0.0
    s1_p2p: float = 0.0
    s1_variance: float = 0.0
    s1_stvar: float = 0.0
    s2_rms: float = 0.0
    s2_p2p: float = 0.0
    s2_variance: float = 0.0
    s2_stvar: float = 0.0
    s1_abnormal: int = 0
    s2_abnormal: int = 0
    is_transient: int = 0
    status_str: str = "PRELIM_NORMAL"
    is_demo: bool = False


class BaselineProfileModel(BaseModel):
    s1_rms_median: float = 12.0
    s1_rms_mad: float = 1.2
    s1_thresh: float = 25.0
    s2_rms_median: float = 11.5
    s2_rms_mad: float = 1.1
    s2_thresh: float = 24.0
    is_calibrated: bool = True
    calibrated_at: Optional[str] = None


class WindowDecisionModel(BaseModel):
    id: Optional[int] = None
    window_index: int
    timestamp: str
    decision: str
    reasoning: str
    s1_abnormal_count: int
    s2_abnormal_count: int
    s1_max_seq: int
    s2_max_seq: int
    s1_med_rms: float
    s2_med_rms: float
    s1_var_ratio: float
    s2_var_ratio: float
    tdoa_sec: float = 0.0
    peak_corr: float = 0.0
    loc_valid: bool = False
    estimated_distance_m: Optional[float] = None
    is_demo: bool = False


class EventRecordModel(BaseModel):
    id: int
    timestamp: str
    status: str
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    s1_abnormal_sec: int
    s2_abnormal_sec: int
    s1_med_rms: float
    s2_med_rms: float
    reasoning: str
    operator_status: str = "UNCONFIRMED"  # "UNCONFIRMED", "ACKNOWLEDGED", "CONFIRMED_LEAK", "FALSE_ALARM"
    operator_note: Optional[str] = None
    is_demo: bool = False


class SerialConfigModel(BaseModel):
    port: str
    baud_rate: int = 115200
    connected: bool = False
    connection_state: str = "DISCONNECTED"  # "DISCONNECTED", "CONNECTING", "CONNECTED", "CALIBRATING", "STREAMING", "STALE", "ERROR"
    auto_reconnect: bool = True
    output_mode: str = "CSV"  # "CSV" or "DEMO"
    verbose_mode: bool = True
    last_seen_timestamp: float = 0.0
    last_error: Optional[str] = None
    status_str: str = "PRELIM_NORMAL"


class HardwareDiagnosticsModel(BaseModel):
    serial_port: str
    baud_rate: int
    connection_status: str  # "CONNECTED", "DISCONNECTED", "DEMO_MODE", "PORT_LOCKED"
    esp32_uptime_sec: int = 0
    sample_rate_hz: int = 2500
    timing_overruns: int = 0
    s1_adc_offset_ok: bool = True
    s2_adc_offset_ok: bool = True
    pipe_length_m: float = 2.0
    s1_position_m: float = 0.0
    s2_position_m: float = 2.0
    last_error: Optional[str] = None
    data_freshness: str = "LIVE"  # "LIVE", "DELAYED", "STALE", "DISCONNECTED"
    last_record_timestamp: float = 0.0
    last_record_age_sec: float = 0.0
    telemetry_hz: float = 1.0
    # Detailed Raw ADC Diagnostics (GPIO 34 & GPIO 35)
    s1_min: int = 0
    s1_max: int = 4095
    s1_mean: float = 2048.0
    s1_clips: int = 0
    s1_clip_pct: float = 0.0
    s2_min: int = 0
    s2_max: int = 4095
    s2_mean: float = 2048.0
    s2_clips: int = 0
    s2_clip_pct: float = 0.0


class ADCDiagnosticsModel(BaseModel):
    s1_min: int = 0
    s1_max: int = 4095
    s1_mean: float = 2048.0
    s1_clips: int = 0
    s1_clip_pct: float = 0.0
    s2_min: int = 0
    s2_max: int = 4095
    s2_mean: float = 2048.0
    s2_clips: int = 0
    s2_clip_pct: float = 0.0
    is_clipping: bool = False
    status: str = "OK"  # "OK", "ADC_CLIPPING_FAULT", "BIAS_DRIFT_WARNING"
    last_updated: float = 0.0


class ExperimentMetricsModel(BaseModel):
    label: str
    file_name: str
    duration_sec: int
    s1_rms_median: float
    s1_rms_mad: float
    s1_abn_pct: float
    s1_max_seq: int
    s1_var_ratio: float
    s2_rms_median: float
    s2_rms_mad: float
    s2_abn_pct: float
    s2_max_seq: int
    s2_var_ratio: float
    transient_count: int
    is_simulated: bool = True


class ExperimentAnalysisResponse(BaseModel):
    summaries: List[ExperimentMetricsModel]
    datasets_preview: Dict[str, List[Dict[str, Any]]]


class GPSDataModel(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    satellites: int = 0
    hdop: float = 99.99
    fix_age_ms: int = 999999
    fix_status: str = "NO_FIX"  # "FIX", "NO_FIX", "STALE"
    is_stale: bool = True
    is_demo: bool = False
    last_updated: float = 0.0


class FlowTelemetryModel(BaseModel):
    esp32_ms: int = 0
    interval_ms: int = 5000
    in_pulses: int = 0
    out_pulses: int = 0
    flow_in_lpm: float = 0.0
    flow_out_lpm: float = 0.0
    flow_diff_lpm: float = 0.0
    leak_progress: int = 0  # 0..3 windows
    leak_confirmed: bool = False
    status: str = "NO_FLOW"
    last_updated: float = 0.0


class HighResLocalizationModel(BaseModel):
    pipe_length_m: float = 2.0
    s1_pos_m: float = 0.0
    s2_pos_m: float = 2.0
    delta_t_us: float = 0.0
    sample_rate_hz: int = 10000
    propagation_velocity_mps: float = 1250.0
    propagation_velocity_status: str = "NOMINAL_UNCALIBRATED"
    leak_distance_s1_m: Optional[float] = None
    leak_distance_s2_m: Optional[float] = None
    confidence_pct: float = 0.0
    uncertainty_m: float = 0.20
    correlation_peak: float = 0.0
    psr: float = 0.0
    status: str = "LOCATION UNAVAILABLE — INSUFFICIENT SIGNAL QUALITY"
    loc_valid: bool = False
    flow_confirmed_leak: bool = False
    leak_location_revealed: bool = False
    event_id: Optional[int] = None
    failure_code: Optional[int] = 0
    failure_reason: Optional[str] = None
    s1_waveform: List[float] = []
    s2_waveform: List[float] = []
    last_updated: float = 0.0


class WirelessTelemetryModel(BaseModel):
    utc_timestamp: str
    node_id: int = 1
    packet_sequence: int = 0
    flow_in_lpm: float = 0.0
    flow_out_lpm: float = 0.0
    flow_diff_lpm: float = 0.0
    leak_alarm: bool = False
    rms1: float = 0.0
    p2p1: int = 0
    rms2: float = 0.0
    p2p2: int = 0
    s1_clipped: bool = False
    s2_clipped: bool = False
    vibration_invalid: bool = False
    gps_valid: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    satellites: int = 0
    hdop: float = 99.9
    gps_time: Optional[str] = None
    missed_packets: int = 0
    sequence_reset: int = 0
    communication_source: str = "ARDUINO_UNO_NRF24"
    status_str: str = "NORMAL"
    is_demo: bool = False
    last_updated: float = 0.0


class TelemetryStreamPayload(BaseModel):
    type: str  # "telemetry_update", "window_completed", "system_state_change", "baseline_updated"
    system_state: str
    demo_mode: bool
    demo_scenario: str
    telemetry: Optional[TelemetryRecord] = None
    baseline: BaselineProfileModel
    current_window_sec: int
    window_decision: Optional[WindowDecisionModel] = None
    diagnostics: HardwareDiagnosticsModel
    gps: Optional[GPSDataModel] = None
    localization: Optional[HighResLocalizationModel] = None
    adc: Optional[ADCDiagnosticsModel] = None
    flow: Optional[FlowTelemetryModel] = None
    wireless: Optional[WirelessTelemetryModel] = None


