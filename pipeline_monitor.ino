/*
 * ESP32 Pipeline Leakage Detection System
 * ---------------------------------------
 * Hardware Architecture:
 * - Microcontroller: ESP32 Dev Module (3.3V Logic)
 * - Sensor 1: Piezoelectric Vibration Transducer on GPIO 34 (ADC1_CH6, Input Only)
 * - Sensor 2: Piezoelectric Vibration Transducer on GPIO 35 (ADC1_CH7, Input Only)
 * - Pipeline: 2.0 Meter Steel Water Pipeline with standard operating pump
 * - Serial Interface: 115200 Baud Rate
 *
 * Signal Conditioning Circuit (Mandatory for safe ADC operation):
 * - DC Bias: 100k/100k voltage divider to 3.3V rail with 10uF bypass cap creating ~1.65V mid-rail offset.
 * - AC Coupling: 0.1uF ceramic capacitor in series with piezo positive node.
 * - Discharge/Impedance: 1M resistor across piezo element.
 * - Overvoltage Protection: Dual Schottky clamping diodes (BAT54S or 1N4148) to 3.3V and GND.
 * - Anti-Aliasing LP Filter: 10k resistor + 10nF capacitor (fc = 1.59 kHz).
 *
 * Key Design Principles:
 * 1. 60-Second Windowed Multi-Criteria Analysis (Never judge on single high sample).
 * 2. Independent Sensor Anomaly Detection (S1 can increase 20x while S2 stays baseline due to attenuation).
 * 3. Noise-Aware Robust Baseline (Median, MAD, dynamic thresholds, absolute floors).
 * 4. Sustained Anomaly vs. Transient Spike vs. Sensor Fault Classification.
 * 5. Honest Uncertainty in Localization (Requires cross-correlation quality check; otherwise LOCATION NOT VERIFIED).
 */

#include <Arduino.h>

// ============================================================================
// CONFIGURABLE SYSTEM PARAMETERS & CONSTANTS
// ============================================================================

// Hardware Pins (ADC1 channels on ESP32, safe from WiFi interference)
static const uint8_t PIN_SENSOR_1 = 34;
static const uint8_t PIN_SENSOR_2 = 35;

// Sampling Configuration
static const uint32_t SAMPLE_RATE_HZ       = 1000;      // 1000 Hz sampling per channel
static const uint32_t SAMPLE_PERIOD_US      = 1000000UL / SAMPLE_RATE_HZ; // 1000 us
static const uint16_t SAMPLES_PER_SECOND    = 1000;      // 1-second analysis window size
static const uint16_t MAX_RAW_BUFFER_SIZE  = 1000;      // Samples per second buffer

// System Timing & Windows
static const uint16_t CALIBRATION_SECONDS   = 60;        // 60-second baseline calibration
static const uint16_t ANALYSIS_WINDOW_SEC   = 60;        // 60-second sliding history buffer
static const uint16_t STABILIZE_SECONDS     = 5;         // Initial power/pump stabilization delay

// Anomaly & Persistence Thresholds (Experimental Settings)
static const uint16_t DEFAULT_PERSISTENCE_SEC = 42;      // 42 out of 60 abnormal seconds required (70%)
static const uint16_t MIN_CONSECUTIVE_ABN     = 15;      // Minimum consecutive abnormal seconds run length
static float MAD_MULTIPLIER                   = 3.5f;    // Threshold offset = median + 3.5 * MAD
static float RMS_FACTOR_MULTIPLIER            = 2.2f;    // Threshold offset = median * 2.2
static const float MIN_RMS_ABSOLUTE_FLOOR     = 15.0f;   // Minimum threshold floor (ADC counts)
static const float MIN_P2P_ABSOLUTE_FLOOR    = 40.0f;   // Minimum P2P floor (ADC counts)

// Transient & Noise Classification Bounds
static const float MAX_VARIABILITY_RATIO      = 0.48f;   // Max RMS std-dev / mean ratio for sustained noise
static const float CREST_FACTOR_SPIKE_LIMIT   = 7.0f;    // Crest factor > 7 indicates impulse transient spike

// Hardware & ADC Fault Bounds (12-bit ADC: 0..4095)
static const float ADC_RAW_MIN_VALID          = 400.0f;  // Lower rail short/disconnection threshold (~0.32V)
static const float ADC_RAW_MAX_VALID          = 3700.0f; // Upper rail short threshold (~2.98V)
static const float ADC_FLATLINE_VARIANCE_MIN  = 0.1f;    // Disconnected pin / flatline variance

// Pipeline & Acoustic Localization Constants
static const float PIPE_LENGTH_METERS        = 2.0f;    // Sensor spacing = 2.0 m
static const float ACOUSTIC_SPEED_MPS        = 1200.0f; // Nominal speed of sound in water-filled steel pipe (m/s)
static const float MIN_CORRELATION_PEAK      = 0.65f;   // Minimum cross-correlation coefficient for location trust

// ============================================================================
// DATA STRUCTURES
// ============================================================================

enum SystemState {
  STATE_STABILIZING,
  STATE_CALIBRATING,
  STATE_MONITORING_NORMAL,
  STATE_SUSPECTED_ANOMALY,
  STATE_CONFIRMED_LEAK_ALARM,
  STATE_SENSOR_FAULT
};

struct SensorFeatures {
  float mean_raw;
  float rms;
  float variance;
  float p2p;
  float st_var;         // Short-term variation (mean absolute consecutive difference)
  float zcr;            // Zero crossing rate (crossings/sec)
  float crest_factor;
};

struct SecondRecord {
  uint32_t second_index;
  SensorFeatures s1;
  SensorFeatures s2;
  bool s1_abnormal;
  bool s2_abnormal;
  bool is_transient;
};

struct BaselineProfile {
  float s1_rms_median;
  float s1_rms_mad;
  float s1_p2p_median;
  float s1_rms_thresh;
  float s1_p2p_thresh;

  float s2_rms_median;
  float s2_rms_mad;
  float s2_p2p_median;
  float s2_rms_thresh;
  float s2_p2p_thresh;

  bool is_calibrated;
};

// ============================================================================
// GLOBAL STATE & BUFFERS
// ============================================================================

SystemState g_system_state = STATE_STABILIZING;
BaselineProfile g_baseline = {0};

// Raw 1-second sample buffers (used for DSP feature calculation & cross-correlation)
float g_s1_raw_window[SAMPLES_PER_SECOND];
float g_s2_raw_window[SAMPLES_PER_SECOND];
uint16_t g_sample_count = 0;

// 60-Second Circular History Buffer
SecondRecord g_history[ANALYSIS_WINDOW_SEC];
uint16_t g_history_count = 0;
uint16_t g_history_head  = 0;

// Calibration accumulator arrays (60 entries)
float g_cal_s1_rms[CALIBRATION_SECONDS];
float g_cal_s1_p2p[CALIBRATION_SECONDS];
float g_cal_s2_rms[CALIBRATION_SECONDS];
float g_cal_s2_p2p[CALIBRATION_SECONDS];
uint16_t g_cal_index = 0;

// Diagnostics & Timing Performance Metrics
uint32_t g_total_seconds_elapsed = 0;
uint32_t g_timing_overrun_count  = 0;
uint32_t g_last_sample_us        = 0;
bool     g_verbose_mode          = true;
bool     g_csv_mode              = false;
uint16_t g_persistence_req       = DEFAULT_PERSISTENCE_SEC;

// Alarm hysteresis tracker
uint16_t g_normal_windows_in_alarm = 0;

// ============================================================================
// FUNCTION DECLARATIONS
// ============================================================================

void processSample(uint16_t s1_adc, uint16_t s2_adc);
SensorFeatures computeFeatures(const float* buffer, uint16_t length);
void computeBaselineStatistics();
void evaluateCurrentSecond(SensorFeatures f1, SensorFeatures f2);
void analyze60SecondWindow();
void performCrossCorrelationLocalization(float* tdoa_sec_out, float* peak_corr_out, bool* valid_out);
void handleSerialCommands();
void printHelp();
void printStatusReport();
void printFull60SecondReport(const char* state_str, uint16_t s1_abn, uint16_t s2_abn, 
                             uint16_t s1_max_seq, uint16_t s2_max_seq, 
                             float s1_med_rms, float s2_med_rms,
                             float s1_var_ratio, float s2_var_ratio,
                             float tdoa_sec, float peak_corr, bool loc_valid,
                             const char* reasoning);
float calculateMedian(float* array, uint16_t size);
float calculateMAD(float* array, uint16_t size, float median);

// ============================================================================
// ARDUINO SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000); // Wait for Serial Monitor

  analogReadResolution(12); // ESP32 12-bit ADC (0..4095)
  
  // Set GPIO pin modes explicitly
  pinMode(PIN_SENSOR_1, INPUT);
  pinMode(PIN_SENSOR_2, INPUT);

  Serial.println(F("\n=================================================="));
  Serial.println(F("    ESP32 PIPELINE LEAKAGE DETECTION SYSTEM      "));
  Serial.println(F("=================================================="));
  Serial.printf("Sensors: GPIO %d (S1), GPIO %d (S2)\n", PIN_SENSOR_1, PIN_SENSOR_2);
  Serial.printf("Sampling Rate: %d Hz | Window: %d Sec\n", SAMPLE_RATE_HZ, ANALYSIS_WINDOW_SEC);
  Serial.println(F("Type 'H' or 'HELP' for serial command menu."));
  Serial.println(F("==================================================\n"));

  g_last_sample_us = micros();
}

// ============================================================================
// ARDUINO MAIN LOOP
// ============================================================================

void loop() {
  // Handle user input over Serial
  handleSerialCommands();

  // Precise sampling clock check
  uint32_t now_us = micros();
  if (now_us - g_last_sample_us >= SAMPLE_PERIOD_US) {
    if (now_us - g_last_sample_us > (SAMPLE_PERIOD_US + 150)) {
      g_timing_overrun_count++;
    }
    g_last_sample_us += SAMPLE_PERIOD_US;

    // Read ADC channels
    uint16_t raw_s1 = analogRead(PIN_SENSOR_1);
    uint16_t raw_s2 = analogRead(PIN_SENSOR_2);

    processSample(raw_s1, raw_s2);
  }
}

// ============================================================================
// SIGNAL PROCESSING & WINDOW MANAGEMENT
// ============================================================================

void processSample(uint16_t s1_adc, uint16_t s2_adc) {
  g_s1_raw_window[g_sample_count] = (float)s1_adc;
  g_s2_raw_window[g_sample_count] = (float)s2_adc;
  g_sample_count++;

  // When a full 1-second window (1000 samples) is collected:
  if (g_sample_count >= SAMPLES_PER_SECOND) {
    g_total_seconds_elapsed++;

    // Compute DSP features for both channels
    SensorFeatures f1 = computeFeatures(g_s1_raw_window, SAMPLES_PER_SECOND);
    SensorFeatures f2 = computeFeatures(g_s2_raw_window, SAMPLES_PER_SECOND);

    // Reset sample index for next second
    g_sample_count = 0;

    // Execute state logic
    switch (g_system_state) {
      case STATE_STABILIZING: {
        if (g_csv_mode) {
          Serial.printf("LOG,%lu,%u,STABILIZING,0,0,0,0,0,0\n", millis(), g_total_seconds_elapsed);
        } else if (g_verbose_mode) {
          Serial.printf("[STABILIZING %u/%d] S1 ADC Mean: %.1f | S2 ADC Mean: %.1f\n", 
                        g_total_seconds_elapsed, STABILIZE_SECONDS, f1.mean_raw, f2.mean_raw);
        }
        if (g_total_seconds_elapsed >= STABILIZE_SECONDS) {
          g_system_state = STATE_CALIBRATING;
          g_cal_index = 0;
          Serial.println(F("\n>>> PUMP STABILIZED. STARTING 60-SECOND NO-LEAK BASELINE CALIBRATION... <<<"));
          Serial.println(F("Ensure pipeline is operating normally with pump ON and NO LEAK present.\n"));
        }
        break;
      }

      case STATE_CALIBRATING: {
        g_cal_s1_rms[g_cal_index] = f1.rms;
        g_cal_s1_p2p[g_cal_index] = f1.p2p;
        g_cal_s2_rms[g_cal_index] = f2.rms;
        g_cal_s2_p2p[g_cal_index] = f2.p2p;
        g_cal_index++;

        if (g_csv_mode) {
          Serial.printf("CAL,%lu,%u,%.2f,%.2f,%.2f,%.2f\n", 
                        millis(), g_cal_index, f1.rms, f1.p2p, f2.rms, f2.p2p);
        } else if (g_verbose_mode) {
          Serial.printf("[CALIBRATING %u/%d] S1 RMS: %.2f P2P: %.1f | S2 RMS: %.2f P2P: %.1f\n",
                        g_cal_index, CALIBRATION_SECONDS, f1.rms, f1.p2p, f2.rms, f2.p2p);
        }

        if (g_cal_index >= CALIBRATION_SECONDS) {
          computeBaselineStatistics();
          g_system_state = STATE_MONITORING_NORMAL;
          g_history_count = 0;
          g_history_head  = 0;
          Serial.println(F("\n>>> CALIBRATION COMPLETE. ENTERING REAL-TIME MONITORING MODE. <<<\n"));
        }
        break;
      }

      case STATE_MONITORING_NORMAL:
      case STATE_SUSPECTED_ANOMALY:
      case STATE_CONFIRMED_LEAK_ALARM:
      case STATE_SENSOR_FAULT: {
        evaluateCurrentSecond(f1, f2);
        break;
      }
    }
  }
}

// Compute per-window statistical & DSP features (DC-removed RMS, variance, P2P, ZCR, ST-Var)
SensorFeatures computeFeatures(const float* buffer, uint16_t length) {
  SensorFeatures feat = {0};
  if (length == 0) return feat;

  // 1. Compute Raw Mean (DC Offset)
  double sum = 0.0;
  float max_val = buffer[0];
  float min_val = buffer[0];

  for (uint16_t i = 0; i < length; i++) {
    float val = buffer[i];
    sum += val;
    if (val > max_val) max_val = val;
    if (val < min_val) min_val = val;
  }
  feat.mean_raw = (float)(sum / length);
  feat.p2p = max_val - min_val;

  // 2. DC Removal and Variance/RMS computation
  double sq_sum = 0.0;
  double diff_sum = 0.0;
  uint32_t zero_crossings = 0;

  float prev_ac = buffer[0] - feat.mean_raw;

  for (uint16_t i = 0; i < length; i++) {
    float ac_val = buffer[i] - feat.mean_raw;
    sq_sum += (double)ac_val * (double)ac_val;

    if (i > 0) {
      diff_sum += fabsf(buffer[i] - buffer[i - 1]);
      if ((prev_ac < 0.0f && ac_val >= 0.0f) || (prev_ac >= 0.0f && ac_val < 0.0f)) {
        zero_crossings++;
      }
    }
    prev_ac = ac_val;
  }

  feat.variance = (float)(sq_sum / length);
  feat.rms = sqrtf(feat.variance);
  feat.st_var = (float)(diff_sum / (length - 1));
  feat.zcr = (float)zero_crossings;

  float peak_ac = fabsf(max_val - feat.mean_raw) > fabsf(min_val - feat.mean_raw) ?
                  fabsf(max_val - feat.mean_raw) : fabsf(min_val - feat.mean_raw);
  feat.crest_factor = (feat.rms > 0.001f) ? (peak_ac / feat.rms) : 0.0f;

  return feat;
}

// Compute dynamic baseline thresholds using median & MAD
void computeBaselineStatistics() {
  // Compute Sensor 1 RMS baseline statistics
  float s1_rms_temp[CALIBRATION_SECONDS];
  float s1_p2p_temp[CALIBRATION_SECONDS];
  float s2_rms_temp[CALIBRATION_SECONDS];
  float s2_p2p_temp[CALIBRATION_SECONDS];

  for (uint16_t i = 0; i < CALIBRATION_SECONDS; i++) {
    s1_rms_temp[i] = g_cal_s1_rms[i];
    s1_p2p_temp[i] = g_cal_s1_p2p[i];
    s2_rms_temp[i] = g_cal_s2_rms[i];
    s2_p2p_temp[i] = g_cal_s2_p2p[i];
  }

  g_baseline.s1_rms_median = calculateMedian(s1_rms_temp, CALIBRATION_SECONDS);
  g_baseline.s1_rms_mad    = calculateMAD(g_cal_s1_rms, CALIBRATION_SECONDS, g_baseline.s1_rms_median);
  g_baseline.s1_p2p_median = calculateMedian(s1_p2p_temp, CALIBRATION_SECONDS);

  g_baseline.s2_rms_median = calculateMedian(s2_rms_temp, CALIBRATION_SECONDS);
  g_baseline.s2_rms_mad    = calculateMAD(g_cal_s2_rms, CALIBRATION_SECONDS, g_baseline.s2_rms_median);
  g_baseline.s2_p2p_median = calculateMedian(s2_p2p_temp, CALIBRATION_SECONDS);

  // Compute noise-aware dynamic thresholds with absolute safety floor
  float s1_t1 = g_baseline.s1_rms_median + (MAD_MULTIPLIER * g_baseline.s1_rms_mad);
  float s1_t2 = g_baseline.s1_rms_median * RMS_FACTOR_MULTIPLIER;
  g_baseline.s1_rms_thresh = max(max(s1_t1, s1_t2), MIN_RMS_ABSOLUTE_FLOOR);
  g_baseline.s1_p2p_thresh = max(g_baseline.s1_p2p_median * 2.5f, MIN_P2P_ABSOLUTE_FLOOR);

  float s2_t1 = g_baseline.s2_rms_median + (MAD_MULTIPLIER * g_baseline.s2_rms_mad);
  float s2_t2 = g_baseline.s2_rms_median * RMS_FACTOR_MULTIPLIER;
  g_baseline.s2_rms_thresh = max(max(s2_t1, s2_t2), MIN_RMS_ABSOLUTE_FLOOR);
  g_baseline.s2_p2p_thresh = max(g_baseline.s2_p2p_median * 2.5f, MIN_P2P_ABSOLUTE_FLOOR);

  g_baseline.is_calibrated = true;

  Serial.println(F("---------------- CALIBRATION RESULTS ----------------"));
  Serial.printf("Sensor 1 Baseline RMS Median: %.2f | MAD: %.2f | Dynamic Thresh: %.2f\n", 
                g_baseline.s1_rms_median, g_baseline.s1_rms_mad, g_baseline.s1_rms_thresh);
  Serial.printf("Sensor 2 Baseline RMS Median: %.2f | MAD: %.2f | Dynamic Thresh: %.2f\n", 
                g_baseline.s2_rms_median, g_baseline.s2_rms_mad, g_baseline.s2_rms_thresh);
  Serial.println(F("----------------------------------------------------\n"));
}

// Evaluate each 1-second record, mark preliminary flags, add to circular buffer
void evaluateCurrentSecond(SensorFeatures f1, SensorFeatures f2) {
  // Hardware Fault Check
  bool hardware_fault = false;
  if (f1.mean_raw < ADC_RAW_MIN_VALID || f1.mean_raw > ADC_RAW_MAX_VALID ||
      f2.mean_raw < ADC_RAW_MIN_VALID || f2.mean_raw > ADC_RAW_MAX_VALID ||
      f1.variance < ADC_FLATLINE_VARIANCE_MIN || f2.variance < ADC_FLATLINE_VARIANCE_MIN) {
    hardware_fault = true;
    g_system_state = STATE_SENSOR_FAULT;
  }

  // Single-second threshold comparison
  bool s1_abn = (f1.rms > g_baseline.s1_rms_thresh);
  bool s2_abn = (f2.rms > g_baseline.s2_rms_thresh);

  // Transient impulse spike check (high P2P / crest factor but non-sustained)
  bool transient = (f1.crest_factor > CREST_FACTOR_SPIKE_LIMIT || f2.crest_factor > CREST_FACTOR_SPIKE_LIMIT ||
                    (f1.p2p > g_baseline.s1_p2p_thresh && !s1_abn) ||
                    (f2.p2p > g_baseline.s2_p2p_thresh && !s2_abn));

  // Store into 60-second circular buffer
  SecondRecord rec;
  rec.second_index = g_total_seconds_elapsed;
  rec.s1 = f1;
  rec.s2 = f2;
  rec.s1_abnormal = s1_abn;
  rec.s2_abnormal = s2_abn;
  rec.is_transient = transient;

  g_history[g_history_head] = rec;
  g_history_head = (g_history_head + 1) % ANALYSIS_WINDOW_SEC;
  if (g_history_count < ANALYSIS_WINDOW_SEC) {
    g_history_count++;
  }

  // Live 1-second diagnostic line (Explicitly marked as PRELIMINARY)
  if (g_csv_mode) {
    Serial.printf("CSV,%lu,%lu,%.2f,%.1f,%.2f,%.2f,%.2f,%.1f,%.2f,%.2f,%d,%d,%d,%s\n",
                  millis(), rec.second_index,
                  f1.rms, f1.p2p, f1.variance, f1.st_var,
                  f2.rms, f2.p2p, f2.variance, f2.st_var,
                  s1_abn ? 1 : 0, s2_abn ? 1 : 0, transient ? 1 : 0,
                  hardware_fault ? "FAULT" : ((s1_abn || s2_abn) ? "PRELIM_ABNORMAL" : "PRELIM_NORMAL"));
  } else if (g_verbose_mode) {
    const char* prelim_status = hardware_fault ? "[FAULT]" : 
                               (s1_abn && s2_abn) ? "[PRELIM ABNORMAL: S1+S2]" :
                               s1_abn ? "[PRELIM ABNORMAL: S1 ONLY]" :
                               s2_abn ? "[PRELIM ABNORMAL: S2 ONLY]" :
                               transient ? "[PRELIM TRANSIENT SPIKE]" : "[PRELIM NORMAL]";

    Serial.printf("[LIVE-DIAG %02u/%d] S1 RMS: %5.1f (Th: %5.1f) | S2 RMS: %5.1f (Th: %5.1f) %s\n",
                  g_history_count, ANALYSIS_WINDOW_SEC,
                  f1.rms, g_baseline.s1_rms_thresh,
                  f2.rms, g_baseline.s2_rms_thresh,
                  prelim_status);
  }

  // Trigger 60-Second Comprehensive Decision Evaluation
  if (g_history_count >= ANALYSIS_WINDOW_SEC && (g_total_seconds_elapsed % ANALYSIS_WINDOW_SEC == 0)) {
    analyze60SecondWindow();
  }
}

// ============================================================================
// 60-SECOND COMPREHENSIVE MULTI-CRITERIA EVALUATION ENGINE
// ============================================================================

void analyze60SecondWindow() {
  uint16_t s1_abn_count = 0;
  uint16_t s2_abn_count = 0;
  uint16_t transient_count = 0;

  uint16_t s1_consec = 0, s1_max_consec = 0;
  uint16_t s2_consec = 0, s2_max_consec = 0;

  float s1_rms_vals[ANALYSIS_WINDOW_SEC];
  float s2_rms_vals[ANALYSIS_WINDOW_SEC];

  float s1_rms_sum = 0.0f, s2_rms_sum = 0.0f;

  for (uint16_t i = 0; i < ANALYSIS_WINDOW_SEC; i++) {
    SecondRecord r = g_history[i];
    s1_rms_vals[i] = r.s1.rms;
    s2_rms_vals[i] = r.s2.rms;
    s1_rms_sum += r.s1.rms;
    s2_rms_sum += r.s2.rms;

    if (r.s1_abnormal) {
      s1_abn_count++;
      s1_consec++;
      if (s1_consec > s1_max_consec) s1_max_consec = s1_consec;
    } else {
      s1_consec = 0;
    }

    if (r.s2_abnormal) {
      s2_abn_count++;
      s2_consec++;
      if (s2_consec > s2_max_consec) s2_max_consec = s2_consec;
    } else {
      s2_consec = 0;
    }

    if (r.is_transient) transient_count++;
  }

  // Window Summary Statistics
  float s1_med_rms = calculateMedian(s1_rms_vals, ANALYSIS_WINDOW_SEC);
  float s2_med_rms = calculateMedian(s2_rms_vals, ANALYSIS_WINDOW_SEC);

  float s1_mean_rms = s1_rms_sum / ANALYSIS_WINDOW_SEC;
  float s2_mean_rms = s2_rms_sum / ANALYSIS_WINDOW_SEC;

  // Calculate Noise Variability Ratio (Standard Deviation / Mean)
  float s1_sq_diff = 0.0f, s2_sq_diff = 0.0f;
  for (uint16_t i = 0; i < ANALYSIS_WINDOW_SEC; i++) {
    s1_sq_diff += (s1_rms_vals[i] - s1_mean_rms) * (s1_rms_vals[i] - s1_mean_rms);
    s2_sq_diff += (s2_rms_vals[i] - s2_mean_rms) * (s2_rms_vals[i] - s2_mean_rms);
  }
  float s1_std = sqrtf(s1_sq_diff / ANALYSIS_WINDOW_SEC);
  float s2_std = sqrtf(s2_sq_diff / ANALYSIS_WINDOW_SEC);

  float s1_var_ratio = (s1_mean_rms > 0.001f) ? (s1_std / s1_mean_rms) : 0.0f;
  float s2_var_ratio = (s2_mean_rms > 0.001f) ? (s2_std / s2_mean_rms) : 0.0f;

  // Cross-Correlation Localization Check
  float tdoa_sec = 0.0f, peak_corr = 0.0f;
  bool  loc_valid = false;
  performCrossCorrelationLocalization(&tdoa_sec, &peak_corr, &loc_valid);

  // DECISION MATRIX
  // 1. Hardware / Sensor Fault
  if (g_system_state == STATE_SENSOR_FAULT) {
    printFull60SecondReport("SENSOR OR CALIBRATION FAULT",
                            s1_abn_count, s2_abn_count, s1_max_consec, s2_max_consec,
                            s1_med_rms, s2_med_rms, s1_var_ratio, s2_var_ratio,
                            tdoa_sec, peak_corr, false,
                            "ADC voltage out of bounds or signal flatline detected.");
    return;
  }

  // 2. Sustained Anomaly Criteria Check (EITHER SENSOR RULE)
  // Sensor 1 OR Sensor 2 exhibits persistent elevation over 42/60s AND sustained run length
  bool s1_sustained = (s1_abn_count >= g_persistence_req) && (s1_max_consec >= MIN_CONSECUTIVE_ABN) && (s1_var_ratio <= MAX_VARIABILITY_RATIO);
  bool s2_sustained = (s2_abn_count >= g_persistence_req) && (s2_max_consec >= MIN_CONSECUTIVE_ABN) && (s2_var_ratio <= MAX_VARIABILITY_RATIO);

  if (s1_sustained || s2_sustained) {
    // Lock system in anomaly state (Baseline adaptation IS FROZEN)
    g_system_state = STATE_CONFIRMED_LEAK_ALARM;
    g_normal_windows_in_alarm = 0;

    String reasoning = "SUSTAINED ANOMALY DETECTED: ";
    if (s1_sustained && s2_sustained) {
      reasoning += "Both S1 and S2 show continuous vibration elevation (>=" + String(g_persistence_req) + "/60s).";
    } else if (s1_sustained) {
      reasoning += "Sensor 1 elevated (" + String(s1_abn_count) + "/60s, " + String((int)(s1_med_rms/g_baseline.s1_rms_median)) + "x increase) while Sensor 2 near baseline. Consistent with high acoustic attenuation in pipeline.";
    } else {
      reasoning += "Sensor 2 elevated (" + String(s2_abn_count) + "/60s, " + String((int)(s2_med_rms/g_baseline.s2_rms_median)) + "x increase) while Sensor 1 near baseline.";
    }

    printFull60SecondReport("SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK",
                            s1_abn_count, s2_abn_count, s1_max_consec, s2_max_consec,
                            s1_med_rms, s2_med_rms, s1_var_ratio, s2_var_ratio,
                            tdoa_sec, peak_corr, loc_valid,
                            reasoning.c_str());
  }
  // 3. Transient Disturbance Check (Spikes, pump speed changes, short tapping)
  else if ((s1_abn_count >= 10 || s2_abn_count >= 10) || transient_count > 12 || 
           s1_var_ratio > MAX_VARIABILITY_RATIO || s2_var_ratio > MAX_VARIABILITY_RATIO) {
    
    // If we were previously in ALARM state, check hysteresis before clearing
    if (g_system_state == STATE_CONFIRMED_LEAK_ALARM) {
      g_normal_windows_in_alarm++;
      if (g_normal_windows_in_alarm >= 2) {
        g_system_state = STATE_MONITORING_NORMAL;
        g_normal_windows_in_alarm = 0;
      }
    }

    String reasoning = "TRANSIENT DISTURBANCE: ";
    if (s1_var_ratio > MAX_VARIABILITY_RATIO || s2_var_ratio > MAX_VARIABILITY_RATIO) {
      reasoning += "High vibration variability (std/mean > 0.48) indicates pump speed fluctuation, valve operation, or mechanical handling noise.";
    } else {
      reasoning += "Short-duration spikes (" + String(transient_count) + " transient seconds) without 60s sustained duration.";
    }

    printFull60SecondReport("TRANSIENT DISTURBANCE",
                            s1_abn_count, s2_abn_count, s1_max_consec, s2_max_consec,
                            s1_med_rms, s2_med_rms, s1_var_ratio, s2_var_ratio,
                            tdoa_sec, peak_corr, false,
                            reasoning.c_str());
  }
  // 4. Normal Pipeline Operation
  else {
    if (g_system_state == STATE_CONFIRMED_LEAK_ALARM) {
      g_normal_windows_in_alarm++;
      if (g_normal_windows_in_alarm >= 2) {
        g_system_state = STATE_MONITORING_NORMAL;
        g_normal_windows_in_alarm = 0;
      }
    } else {
      g_system_state = STATE_MONITORING_NORMAL;
    }

    printFull60SecondReport("NORMAL",
                            s1_abn_count, s2_abn_count, s1_max_consec, s2_max_consec,
                            s1_med_rms, s2_med_rms, s1_var_ratio, s2_var_ratio,
                            tdoa_sec, peak_corr, false,
                            "Vibration levels within baseline statistical bounds across full 60s window.");
  }
}

// Perform discrete TDOA cross-correlation on the last collected 1-second raw waveform
void performCrossCorrelationLocalization(float* tdoa_sec_out, float* peak_corr_out, bool* valid_out) {
  *tdoa_sec_out = 0.0f;
  *peak_corr_out = 0.0f;
  *valid_out = false;

  // Zero-mean the 1-second raw arrays
  double s1_sum = 0, s2_sum = 0;
  for (uint16_t i = 0; i < SAMPLES_PER_SECOND; i++) {
    s1_sum += g_s1_raw_window[i];
    s2_sum += g_s2_raw_window[i];
  }
  float s1_m = (float)(s1_sum / SAMPLES_PER_SECOND);
  float s2_m = (float)(s2_sum / SAMPLES_PER_SECOND);

  double s1_energy = 0, s2_energy = 0;
  for (uint16_t i = 0; i < SAMPLES_PER_SECOND; i++) {
    float x1 = g_s1_raw_window[i] - s1_m;
    float x2 = g_s2_raw_window[i] - s2_m;
    s1_energy += x1 * x1;
    s2_energy += x2 * x2;
  }

  if (s1_energy < 10.0 || s2_energy < 10.0) return; // Signal too quiet for correlation

  double norm_denom = sqrt(s1_energy * s2_energy);

  // Search lag range corresponding to max acoustic delay across 2.0 m pipe
  // Acoustic delay max = 2.0m / 1200m/s = 1.67 ms. At 1000 Hz sample rate, 1.67 ms = ~2 samples.
  int max_lag_samples = 8; 
  int best_lag = 0;
  double max_corr = -1.0;

  for (int lag = -max_lag_samples; lag <= max_lag_samples; lag++) {
    double r_12 = 0.0;
    int count = 0;

    for (int n = 0; n < SAMPLES_PER_SECOND; n++) {
      int m = n + lag;
      if (m >= 0 && m < SAMPLES_PER_SECOND) {
        float x1 = g_s1_raw_window[n] - s1_m;
        float x2 = g_s2_raw_window[m] - s2_m;
        r_12 += x1 * x2;
        count++;
      }
    }
    double corr_coeff = r_12 / norm_denom;
    if (corr_coeff > max_corr) {
      max_corr = corr_coeff;
      best_lag = lag;
    }
  }

  *peak_corr_out = (float)max_corr;
  *tdoa_sec_out  = ((float)best_lag) / (float)SAMPLE_RATE_HZ;

  // Check validity conditions (Requirements: bandwidth/timing/correlation quality)
  // At 1000 Hz sampling rate, 1 sample resolution = 1 ms (~1.2m error on 2m pipe).
  // Cross-correlation is ONLY marked valid if correlation coefficient R > 0.65.
  if (*peak_corr_out >= MIN_CORRELATION_PEAK) {
    *valid_out = true;
  } else {
    *valid_out = false;
  }
}

// ============================================================================
// SERIAL COMMAND INTERFACE & REPORTING
// ============================================================================

void handleSerialCommands() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "H" || cmd == "HELP") {
      printHelp();
    } else if (cmd == "B" || cmd == "CAL") {
      if (g_system_state == STATE_CONFIRMED_LEAK_ALARM) {
        Serial.println(F("\n[WARNING] Cannot recalibrate baseline while in CONFIRMED LEAK ALARM state. Confirm pipeline is leak-free first!"));
      } else {
        Serial.println(F("\n[COMMAND] Manual Baseline Recalibration Triggered."));
        g_system_state = STATE_CALIBRATING;
        g_cal_index = 0;
      }
    } else if (cmd == "V" || cmd == "VERBOSE") {
      g_verbose_mode = !g_verbose_mode;
      Serial.printf("[COMMAND] Live Verbose Diagnostic Output: %s\n", g_verbose_mode ? "ENABLED" : "DISABLED");
    } else if (cmd == "M" || cmd == "MODE") {
      g_csv_mode = !g_csv_mode;
      Serial.printf("[COMMAND] Serial Output Format: %s\n", g_csv_mode ? "MACHINE CSV" : "HUMAN READABLE");
    } else if (cmd == "S" || cmd == "STATUS") {
      printStatusReport();
    } else if (cmd.startsWith("P ") || cmd.startsWith("PARAM ")) {
      int space_idx = cmd.indexOf(' ');
      int val = cmd.substring(space_idx + 1).toInt();
      if (val >= 10 && val <= 60) {
        g_persistence_req = val;
        Serial.printf("[COMMAND] Updated Persistence Threshold to %d out of 60 seconds.\n", g_persistence_req);
      } else {
        Serial.println(F("[ERROR] Invalid persistence parameter. Must be between 10 and 60 seconds."));
      }
    } else if (cmd.length() > 0) {
      Serial.printf("[ERROR] Unknown command '%s'. Type 'H' or 'HELP' for menu.\n", cmd.c_str());
    }
  }
}

void printHelp() {
  Serial.println(F("\n=================== SERIAL COMMAND MENU ==================="));
  Serial.println(F("  H or HELP      - Display this help menu"));
  Serial.println(F("  B or CAL       - Perform 60-sec baseline recalibration (Only when leak-free)"));
  Serial.println(F("  V or VERBOSE   - Toggle 1-second live preliminary diagnostics"));
  Serial.println(F("  M or MODE      - Toggle output mode (Human-Readable vs CSV Machine format)"));
  Serial.println(F("  S or STATUS    - Display current baseline calibration & system metrics"));
  Serial.println(F("  P <10-60>      - Set persistence threshold seconds (Default: 42/60)"));
  Serial.println(F("===========================================================\n"));
}

void printStatusReport() {
  Serial.println(F("\n================ SYSTEM STATUS REPORT ================"));
  Serial.printf("State: %s | Total Run Time: %lu sec\n", 
                (g_system_state == STATE_STABILIZING) ? "STABILIZING" :
                (g_system_state == STATE_CALIBRATING) ? "CALIBRATING" :
                (g_system_state == STATE_MONITORING_NORMAL) ? "MONITORING_NORMAL" :
                (g_system_state == STATE_SUSPECTED_ANOMALY) ? "SUSPECTED_ANOMALY" :
                (g_system_state == STATE_CONFIRMED_LEAK_ALARM) ? "CONFIRMED_LEAK_ALARM" : "SENSOR_FAULT",
                g_total_seconds_elapsed);
  Serial.printf("Sampling Rate: %d Hz | Timing Overruns: %lu\n", SAMPLE_RATE_HZ, g_timing_overrun_count);
  Serial.printf("Persistence Threshold: %u / 60 seconds\n", g_persistence_req);

  if (g_baseline.is_calibrated) {
    Serial.printf("S1 Baseline RMS Med: %.2f | MAD: %.2f | Threshold: %.2f\n",
                  g_baseline.s1_rms_median, g_baseline.s1_rms_mad, g_baseline.s1_rms_thresh);
    Serial.printf("S2 Baseline RMS Med: %.2f | MAD: %.2f | Threshold: %.2f\n",
                  g_baseline.s2_rms_median, g_baseline.s2_rms_mad, g_baseline.s2_rms_thresh);
  } else {
    Serial.println(F("Baseline: NOT YET CALIBRATED"));
  }
  Serial.println(F("======================================================\n"));
}

void printFull60SecondReport(const char* state_str, uint16_t s1_abn, uint16_t s2_abn, 
                             uint16_t s1_max_seq, uint16_t s2_max_seq, 
                             float s1_med_rms, float s2_med_rms,
                             float s1_var_ratio, float s2_var_ratio,
                             float tdoa_sec, float peak_corr, bool loc_valid,
                             const char* reasoning) {
  
  Serial.println(F("\n================================================================================"));
  Serial.printf("           60-SECOND PIPELINE MONITORING REPORT (Window #%lu)\n", g_total_seconds_elapsed / ANALYSIS_WINDOW_SEC);
  Serial.println(F("================================================================================"));
  Serial.printf("FINAL DECISION:        [%s]\n", state_str);
  Serial.printf("DECISION REASONING:    %s\n", reasoning);
  Serial.println(F("--------------------------------------------------------------------------------"));
  Serial.println(F("METRIC                     | SENSOR 1 (GPIO 34)       | SENSOR 2 (GPIO 35)       "));
  Serial.println(F("---------------------------+--------------------------+-------------------------"));
  Serial.printf("Baseline RMS Median        | %-24.2f | %-24.2f\n", g_baseline.s1_rms_median, g_baseline.s2_rms_median);
  Serial.printf("Dynamic Threshold          | %-24.2f | %-24.2f\n", g_baseline.s1_rms_thresh, g_baseline.s2_rms_thresh);
  Serial.printf("60s Window RMS Median      | %-24.2f | %-24.2f\n", s1_med_rms, s2_med_rms);
  Serial.printf("Vibration Increase Ratio   | %-24.2fx| %-24.2fx\n", 
                g_baseline.s1_rms_median > 0 ? (s1_med_rms / g_baseline.s1_rms_median) : 1.0f,
                g_baseline.s2_rms_median > 0 ? (s2_med_rms / g_baseline.s2_rms_median) : 1.0f);
  Serial.printf("Abnormal Seconds Count     | %-24u | %-24u\n", s1_abn, s2_abn);
  Serial.printf("Abnormal Percentage        | %-23.1f%% | %-23.1f%%\n", (s1_abn/60.0f)*100.0f, (s2_abn/60.0f)*100.0f);
  Serial.printf("Max Consecutive Sequence   | %-24u | %-24u\n", s1_max_seq, s2_max_seq);
  Serial.printf("Noise Variability (std/mean)| %-24.2f | %-24.2f\n", s1_var_ratio, s2_var_ratio);
  Serial.println(F("--------------------------------------------------------------------------------"));

  // Localization Section (Honest Uncertainty Enforcement)
  if (loc_valid) {
    float loc_s1_meters = (PIPE_LENGTH_METERS + (ACOUSTIC_SPEED_MPS * tdoa_sec)) / 2.0f;
    Serial.printf("LOCALIZATION RESULT:    ESTIMATED DISTANCE = %.2f meters from Sensor 1 (Cross-Corr Peak R=%.2f)\n", 
                  loc_s1_meters, peak_corr);
  } else {
    Serial.printf("LOCALIZATION RESULT:    LOCATION NOT VERIFIED\n");
    Serial.printf("LOCALIZATION REASON:    Peak Cross-Correlation R=%.2f (Min required: %.2f) or sampling interval (1ms) insufficient for 2m acoustic delay.\n",
                  peak_corr, MIN_CORRELATION_PEAK);
  }
  Serial.printf("TIMING PERFORMANCE:     Sample Rate: %d Hz | Timing Overruns: %lu\n", SAMPLE_RATE_HZ, g_timing_overrun_count);
  Serial.println(F("================================================================================\n"));
}

// ============================================================================
// MATHEMATICAL & STATISTICAL HELPERS
// ============================================================================

float calculateMedian(float* array, uint16_t size) {
  if (size == 0) return 0.0f;
  // Simple insertion sort on a copy array
  float temp[60];
  uint16_t n = min(size, (uint16_t)60);
  for (uint16_t i = 0; i < n; i++) temp[i] = array[i];

  for (uint16_t i = 1; i < n; i++) {
    float key = temp[i];
    int j = i - 1;
    while (j >= 0 && temp[j] > key) {
      temp[j + 1] = temp[j];
      j--;
    }
    temp[j + 1] = key;
  }

  if (n % 2 == 1) {
    return temp[n / 2];
  } else {
    return (temp[(n / 2) - 1] + temp[n / 2]) / 2.0f;
  }
}

float calculateMAD(float* array, uint16_t size, float median) {
  if (size == 0) return 0.0f;
  float abs_diffs[60];
  uint16_t n = min(size, (uint16_t)60);
  for (uint16_t i = 0; i < n; i++) {
    abs_diffs[i] = fabsf(array[i] - median);
  }
  return calculateMedian(abs_diffs, n);
}
