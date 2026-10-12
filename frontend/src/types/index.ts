export interface TelemetryRecord {
  pc_timestamp: string;
  esp32_ms: number;
  second_index: number;
  s1_rms: number;
  s1_p2p: number;
  s1_variance: number;
  s1_stvar: number;
  s2_rms: number;
  s2_p2p: number;
  s2_variance: number;
  s2_stvar: number;
  s1_abnormal: number;
  s2_abnormal: number;
  is_transient: number;
  status_str: string;
  is_demo: boolean;
}

export interface BaselineProfile {
  s1_rms_median: number;
  s1_rms_mad: number;
  s1_thresh: number;
  s2_rms_median: number;
  s2_rms_mad: number;
  s2_thresh: number;
  is_calibrated: boolean;
  calibrated_at?: string;
}

export interface WindowDecision {
  id?: number;
  window_index: number;
  timestamp: string;
  decision: string; // "NORMAL", "TRANSIENT DISTURBANCE", "SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK", "SENSOR OR CALIBRATION FAULT"
  reasoning: string;
  s1_abnormal_count: number;
  s2_abnormal_count: number;
  s1_max_seq: number;
  s2_max_seq: number;
  s1_med_rms: number;
  s2_med_rms: number;
  s1_var_ratio: number;
  s2_var_ratio: number;
  tdoa_sec: number;
  peak_corr: number;
  loc_valid: boolean;
  estimated_distance_m?: number | null;
  is_demo: boolean;
}

export interface EventRecord {
  id: number;
  timestamp: string;
  status: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  s1_abnormal_sec: number;
  s2_abnormal_sec: number;
  s1_med_rms: number;
  s2_med_rms: number;
  reasoning: string;
  operator_status: "UNCONFIRMED" | "ACKNOWLEDGED" | "CONFIRMED_LEAK" | "FALSE_ALARM";
  operator_note?: string;
  is_demo: boolean;
}

export interface HardwareDiagnostics {
  serial_port: string;
  baud_rate: number;
  connection_status: "CONNECTED" | "DISCONNECTED" | "DEMO_MODE" | "PORT_LOCKED";
  esp32_uptime_sec: number;
  sample_rate_hz: number;
  timing_overruns: number;
  s1_adc_offset_ok: boolean;
  s2_adc_offset_ok: boolean;
  pipe_length_m: number;
  s1_position_m: number;
  s2_position_m: number;
  last_error?: string | null;
  data_freshness?: "LIVE" | "DELAYED" | "STALE" | "DISCONNECTED";
  last_record_timestamp?: number;
  last_record_age_sec?: number;
  telemetry_hz?: number;
  s1_min?: number;
  s1_max?: number;
  s1_mean?: number;
  s1_clips?: number;
  s1_clip_pct?: number;
  s2_min?: number;
  s2_max?: number;
  s2_mean?: number;
  s2_clips?: number;
  s2_clip_pct?: number;
}

export interface ADCDiagnostics {
  s1_min: number;
  s1_max: number;
  s1_mean: number;
  s1_clips: number;
  s1_clip_pct: number;
  s2_min: number;
  s2_max: number;
  s2_mean: number;
  s2_clips: number;
  s2_clip_pct: number;
  is_clipping: boolean;
  status: string;
  last_updated: number;
}

export interface ExperimentMetrics {
  label: string;
  file_name: string;
  duration_sec: number;
  s1_rms_median: number;
  s1_rms_mad: number;
  s1_abn_pct: number;
  s1_max_seq: number;
  s1_var_ratio: number;
  s2_rms_median: number;
  s2_rms_mad: number;
  s2_abn_pct: number;
  s2_max_seq: number;
  s2_var_ratio: number;
  transient_count: number;
  is_simulated: boolean;
}

export interface ExperimentAnalysisResponse {
  summaries: ExperimentMetrics[];
  datasets_preview: Record<string, any[]>;
}

export interface GPSData {
  latitude: number | null;
  longitude: number | null;
  satellites: number;
  hdop: number;
  fix_age_ms: number;
  fix_status: "FIX" | "NO_FIX" | "STALE" | string;
  is_stale: boolean;
  is_demo?: boolean;
  last_updated: number;
}

export interface FlowTelemetry {
  esp32_ms: number;
  interval_ms: number;
  in_pulses: number;
  out_pulses: number;
  flow_in_lpm: number;
  flow_out_lpm: number;
  flow_diff_lpm: number;
  leak_progress: number;
  leak_confirmed: boolean;
  status: string;
  last_updated?: number;
}

export interface HighResLocalization {
  pipe_length_m: number;
  s1_pos_m: number;
  s2_pos_m: number;
  delta_t_us: number;
  sample_rate_hz: number;
  propagation_velocity_mps: number;
  propagation_velocity_status?: string;
  leak_distance_s1_m: number | null;
  leak_distance_s2_m: number | null;
  confidence_pct: number;
  uncertainty_m: number;
  correlation_peak: number;
  psr: number;
  status: string;
  loc_valid: boolean;
  flow_confirmed_leak?: boolean;
  leak_location_revealed?: boolean;
  s1_waveform?: number[];
  s2_waveform?: number[];
  last_updated?: number;
}

export interface WirelessTelemetry {
  utc_timestamp: string;
  node_id: number;
  packet_sequence: number;
  flow_in_lpm: number;
  flow_out_lpm: number;
  flow_diff_lpm: number;
  leak_alarm: boolean;
  rms1: number;
  p2p1: number;
  rms2: number;
  p2p2: number;
  s1_clipped: boolean;
  s2_clipped: boolean;
  vibration_invalid: boolean;
  gps_valid: boolean;
  latitude: number | null;
  longitude: number | null;
  satellites: number;
  hdop: number;
  gps_time?: string | null;
  missed_packets: number;
  sequence_reset: number;
  communication_source: string;
  status_str: string;
  is_demo: boolean;
  last_updated: number;
}

export interface TelemetryStreamPayload {
  type: string;
  system_state: "INITIALIZING" | "NORMAL" | "SUSPECTED_ANOMALY" | "CONFIRMED_LEAK" | "SENSOR_FAULT" | "COMMUNICATION_LOST" | "LOW_OR_NO_FLOW" | string;
  demo_mode: boolean;
  demo_scenario: "normal" | "pump_disturbance" | "confirmed_leak";
  telemetry: TelemetryRecord | null;
  baseline: BaselineProfile;
  current_window_sec: number;
  window_decision?: WindowDecision | null;
  diagnostics: HardwareDiagnostics;
  gps?: GPSData | null;
  localization?: HighResLocalization | null;
  adc?: ADCDiagnostics | null;
  flow?: FlowTelemetry | null;
  wireless?: WirelessTelemetry | null;
}

export interface SerialPortInfo {
  device: string;
  description: string;
  hwid: string;
  is_arduino?: boolean;
  is_esp32?: boolean;
}


