/*
 * ESP32 Pipeline Leakage Detection System - AquaGuard AI
 * ========================================================
 * Restored Pre-GPS DSP Vibration-Processing Architecture with GPS Integration
 * 
 * Microcontroller: ESP32 Dev Module (3.3V Logic)
 * Sensor 1 Input:  GPIO 34 (ADC1_CH6)
 * Sensor 2 Input:  GPIO 35 (ADC1_CH7)
 * GPS Module:      NEO-6M on Serial2 (RX: GPIO 16, TX: GPIO 17 @ 9600 baud)
 * Serial Port:     115200 Baud (CSV Machine Protocol & Human Diagnostic)
 *
 * Signal Acquisition & DSP Design:
 * - 2,000 sample pairs captured per 1-second observation at 400 us intervals (~2500 Hz nominal).
 * - Discard initial 30 points to allow HP filter initialization.
 * - Digital High-Pass DC Blocker: y = 0.98 * (y + raw - prevRaw).
 * - RMS = sqrt( sum(y^2) / count ) on HP-filtered AC vibration.
 * - Difference RMS = sqrt( sum((y - prevY)^2) / count ).
 * - Peak-to-Peak (P2P) = raw_max - raw_min over 2,000 samples.
 * - ADC Clipping check (raw <= 4 || raw >= 4091).
 * - 60-second robust baseline calibration using median, MAD, and robust sigmas.
 * - Continuous telemetry streaming during calibration fault states (never freezes website).
 * - GPS parsing isolated to the non-acquisition interval (~0.2s) to prevent sampling jitter.
 * - 15-field CSV telemetry protocol output every second for full website compatibility.
 */

#include <Arduino.h>
#include <math.h>

// ============================================================================
// HARDWARE PINS & PHYSICAL CONSTANTS
// ============================================================================

constexpr int PIN_S1 = 34;
constexpr int PIN_S2 = 35;
constexpr float SENSOR_SPACING_M = 2.0f;

// GPS UART2 Configuration
constexpr uint8_t PIN_GPS_RX = 16;
constexpr uint8_t PIN_GPS_TX = 17;
constexpr uint32_t GPS_BAUD = 9600;

// YF-S201 Flow Sensor Configuration (Inlet & Outlet Pulse Inputs)
constexpr int PIN_FLOW_IN = 25;   // Inlet YF-S201 pulse signal (GPIO 25)
constexpr int PIN_FLOW_OUT = 26;  // Outlet YF-S201 pulse signal (GPIO 26)
constexpr float FLOW_K_IN = 450.0f;   // Nominal 450 pulses/liter (independently calibratable)
constexpr float FLOW_K_OUT = 450.0f;  // Nominal 450 pulses/liter (independently calibratable)
constexpr uint32_t FLOW_WINDOW_MS = 5000; // 5-second measurement window
constexpr float FLOW_LEAK_THRESHOLD_LPM = 0.10f; // Configurable flow imbalance threshold (L/min)
constexpr float FLOW_MIN_INLET_LPM = 0.50f;      // Minimum inlet flow to assess leakage
constexpr uint8_t FLOW_CONFIRM_WINDOWS = 3;      // 3 consecutive windows to confirm leak (~15s)
constexpr uint8_t FLOW_RECOVERY_WINDOWS = 3;     // 3 consecutive normal windows to recover

// Sampling Window Constants (~0.7 seconds of RMS sampling, 1750 points)
constexpr int POINTS = 1750;
constexpr uint32_t SAMPLE_INTERVAL_US = 400; // 2500 Hz per channel
constexpr int SECONDS_PER_REPORT = 60;
constexpr int DISCARD_POINTS = 30; // Allow HP filter to settle

// High-Speed Synchronized Sampling & TDOA Constants (10 kHz per channel)
constexpr uint32_t TDOA_SAMPLE_INTERVAL_US = 100; // 100 us = 10 kHz nominal per channel
constexpr int TDOA_BURST_SAMPLES = 500;           // 500 sample pairs = 50 ms window
constexpr float PIPE_PROPAGATION_VELOCITY_MPS = 1250.0f; // NOMINAL / UNCALIBRATED wave speed in steel pipe
constexpr float ADC_INTERCHANNEL_SKEW_ESTIMATE_US = 10.0f; // Nominal estimate of sequential ADC1 conversion delay (subject to electrical calibration)
constexpr int TDOA_MAX_SEARCH_LAG = 20;           // Lags -20 to +20 (-2000 us to +2000 us)
constexpr float MIN_TDOA_CORRELATION = 0.65f;


// Baseline Limits (Median & MAD Multipliers)
constexpr float RMS_RATIO_LIMIT = 1.50f;
constexpr float DIFF_RATIO_LIMIT = 1.50f;
constexpr float ROBUST_SIGMAS = 4.0f;
constexpr float MIN_RMS_RISE = 6.0f;   // ADC counts
constexpr float MIN_DIFF_RISE = 4.0f;  // ADC counts

// Detection Parameters
constexpr int MIN_VALID_SECONDS = 50;
constexpr int SUSTAINED_SECONDS = 42;  // >=70% of 60 seconds
constexpr int MIN_CONTINUOUS_SECONDS = 12;
constexpr int INTERMITTENT_SECONDS = 12;

// Cross-Correlation Lag
constexpr int MAX_LAG_SAMPLES = 8;
constexpr float MIN_CORRELATION = 0.65f;
constexpr int MIN_DIRECTION_VOTES = 15;

// ============================================================================
// DATA STRUCTURES
// ============================================================================

enum SystemState {
  STATE_CALIBRATING,
  STATE_MONITORING_NORMAL,
  STATE_SUSPECTED_ANOMALY,
  STATE_CONFIRMED_LEAK_ALARM,
  STATE_SENSOR_FAULT
};

struct TDOAResult {
  float delta_t_us = 0.0f;
  float peak_corr = 0.0f;
  float psr = 0.0f;
  float dist_s1_m = 0.0f;
  float dist_s2_m = 0.0f;
  float confidence_pct = 0.0f;
  float uncertainty_m = 0.15f;
  int sample_rate_hz = 10000;
  bool loc_valid = false;
  char status[40] = "LOCATION_UNAVAILABLE";
  int16_t s1_wave[50];
  int16_t s2_wave[50];
};

struct FlowResult {
  uint32_t esp32_ms = 0;
  uint32_t interval_ms = 5000;
  uint32_t in_pulses = 0;
  uint32_t out_pulses = 0;
  float flow_in_lpm = 0.0f;
  float flow_out_lpm = 0.0f;
  float flow_diff_lpm = 0.0f;
  uint8_t leak_progress = 0; // 0..3 windows
  bool leak_confirmed = false;
  char status[32] = "NO_FLOW";
};

struct Observation {
  float rms1 = 0;
  float rms2 = 0;
  float diff1 = 0;
  float diff2 = 0;
  float p2p1 = 0;
  float p2p2 = 0;
  int minRaw1 = 4095, maxRaw1 = 0;
  int minRaw2 = 4095, maxRaw2 = 0;
  float meanRaw1 = 2048.0f;
  float meanRaw2 = 2048.0f;
  int s1_clip_count = 0;
  int s2_clip_count = 0;
  float s1_clip_pct = 0.0f;
  float s2_clip_pct = 0.0f;
  float corr = 0;
  int lag = 0;
  bool valid = false;
  bool high1 = false;
  bool high2 = false;
  int late_count = 0;
  int clipped_count = 0;
  float effective_hz = 2500.0f;
};

struct Baseline {
  float rms1 = 0, rms2 = 0, diff1 = 0, diff2 = 0;
  float thresholdRms1 = 0, thresholdRms2 = 0;
  float thresholdDiff1 = 0, thresholdDiff2 = 0;
  bool ready = false;
};


// ============================================================================
// GLOBAL STATE & BUFFERS
// ============================================================================

float signal1[POINTS];
float signal2[POINTS];

Observation minuteData[SECONDS_PER_REPORT];
Baseline base;

SystemState g_system_state = STATE_CALIBRATING;
unsigned long g_minute_number = 0;
unsigned long g_total_seconds_elapsed = 0;

bool g_csv_mode = true;
bool g_verbose_mode = true;
bool g_gps_enabled = true;
int g_persistence_req = SUSTAINED_SECONDS;

// GPS State
float g_gps_lat = 0.0f;
float g_gps_lon = 0.0f;
uint8_t g_gps_sats = 0;
float g_gps_hdop = 99.99f;
bool g_gps_has_fix = false;
uint32_t g_last_gps_fix_ms = 0;
char g_nmea_line_buf[128];
uint8_t g_nmea_buf_idx = 0;

Observation g_last_obs;

// ============================================================================
// FLOW PULSE COUNTERS, CRITICAL MUX & TDOA CANDIDATE RING BUFFER
// ============================================================================
volatile uint32_t g_inlet_pulses = 0;
volatile uint32_t g_outlet_pulses = 0;
portMUX_TYPE g_flow_mux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR flowInletISR() {
  portENTER_CRITICAL_ISR(&g_flow_mux);
  g_inlet_pulses++;
  portEXIT_CRITICAL_ISR(&g_flow_mux);
}

void IRAM_ATTR flowOutletISR() {
  portENTER_CRITICAL_ISR(&g_flow_mux);
  g_outlet_pulses++;
  portEXIT_CRITICAL_ISR(&g_flow_mux);
}

FlowResult g_latest_flow;
uint32_t g_last_flow_calc_ms = 0;
uint8_t g_flow_leak_count = 0;
uint8_t g_flow_normal_count = 0;
bool g_flow_leak_alarm = false;
uint32_t g_flow_imbalance_onset_ms = 0;

// Candidate Vibration TDOA Buffer (30 elements = 30 seconds of history)
constexpr int TDOA_HISTORY_SIZE = 30;
TDOAResult g_tdoa_history[TDOA_HISTORY_SIZE];
uint32_t g_tdoa_history_ts[TDOA_HISTORY_SIZE];
int g_tdoa_history_idx = 0;
int g_tdoa_history_count = 0;

// Associated Candidate Acoustic Lock when leak confirmed
TDOAResult g_associated_tdoa_lock;
bool g_associated_tdoa_valid = false;

// ============================================================================
// STATIC BUFFERS IN BSS (Off-stack storage to prevent FreeRTOS loopTask stack canary panic)
// ============================================================================
static int16_t   s_tdoa_raw1[TDOA_BURST_SAMPLES];
static int16_t   s_tdoa_raw2[TDOA_BURST_SAMPLES];
static float     s_tdoa_filt1[TDOA_BURST_SAMPLES];
static float     s_tdoa_filt2[TDOA_BURST_SAMPLES];
static float     s_tdoa_r_vals[2 * TDOA_MAX_SEARCH_LAG + 1];
static TDOAResult s_tdoa_result;

// Reusable static analysis buffers (replaces 1KB+ stack arrays in calibrate, analyzeMinute, medianOf)
static float s_analysis_r1[SECONDS_PER_REPORT];
static float s_analysis_r2[SECONDS_PER_REPORT];
static float s_analysis_d1[SECONDS_PER_REPORT];
static float s_analysis_d2[SECONDS_PER_REPORT];
static bool  s_analysis_a1[SECONDS_PER_REPORT];
static bool  s_analysis_a2[SECONDS_PER_REPORT];
static float s_median_temp[SECONDS_PER_REPORT];
static float s_baseline_deviations[SECONDS_PER_REPORT];

// ============================================================================
// FUNCTION DECLARATIONS
// ============================================================================

void sortFloats(float *a, int n);
float medianOf(const float *values, int n);
float baselineLimit(const float *values, int n, float ratio, float minimumIncrease, float &center);
Observation captureObservation();
void estimateDirection(Observation &o);
const TDOAResult& captureHighSpeedTDOA();
void calibrate();
void analyzeMinute();
void readGPS();
void parseNMEASentence(char* line);
void printGPSTelemetry();
void printADCDiagnostics();
void printADCTelemetry(const Observation &o);
void handleSerialCommands();
void printHelp();
void printStatusReport();
void printFull60SecondReport(const char* state_str, int valid, int invalid,
                             float medR1, float medR2, float medD1, float medD2,
                             int count1, int count2, int simultaneous,
                             int strongCorr, int lead1, int lead2,
                             const char* reasoning);
void printMemoryDiagnostics(const char* tag);
void printProgressMarker(const char* stage, uint32_t elapsed_us = 0);
void evaluateFlowSensors();
void printFlowTelemetry(const FlowResult &f);
void printFlowDiagnostics();
void recordTDOAHistory(const TDOAResult &t);
void associateCandidateTDOALock();

// ============================================================================
// HELPER FUNCTIONS & RUNTIME DIAGNOSTICS
// ============================================================================

void printMemoryDiagnostics(const char* tag) {
  uint32_t freeHeap = ESP.getFreeHeap();
  uint32_t minHeap = ESP.getMinFreeHeap();
  UBaseType_t stackRemain = uxTaskGetStackHighWaterMark(NULL);
  Serial.printf("[MEM-CHECK @ %s] FreeHeap: %lu B | MinHeap: %lu B | StackHighWater: %u B\n",
                tag, (unsigned long)freeHeap, (unsigned long)minHeap, (unsigned int)stackRemain);
}

void printProgressMarker(const char* stage, uint32_t elapsed_us) {
  if (g_verbose_mode || g_total_seconds_elapsed <= 2) {
    if (elapsed_us > 0) {
      Serial.printf("[STAGE: %s] (%lu us)\n", stage, (unsigned long)elapsed_us);
    } else {
      Serial.printf("[STAGE: %s]\n", stage);
    }
  }
}

void sortFloats(float *a, int n) {
  for (int i = 1; i < n; ++i) {
    float v = a[i];
    int j = i - 1;
    while (j >= 0 && a[j] > v) {
      a[j + 1] = a[j];
      --j;
    }
    a[j + 1] = v;
  }
}

float medianOf(const float *values, int n) {
  if (n <= 0) return 0;
  int count = (n > SECONDS_PER_REPORT) ? SECONDS_PER_REPORT : n;
  for (int i = 0; i < count; ++i) s_median_temp[i] = values[i];
  sortFloats(s_median_temp, count);
  return (count % 2) ? s_median_temp[count / 2] : 0.5f * (s_median_temp[count / 2 - 1] + s_median_temp[count / 2]);
}

float baselineLimit(const float *values, int n,
                    float ratio, float minimumIncrease, float &center) {
  center = medianOf(values, n);
  int count = (n > SECONDS_PER_REPORT) ? SECONDS_PER_REPORT : n;
  for (int i = 0; i < count; ++i) s_baseline_deviations[i] = fabsf(values[i] - center);
  float robustSigma = 1.4826f * medianOf(s_baseline_deviations, count);
  float a = center * ratio;
  float b = center + ROBUST_SIGMAS * robustSigma;
  float c = center + minimumIncrease;
  return fmaxf(a, fmaxf(b, c));
}

int longestRun(bool *flags) {
  int best = 0, run = 0;
  for (int i = 0; i < SECONDS_PER_REPORT; ++i) {
    run = flags[i] ? run + 1 : 0;
    if (run > best) best = run;
  }
  return best;
}

// ============================================================================
// VIBRATION SIGNAL ACQUISITION & DIAGNOSTICS
// ============================================================================

Observation captureObservation() {
  Observation result;
  float prevRaw1 = 0, prevRaw2 = 0;
  float previousY1 = 0, previousY2 = 0;
  float y1 = 0, y2 = 0;
  double sum1 = 0, sum2 = 0, delta1 = 0, delta2 = 0;
  long sumRaw1 = 0, sumRaw2 = 0;
  int used = 0, deltasUsed = 0;
  int late = 0, clipped = 0;
  int s1_clips = 0, s2_clips = 0;
  int minRaw1 = 4095, maxRaw1 = 0;
  int minRaw2 = 4095, maxRaw2 = 0;

  uint32_t start_us = micros();
  uint32_t next = start_us;

  for (int i = 0; i < POINTS; ++i) {
    while ((int32_t)(micros() - next) < 0) { }
    uint32_t now = micros();
    if ((int32_t)(now - next) > (int32_t)(SAMPLE_INTERVAL_US / 2)) late++;
    next += SAMPLE_INTERVAL_US;

    int raw1 = analogRead(PIN_S1);
    int raw2 = analogRead(PIN_S2);

    sumRaw1 += raw1;
    sumRaw2 += raw2;

    if (raw1 < minRaw1) minRaw1 = raw1;
    if (raw1 > maxRaw1) maxRaw1 = raw1;
    if (raw2 < minRaw2) minRaw2 = raw2;
    if (raw2 > maxRaw2) maxRaw2 = raw2;

    bool c1 = (raw1 <= 4 || raw1 >= 4091);
    bool c2 = (raw2 <= 4 || raw2 >= 4091);
    if (c1) s1_clips++;
    if (c2) s2_clips++;
    if (c1 || c2) clipped++;

    if (i == 0) {
      prevRaw1 = raw1;
      prevRaw2 = raw2;
    }

    // High-pass filter removes the DC offset sample-by-sample
    y1 = 0.98f * (y1 + raw1 - prevRaw1);
    y2 = 0.98f * (y2 + raw2 - prevRaw2);
    prevRaw1 = raw1;
    prevRaw2 = raw2;

    signal1[i] = y1;
    signal2[i] = y2;

    if (i >= DISCARD_POINTS) {
      sum1 += (double)y1 * y1;
      sum2 += (double)y2 * y2;
      used++;
      if (i > DISCARD_POINTS) {
        float d1 = y1 - previousY1;
        float d2 = y2 - previousY2;
        delta1 += (double)d1 * d1;
        delta2 += (double)d2 * d2;
        deltasUsed++;
      }
      previousY1 = y1;
      previousY2 = y2;
    }
  }

  uint32_t duration_us = micros() - start_us;

  result.rms1 = (used > 0) ? sqrt(sum1 / used) : 0;
  result.rms2 = (used > 0) ? sqrt(sum2 / used) : 0;
  result.diff1 = (deltasUsed > 0) ? sqrt(delta1 / deltasUsed) : 0;
  result.diff2 = (deltasUsed > 0) ? sqrt(delta2 / deltasUsed) : 0;
  result.p2p1 = (float)(maxRaw1 - minRaw1);
  result.p2p2 = (float)(maxRaw2 - minRaw2);
  result.minRaw1 = minRaw1;
  result.maxRaw1 = maxRaw1;
  result.minRaw2 = minRaw2;
  result.maxRaw2 = maxRaw2;
  result.meanRaw1 = (float)sumRaw1 / (float)POINTS;
  result.meanRaw2 = (float)sumRaw2 / (float)POINTS;
  result.s1_clip_count = s1_clips;
  result.s2_clip_count = s2_clips;
  result.s1_clip_pct = ((float)s1_clips / (float)POINTS) * 100.0f;
  result.s2_clip_pct = ((float)s2_clips / (float)POINTS) * 100.0f;

  result.late_count = late;
  result.clipped_count = clipped;
  result.effective_hz = (duration_us > 0) ? (2000.0f / (duration_us / 1000000.0f)) : 2500.0f;

  // Rejection check: >5% clipped (100 samples) or >2% late (40 samples)
  result.valid = (late <= POINTS / 50) && (clipped <= POINTS / 20);
  return result;
}

void estimateDirection(Observation &o) {
  float best = 0;
  int bestLag = 0;
  for (int lag = -MAX_LAG_SAMPLES; lag <= MAX_LAG_SAMPLES; ++lag) {
    int start = lag < 0 ? -lag : 0;
    int end = lag > 0 ? POINTS - lag : POINTS;
    if (start < DISCARD_POINTS) start = DISCARD_POINTS;
    double dot = 0, e1 = 0, e2 = 0;
    for (int i = start; i < end; ++i) {
      float a = signal1[i];
      float b = signal2[i + lag];
      dot += (double)a * b;
      e1 += (double)a * a;
      e2 += (double)b * b;
    }
    float corr = (e1 > 1e-8 && e2 > 1e-8) ? fabsf(dot / sqrt(e1 * e2)) : 0;
    if (corr > best) {
      best = corr;
      bestLag = lag;
    }
  }
  o.corr = best;
  o.lag = bestLag;
}

// ============================================================================
// HIGH-SPEED SYNCHRONIZED ACQUISITION & TDOA LOCALIZATION
// ============================================================================

const TDOAResult& captureHighSpeedTDOA() {
  TDOAResult &res = s_tdoa_result;
  memset(&res, 0, sizeof(TDOAResult));
  res.sample_rate_hz = 10000;
  res.uncertainty_m = 0.15f;
  res.loc_valid = false;
  strncpy(res.status, "LOCATION_UNAVAILABLE", sizeof(res.status) - 1);

  printProgressMarker("TDOA_ACQ_START");
  uint32_t start_us = micros();
  uint32_t next_us = start_us;
  int clip1 = 0, clip2 = 0;
  long sum1 = 0, sum2 = 0;

  for (int i = 0; i < TDOA_BURST_SAMPLES; ++i) {
    while ((int32_t)(micros() - next_us) < 0) { }
    next_us += TDOA_SAMPLE_INTERVAL_US;

    int s1 = analogRead(PIN_S1);
    int s2 = analogRead(PIN_S2);

    s_tdoa_raw1[i] = (int16_t)s1;
    s_tdoa_raw2[i] = (int16_t)s2;

    if (s1 <= 4 || s1 >= 4091) clip1++;
    if (s2 <= 4 || s2 >= 4091) clip2++;

    sum1 += s1;
    sum2 += s2;
  }

  uint32_t elapsed_us = micros() - start_us;
  printProgressMarker("TDOA_ACQ_DONE", elapsed_us);
  if (elapsed_us > 0) {
    res.sample_rate_hz = (int)((float)TDOA_BURST_SAMPLES / ((float)elapsed_us / 1000000.0f) + 0.5f);
  }

  // Populate 50 downsampled snapshot points for web visualization
  for (int j = 0; j < 50; ++j) {
    int idx = j * 10;
    res.s1_wave[j] = s_tdoa_raw1[idx] - (int16_t)(sum1 / TDOA_BURST_SAMPLES);
    res.s2_wave[j] = s_tdoa_raw2[idx] - (int16_t)(sum2 / TDOA_BURST_SAMPLES);
  }

  // Quality check: Reject if excessive ADC clipping (>5% = 25 samples)
  if (clip1 > 25 || clip2 > 25) {
    res.loc_valid = false;
    strncpy(res.status, "ADC_CLIPPING_FAULT", sizeof(res.status) - 1);
    return res;
  }

  printProgressMarker("TDOA_FILTER_START");
  // Zero-mean centering and digital high-pass filtering (300 Hz cutoff at 10 kHz fs: alpha = 0.8273)
  float mean1 = (float)sum1 / TDOA_BURST_SAMPLES;
  float mean2 = (float)sum2 / TDOA_BURST_SAMPLES;

  float y1 = 0, y2 = 0;
  double var1 = 0, var2 = 0;
  // Exactly 300 Hz (-3 dB) cutoff for y[n] = alpha*(y[n-1] + x[n] - x[n-1]) at fs=10 kHz:
  // Derived from cos(w_c) = 2*alpha / (1 + alpha^2) => alpha = (1 - sin(w_c)) / cos(w_c) = 0.8273f
  constexpr float ALPHA_HP_10KHZ = 0.8273f;

  for (int i = 0; i < TDOA_BURST_SAMPLES; ++i) {
    float x1 = (float)s_tdoa_raw1[i] - mean1;
    float x2 = (float)s_tdoa_raw2[i] - mean2;

    y1 = ALPHA_HP_10KHZ * (y1 + x1 - (i > 0 ? (float)s_tdoa_raw1[i-1] - mean1 : x1));
    y2 = ALPHA_HP_10KHZ * (y2 + x2 - (i > 0 ? (float)s_tdoa_raw2[i-1] - mean2 : x2));

    s_tdoa_filt1[i] = y1;
    s_tdoa_filt2[i] = y2;

    var1 += (double)y1 * y1;
    var2 += (double)y2 * y2;
  }

  var1 /= TDOA_BURST_SAMPLES;
  var2 /= TDOA_BURST_SAMPLES;
  printProgressMarker("TDOA_FILTER_DONE");

  // Floor check: If variance < 4.0 ADC counts^2, signal is silent background noise
  if (var1 < 4.0 || var2 < 4.0) {
    res.loc_valid = false;
    strncpy(res.status, "LOW_SIGNAL_POWER", sizeof(res.status) - 1);
    return res;
  }

  printProgressMarker("TDOA_CORR_START");
  // Normalized Cross-Correlation (NCC) across lags [-20, +20]
  float best_r = -1.0f;
  int best_lag = 0;

  for (int lag = -TDOA_MAX_SEARCH_LAG; lag <= TDOA_MAX_SEARCH_LAG; ++lag) {
    int start = lag < 0 ? -lag : 0;
    int end = lag > 0 ? TDOA_BURST_SAMPLES - lag : TDOA_BURST_SAMPLES;
    double dot = 0, e1 = 0, e2 = 0;

    for (int i = start; i < end; ++i) {
      float a = s_tdoa_filt1[i];
      float b = s_tdoa_filt2[i + lag];
      dot += (double)a * b;
      e1 += (double)a * a;
      e2 += (double)b * b;
    }

    float norm = (e1 > 1e-8 && e2 > 1e-8) ? (float)(dot / sqrt(e1 * e2)) : 0.0f;
    int arr_idx = lag + TDOA_MAX_SEARCH_LAG;
    s_tdoa_r_vals[arr_idx] = norm;

    if (norm > best_r) {
      best_r = norm;
      best_lag = lag;
    }
  }

  res.peak_corr = best_r;

  // Compute Peak-to-Sidelobe Ratio (PSR)
  double sidelobe_sum = 0, sidelobe_sq = 0;
  int sidelobe_count = 0;
  for (int lag = -TDOA_MAX_SEARCH_LAG; lag <= TDOA_MAX_SEARCH_LAG; ++lag) {
    if (abs(lag - best_lag) > 2) {
      float r = s_tdoa_r_vals[lag + TDOA_MAX_SEARCH_LAG];
      sidelobe_sum += r;
      sidelobe_sq += (double)r * r;
      sidelobe_count++;
    }
  }

  if (sidelobe_count > 0) {
    double side_mean = sidelobe_sum / sidelobe_count;
    double side_var = (sidelobe_sq / sidelobe_count) - (side_mean * side_mean);
    double side_std = (side_var > 1e-6) ? sqrt(side_var) : 0.05;
    res.psr = (float)((best_r - side_mean) / side_std);
  } else {
    res.psr = 1.0f;
  }

  // Sub-sample parabolic interpolation around peak
  float sub_sample_delta = 0.0f;
  int best_idx = best_lag + TDOA_MAX_SEARCH_LAG;
  if (best_idx > 0 && best_idx < 2 * TDOA_MAX_SEARCH_LAG) {
    float y_left = s_tdoa_r_vals[best_idx - 1];
    float y_mid = s_tdoa_r_vals[best_idx];
    float y_right = s_tdoa_r_vals[best_idx + 1];
    float denom = 2.0f * (2.0f * y_mid - y_left - y_right);
    if (fabsf(denom) > 1e-5f) {
      sub_sample_delta = (y_right - y_left) / denom;
      if (sub_sample_delta > 0.5f) sub_sample_delta = 0.5f;
      if (sub_sample_delta < -0.5f) sub_sample_delta = -0.5f;
    }
  }

  printProgressMarker("TDOA_CORR_DONE");

  // Refined time delay in microseconds:
  // With Sensor 2 sampled +10 us LATER than Sensor 1, an event arriving +10 us later
  // at Sensor 2 produces lag = 0. To recover true physical dt = t2 - t1, we ADD tau_skew.
  float refined_lag = (float)best_lag + sub_sample_delta;
  res.delta_t_us = (refined_lag * (float)TDOA_SAMPLE_INTERVAL_US) + ADC_INTERCHANNEL_SKEW_ESTIMATE_US;

  // Calculate distance from Sensor 1: d1 = (L - v * dt) / 2
  float dt_sec = res.delta_t_us / 1000000.0f;
  float d1 = (SENSOR_SPACING_M - (PIPE_PROPAGATION_VELOCITY_MPS * dt_sec)) / 2.0f;
  float d2 = SENSOR_SPACING_M - d1;

  res.dist_s1_m = d1;
  res.dist_s2_m = d2;

  // Physical plausibility & quality criteria
  bool corr_ok = (best_r >= MIN_TDOA_CORRELATION);
  bool psr_ok = (res.psr >= 2.0f);
  bool range_ok = (d1 >= -0.15f && d1 <= (SENSOR_SPACING_M + 0.15f));

  if (corr_ok && psr_ok && range_ok) {
    res.loc_valid = true;
    res.dist_s1_m = fmaxf(0.0f, fminf(SENSOR_SPACING_M, d1));
    res.dist_s2_m = fmaxf(0.0f, fminf(SENSOR_SPACING_M, d2));
    res.confidence_pct = roundf(best_r * 100.0f);
    // Honest uncertainty bounds: uncalibrated velocity & steel wave dispersion preclude false centimeter claims
    res.uncertainty_m = fmaxf(0.15f, (1.0f - best_r) * 0.6f);
    strncpy(res.status, "LOCALIZATION_ACQUIRED", sizeof(res.status) - 1);
  } else {
    res.loc_valid = false;
    strncpy(res.status, "INSUFFICIENT_CORRELATION", sizeof(res.status) - 1);
  }

  return res;
}


void printTDOATelemetry(const TDOAResult &t) {
  Serial.printf("TDOA,%lu,%.1f,%.3f,%.2f,%.2f,%.2f,%d,%.1f,%d,%s\n",
                millis(),
                t.delta_t_us,
                t.peak_corr,
                t.psr,
                t.dist_s1_m,
                t.dist_s2_m,
                t.sample_rate_hz,
                PIPE_PROPAGATION_VELOCITY_MPS,
                t.loc_valid ? 1 : 0,
                t.status);

  // Output compact waveform snapshot
  Serial.print(F("WAVE,"));
  for (int i = 0; i < 50; ++i) {
    Serial.print(t.s1_wave[i]);
    if (i < 49) Serial.print(F(","));
  }
  Serial.print(F(";"));
  for (int i = 0; i < 50; ++i) {
    Serial.print(t.s2_wave[i]);
    if (i < 49) Serial.print(F(","));
  }
  Serial.println();
}

void printADCTelemetry(const Observation &o) {
  // Format: ADC,millis,min1,max1,mean1,clips1,pct1,min2,max2,mean2,clips2,pct2
  Serial.printf("ADC,%lu,%d,%d,%.1f,%d,%.2f,%d,%d,%.1f,%d,%.2f\n",
                millis(),
                o.minRaw1, o.maxRaw1, o.meanRaw1, o.s1_clip_count, o.s1_clip_pct,
                o.minRaw2, o.maxRaw2, o.meanRaw2, o.s2_clip_count, o.s2_clip_pct);
}

// ============================================================================
// DUAL YF-S201 FLOW SENSOR EVALUATION & CANDIDATE ACOUSTIC LOCK ASSOCIATION
// ============================================================================

void recordTDOAHistory(const TDOAResult &t) {
  g_tdoa_history[g_tdoa_history_idx] = t;
  g_tdoa_history_ts[g_tdoa_history_idx] = millis();
  g_tdoa_history_idx = (g_tdoa_history_idx + 1) % TDOA_HISTORY_SIZE;
  if (g_tdoa_history_count < TDOA_HISTORY_SIZE) {
    g_tdoa_history_count++;
  }
}

void associateCandidateTDOALock() {
  // Search bounded TDOA history buffer (last 30 seconds)
  // Associate candidate with highest peak_corr that occurred around or since the onset of flow imbalance.
  // Prevents normal quiescent pump vibration prior to leak onset from being selected as a leak event.
  float best_corr = -1.0f;
  int best_idx = -1;

  for (int i = 0; i < g_tdoa_history_count; ++i) {
    const TDOAResult &cand = g_tdoa_history[i];
    uint32_t ts = g_tdoa_history_ts[i];

    if (cand.loc_valid && cand.peak_corr >= MIN_TDOA_CORRELATION) {
      // Must be within candidate window starting from onset of flow imbalance (-2s tolerance for burst alignment)
      if (g_flow_imbalance_onset_ms == 0 || (ts + 2000 >= g_flow_imbalance_onset_ms)) {
        if (cand.peak_corr > best_corr) {
          best_corr = cand.peak_corr;
          best_idx = i;
        }
      }
    }
  }

  if (best_idx >= 0) {
    g_associated_tdoa_lock = g_tdoa_history[best_idx];
    g_associated_tdoa_valid = true;
  } else {
    g_associated_tdoa_valid = false;
  }
}

void printFlowTelemetry(const FlowResult &f) {
  // Format: FLOW,millis,interval_ms,in_pulses,out_pulses,flow_in_lpm,flow_out_lpm,diff_lpm,progress,confirmed,status
  Serial.printf("FLOW,%lu,%lu,%lu,%lu,%.3f,%.3f,%.3f,%d,%d,%s\n",
                (unsigned long)f.esp32_ms,
                (unsigned long)f.interval_ms,
                (unsigned long)f.in_pulses,
                (unsigned long)f.out_pulses,
                f.flow_in_lpm,
                f.flow_out_lpm,
                f.flow_diff_lpm,
                f.leak_progress,
                f.leak_confirmed ? 1 : 0,
                f.status);
}

void evaluateFlowSensors() {
  uint32_t now = millis();
  if (g_last_flow_calc_ms == 0) {
    g_last_flow_calc_ms = now;
    return;
  }
  uint32_t elapsed = now - g_last_flow_calc_ms;
  if (elapsed < FLOW_WINDOW_MS) {
    return;
  }
  g_last_flow_calc_ms = now;

  portENTER_CRITICAL(&g_flow_mux);
  uint32_t pIn = g_inlet_pulses;
  uint32_t pOut = g_outlet_pulses;
  g_inlet_pulses = 0;
  g_outlet_pulses = 0;
  portEXIT_CRITICAL(&g_flow_mux);

  // Exact pulse-to-flow conversion:
  // flow_lpm = (pulses * 60000.0) / (calibration_pulses_per_liter * actual_interval_ms)
  float flowIn = (pIn * 60000.0f) / (FLOW_K_IN * (float)elapsed);
  float flowOut = (pOut * 60000.0f) / (FLOW_K_OUT * (float)elapsed);
  float difference = flowIn - flowOut;

  g_latest_flow.esp32_ms = now;
  g_latest_flow.interval_ms = elapsed;
  g_latest_flow.in_pulses = pIn;
  g_latest_flow.out_pulses = pOut;
  g_latest_flow.flow_in_lpm = flowIn;
  g_latest_flow.flow_out_lpm = flowOut;
  g_latest_flow.flow_diff_lpm = difference;

  // Rule: Do not assess leak when inlet flow is low or zero
  if (flowIn < FLOW_MIN_INLET_LPM) {
    g_flow_leak_count = 0;
    g_flow_normal_count = 0;
    g_flow_leak_alarm = false;
    g_flow_imbalance_onset_ms = 0;
    g_latest_flow.leak_progress = 0;
    g_latest_flow.leak_confirmed = false;
    strncpy(g_latest_flow.status, "LOW_OR_NO_FLOW", sizeof(g_latest_flow.status) - 1);
    printFlowTelemetry(g_latest_flow);
    return;
  }

  // Leak threshold evaluation with 3-window confirmation & 3-window recovery hysteresis
  if (difference >= FLOW_LEAK_THRESHOLD_LPM) {
    if (g_flow_leak_count == 0) {
      g_flow_imbalance_onset_ms = now;
    }

    if (g_flow_leak_count < FLOW_CONFIRM_WINDOWS) {
      g_flow_leak_count++;
    }
    g_flow_normal_count = 0;

    if (g_flow_leak_count >= FLOW_CONFIRM_WINDOWS) {
      g_flow_leak_alarm = true;
      strncpy(g_latest_flow.status, "LEAK_CONFIRMED", sizeof(g_latest_flow.status) - 1);
      // Associate with relevant valid candidate acoustic lock from imbalance onset
      associateCandidateTDOALock();
    } else {
      strncpy(g_latest_flow.status, "VERIFYING_FLOW", sizeof(g_latest_flow.status) - 1);
    }
  } else {
    g_flow_leak_count = 0;
    if (g_flow_normal_count < FLOW_RECOVERY_WINDOWS) {
      g_flow_normal_count++;
    }
    if (g_flow_normal_count >= FLOW_RECOVERY_WINDOWS) {
      g_flow_leak_alarm = false;
      g_associated_tdoa_valid = false;
      g_flow_imbalance_onset_ms = 0;
    }
    strncpy(g_latest_flow.status, g_flow_leak_alarm ? "LEAK_CONFIRMED" : "NO_LEAK", sizeof(g_latest_flow.status) - 1);
  }

  g_latest_flow.leak_progress = g_flow_leak_count;
  g_latest_flow.leak_confirmed = g_flow_leak_alarm;

  printFlowTelemetry(g_latest_flow);
}

void printFlowDiagnostics() {
  Serial.println(F("\n================ FLOW SENSOR HARDWARE DIAGNOSTIC ================"));
  Serial.printf("Inlet Pin: GPIO %d | Outlet Pin: GPIO %d | K-factor: %.1f / %.1f P/L\n",
                PIN_FLOW_IN, PIN_FLOW_OUT, FLOW_K_IN, FLOW_K_OUT);
  Serial.printf("Inlet: %lu pulses (%.3f L/min) | Outlet: %lu pulses (%.3f L/min)\n",
                (unsigned long)g_latest_flow.in_pulses, g_latest_flow.flow_in_lpm,
                (unsigned long)g_latest_flow.out_pulses, g_latest_flow.flow_out_lpm);
  Serial.printf("Differential: %.3f L/min | Threshold: %.2f L/min | Min Inlet: %.2f L/min\n",
                g_latest_flow.flow_diff_lpm, FLOW_LEAK_THRESHOLD_LPM, FLOW_MIN_INLET_LPM);
  Serial.printf("Confirmation Progress: %d/%d windows | Leak Alarm: %s | Status: %s\n",
                g_latest_flow.leak_progress, FLOW_CONFIRM_WINDOWS,
                g_latest_flow.leak_confirmed ? "CONFIRMED" : "NORMAL", g_latest_flow.status);
  if (g_associated_tdoa_valid) {
    Serial.printf("Associated Acoustic Lock: d1=%.2fm, d2=%.2fm, dt=%.1fus, Peak R=%.3f\n",
                  g_associated_tdoa_lock.dist_s1_m, g_associated_tdoa_lock.dist_s2_m,
                  g_associated_tdoa_lock.delta_t_us, g_associated_tdoa_lock.peak_corr);
  } else {
    Serial.println(F("Associated Acoustic Lock: NONE / WAITING FOR CONFIRMATION"));
  }
  Serial.println(F("=================================================================\n"));
}


// ============================================================================
// BASELINE CALIBRATION & MONITORING
// ============================================================================

void calibrate() {
  base.ready = false;
  g_system_state = STATE_CALIBRATING;
  printProgressMarker("CALIBRATION_START");
  printMemoryDiagnostics("CALIB_START");

  Serial.println(F("\n================================================="));
  Serial.println(F("60-SECOND BASELINE CALIBRATION: PUMP ON, NO LEAK"));
  Serial.println(F("Ensure pipeline is operating normally without tap/leak."));
  Serial.println(F("================================================="));

  int s1_clip_secs = 0;
  int s2_clip_secs = 0;
  int late_secs = 0;

  for (int sec = 0; sec < SECONDS_PER_REPORT; ++sec) {
    uint32_t startMs = millis();
    if (sec == 0) printProgressMarker("RMS_CAPTURE_START");
    uint32_t t_rms_start = micros();
    Observation o = captureObservation();
    uint32_t t_rms_dur = micros() - t_rms_start;
    if (sec == 0) printProgressMarker("RMS_CAPTURE_DONE", t_rms_dur);

    const TDOAResult& tdoa = captureHighSpeedTDOA();
    minuteData[sec] = o;
    g_last_obs = o;
    g_total_seconds_elapsed++;

    if (o.s1_clip_count > 100) s1_clip_secs++;
    if (o.s2_clip_count > 100) s2_clip_secs++;
    if (o.late_count > 40) late_secs++;

    if (g_gps_enabled) readGPS();
    handleSerialCommands();

    if (g_csv_mode) {
      Serial.printf("CSV,%lu,%lu,%.2f,%.1f,%.2f,%.2f,%.2f,%.1f,%.2f,%.2f,0,0,%d,CALIBRATING\n",
                    millis(), g_total_seconds_elapsed,
                    o.rms1, o.p2p1, o.rms1 * o.rms1, o.diff1,
                    o.rms2, o.p2p2, o.rms2 * o.rms2, o.diff2,
                    (!o.valid || o.clipped_count > 0) ? 1 : 0);
      printTDOATelemetry(tdoa);
      printADCTelemetry(o);
      if (g_gps_enabled) printGPSTelemetry();
      recordTDOAHistory(tdoa);
      evaluateFlowSensors();
    } else if (g_verbose_mode) {
      Serial.printf("[CALIBRATING %d/60] S1 RMS: %.2f P2P: %.1f | S2 RMS: %.2f P2P: %.1f [%s]\n",
                    sec + 1, o.rms1, o.p2p1, o.rms2, o.p2p2, o.valid ? "OK" : "CLIPPED/INVALID");
    }

    if (sec == 0) {
      printMemoryDiagnostics("CALIB_SEC_0_DONE");
    }

    uint32_t elapsedMs = millis() - startMs;
    if (elapsedMs < 1000) {
      delay(1000 - elapsedMs);
    }
  }

  int n = 0;
  for (int i = 0; i < SECONDS_PER_REPORT; ++i) {
    if (!minuteData[i].valid) continue;
    if (n < SECONDS_PER_REPORT) {
      s_analysis_r1[n] = minuteData[i].rms1;
      s_analysis_r2[n] = minuteData[i].rms2;
      s_analysis_d1[n] = minuteData[i].diff1;
      s_analysis_d2[n] = minuteData[i].diff2;
      n++;
    }
  }

  if (n < MIN_VALID_SECONDS) {
    base.ready = false;
    g_system_state = STATE_SENSOR_FAULT;
    printProgressMarker("CALIBRATION_FAILED");
    printMemoryDiagnostics("CALIB_FAILED");
    Serial.println(F("\n================ CALIBRATION FAILED ================"));
    Serial.printf("Accepted Valid Seconds: %d/60 (Minimum required: %d)\n", n, MIN_VALID_SECONDS);
    Serial.println(F("REJECTION BREAKDOWN:"));
    Serial.printf("  - Sensor 1 ADC Clipping (>5%% clipped): %d/60 seconds\n", s1_clip_secs);
    Serial.printf("  - Sensor 2 ADC Clipping (>5%% clipped): %d/60 seconds\n", s2_clip_secs);
    Serial.printf("  - Sample Timing Overruns (>2%% late):   %d/60 seconds\n", late_secs);
    Serial.printf("Latest ADC Range: S1 [%d..%d] (Clips: %d) | S2 [%d..%d] (Clips: %d)\n",
                  g_last_obs.minRaw1, g_last_obs.maxRaw1, g_last_obs.s1_clip_count,
                  g_last_obs.minRaw2, g_last_obs.maxRaw2, g_last_obs.s2_clip_count);
    Serial.println(F("HARDWARE DIAGNOSTIC ADVICE:"));
    Serial.println(F("  1. Check 100k/100k voltage divider creating ~1.65V DC bias at GPIO 34 & 35."));
    Serial.println(F("  2. Check 0.1uF AC coupling capacitor & 1M resistor across piezo element."));
    Serial.println(F("  3. Check BAT54S dual Schottky clamping diodes to 3.3V and GND."));
    Serial.println(F("Send 'B' command after correcting hardware to retry baseline calibration."));
    Serial.println(F("====================================================\n"));
    return;
  }

  base.thresholdRms1  = baselineLimit(s_analysis_r1, n, RMS_RATIO_LIMIT, MIN_RMS_RISE, base.rms1);
  base.thresholdRms2  = baselineLimit(s_analysis_r2, n, RMS_RATIO_LIMIT, MIN_RMS_RISE, base.rms2);
  base.thresholdDiff1 = baselineLimit(s_analysis_d1, n, DIFF_RATIO_LIMIT, MIN_DIFF_RISE, base.diff1);
  base.thresholdDiff2 = baselineLimit(s_analysis_d2, n, DIFF_RATIO_LIMIT, MIN_DIFF_RISE, base.diff2);

  if (base.rms1 < 1.0f || base.rms2 < 1.0f) {
    Serial.println(F("CALIBRATION FAILED: one or both sensors have almost no AC signal. Send B to retry."));
    g_system_state = STATE_SENSOR_FAULT;
    printProgressMarker("CALIBRATION_FAILED");
    printMemoryDiagnostics("CALIB_FAILED");
    return;
  }

  base.ready = true;
  g_system_state = STATE_MONITORING_NORMAL;
  g_minute_number = 0;
  printProgressMarker("CALIBRATION_COMPLETE");
  printMemoryDiagnostics("CALIB_COMPLETE");
  Serial.println(F("\n============ BASELINE READY ============"));
  Serial.printf("S1 Normal RMS: %.2f (Thresh: %.2f) | DIFF: %.2f (Thresh: %.2f)\n",
                base.rms1, base.thresholdRms1, base.diff1, base.thresholdDiff1);
  Serial.printf("S2 Normal RMS: %.2f (Thresh: %.2f) | DIFF: %.2f (Thresh: %.2f)\n",
                base.rms2, base.thresholdRms2, base.diff2, base.thresholdDiff2);
  Serial.println(F("Entering 60-second real-time monitoring mode..."));
}

void analyzeMinute() {
  memset(s_analysis_a1, 0, sizeof(s_analysis_a1));
  memset(s_analysis_a2, 0, sizeof(s_analysis_a2));
  int valid = 0, count1 = 0, count2 = 0, simultaneous = 0;
  int leading1 = 0, leading2 = 0;
  int strongCorrelation = 0;
  int invalid = 0;

  for (int i = 0; i < SECONDS_PER_REPORT; ++i) {
    Observation &o = minuteData[i];
    if (!o.valid) { invalid++; continue; }

    if (valid < SECONDS_PER_REPORT) {
      s_analysis_r1[valid] = o.rms1;
      s_analysis_r2[valid] = o.rms2;
      s_analysis_d1[valid] = o.diff1;
      s_analysis_d2[valid] = o.diff2;
      valid++;
    }

    s_analysis_a1[i] = o.high1;
    s_analysis_a2[i] = o.high2;
    if (s_analysis_a1[i]) count1++;
    if (s_analysis_a2[i]) count2++;
    if (s_analysis_a1[i] && s_analysis_a2[i]) {
      simultaneous++;
      if (o.corr >= MIN_CORRELATION) {
        strongCorrelation++;
        if (o.lag >= 2 && o.lag <= 6) leading1++;
        if (o.lag <= -2 && o.lag >= -6) leading2++;
      }
    }
  }

  if (valid < MIN_VALID_SECONDS) {
    g_system_state = STATE_SENSOR_FAULT;
    printFull60SecondReport("INCONCLUSIVE - BAD SENSOR/SAMPLE QUALITY", valid, invalid,
                           0, 0, 0, 0, count1, count2, simultaneous, strongCorrelation,
                           leading1, leading2, "Excessive ADC clipping or timing overruns detected.");
    return;
  }

  float medR1 = medianOf(s_analysis_r1, valid), medR2 = medianOf(s_analysis_r2, valid);
  float medD1 = medianOf(s_analysis_d1, valid), medD2 = medianOf(s_analysis_d2, valid);
  int longest1 = longestRun(s_analysis_a1), longest2 = longestRun(s_analysis_a2);

  bool sustained1 = count1 >= g_persistence_req && longest1 >= MIN_CONTINUOUS_SECONDS &&
                    (medR1 > base.thresholdRms1 || medD1 > base.thresholdDiff1);
  bool sustained2 = count2 >= g_persistence_req && longest2 >= MIN_CONTINUOUS_SECONDS &&
                    (medR2 > base.thresholdRms2 || medD2 > base.thresholdDiff2);

  if (medR1 < 1 || medR2 < 1) {
    g_system_state = STATE_SENSOR_FAULT;
    printFull60SecondReport("SENSOR SIGNAL FAULT", valid, invalid,
                           medR1, medR2, medD1, medD2, count1, count2, simultaneous, strongCorrelation,
                           leading1, leading2, "Sensor disconnected or zero AC signal.");
    return;
  }

  if (sustained1 || sustained2) {
    g_system_state = STATE_CONFIRMED_LEAK_ALARM;
    String reasoning = "SUSTAINED ANOMALY DETECTED: ";
    if (sustained1 && sustained2) {
      reasoning += "Both S1 and S2 show continuous vibration elevation (>=" + String(g_persistence_req) + "/60s).";
    } else if (sustained1) {
      reasoning += "Sensor 1 elevated (" + String(count1) + "/60s) while Sensor 2 near baseline.";
    } else {
      reasoning += "Sensor 2 elevated (" + String(count2) + "/60s) while Sensor 1 near baseline.";
    }

    printFull60SecondReport("SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK", valid, invalid,
                           medR1, medR2, medD1, medD2, count1, count2, simultaneous, strongCorrelation,
                           leading1, leading2, reasoning.c_str());
  } else if (count1 >= INTERMITTENT_SECONDS || count2 >= INTERMITTENT_SECONDS) {
    g_system_state = STATE_SUSPECTED_ANOMALY;
    printFull60SecondReport("INTERMITTENT VIBRATION CHANGE", valid, invalid,
                           medR1, medR2, medD1, medD2, count1, count2, simultaneous, strongCorrelation,
                           leading1, leading2, "Short-duration spikes or pump speed fluctuation detected.");
  } else {
    g_system_state = STATE_MONITORING_NORMAL;
    printFull60SecondReport("NORMAL", valid, invalid,
                           medR1, medR2, medD1, medD2, count1, count2, simultaneous, strongCorrelation,
                           leading1, leading2, "Vibration levels within normal baseline statistical bounds.");
  }
}

// ============================================================================
// GPS PARSER & TELEMETRY
// ============================================================================

void readGPS() {
  while (Serial2.available() > 0) {
    char c = Serial2.read();
    if (c == '\r' || c == '\n') {
      if (g_nmea_buf_idx > 0) {
        g_nmea_line_buf[g_nmea_buf_idx] = '\0';
        parseNMEASentence(g_nmea_line_buf);
        g_nmea_buf_idx = 0;
      }
    } else if (g_nmea_buf_idx < sizeof(g_nmea_line_buf) - 1) {
      g_nmea_line_buf[g_nmea_buf_idx++] = c;
    }
  }
}

void parseNMEASentence(char* line) {
  if (strncmp(line, "$GPRMC", 6) == 0 || strncmp(line, "$GNRMC", 6) == 0) {
    char* tokens[15];
    uint8_t count = 0;
    char* p = line;
    tokens[count++] = p;
    while (*p && count < 15) {
      if (*p == ',') {
        *p = '\0';
        tokens[count++] = p + 1;
      }
      p++;
    }
    if (count >= 7) {
      char status = tokens[2][0];
      if (status == 'A') {
        float lat_raw = atof(tokens[3]);
        char lat_ns = tokens[4][0];
        float lon_raw = atof(tokens[5]);
        char lon_ew = tokens[6][0];

        int lat_deg = (int)(lat_raw / 100);
        float lat_min = lat_raw - (lat_deg * 100);
        float lat_dec = lat_deg + (lat_min / 60.0f);
        if (lat_ns == 'S') lat_dec = -lat_dec;

        int lon_deg = (int)(lon_raw / 100);
        float lon_min = lon_raw - (lon_deg * 100);
        float lon_dec = lon_deg + (lon_min / 60.0f);
        if (lon_ew == 'W') lon_dec = -lon_dec;

        if (lat_dec != 0.0f || lon_dec != 0.0f) {
          g_gps_lat = lat_dec;
          g_gps_lon = lon_dec;
          g_gps_has_fix = true;
          g_last_gps_fix_ms = millis();
        }
      } else if (status == 'V') {
        if (g_gps_has_fix && (millis() - g_last_gps_fix_ms > 10000)) {
          g_gps_has_fix = false;
        }
      }
    }
  } else if (strncmp(line, "$GPGGA", 6) == 0 || strncmp(line, "$GNGGA", 6) == 0) {
    char* tokens[15];
    uint8_t count = 0;
    char* p = line;
    tokens[count++] = p;
    while (*p && count < 15) {
      if (*p == ',') {
        *p = '\0';
        tokens[count++] = p + 1;
      }
      p++;
    }
    if (count >= 9) {
      int fix_quality = atoi(tokens[6]);
      int sats = atoi(tokens[7]);
      float hdop = atof(tokens[8]);

      g_gps_sats = (uint8_t)sats;
      if (hdop > 0.01f) g_gps_hdop = hdop;

      if (fix_quality > 0) {
        float lat_raw = atof(tokens[2]);
        char lat_ns = tokens[3][0];
        float lon_raw = atof(tokens[4]);
        char lon_ew = tokens[5][0];

        int lat_deg = (int)(lat_raw / 100);
        float lat_min = lat_raw - (lat_deg * 100);
        float lat_dec = lat_deg + (lat_min / 60.0f);
        if (lat_ns == 'S') lat_dec = -lat_dec;

        int lon_deg = (int)(lon_raw / 100);
        float lon_min = lon_raw - (lon_deg * 100);
        float lon_dec = lon_deg + (lon_min / 60.0f);
        if (lon_ew == 'W') lon_dec = -lon_dec;

        if (lat_dec != 0.0f || lon_dec != 0.0f) {
          g_gps_lat = lat_dec;
          g_gps_lon = lon_dec;
          g_gps_has_fix = true;
          g_last_gps_fix_ms = millis();
        }
      }
    }
  }
}

void printGPSTelemetry() {
  uint32_t fix_age = g_gps_has_fix ? (millis() - g_last_gps_fix_ms) : 999999;
  const char* fix_str = "NO_FIX";
  if (g_gps_has_fix) {
    fix_str = (fix_age > 10000) ? "STALE" : "FIX";
  }
  Serial.printf("GPS,%.6f,%.6f,%u,%.2f,%lu,%s\n",
                g_gps_lat, g_gps_lon, (unsigned int)g_gps_sats, g_gps_hdop,
                (unsigned long)fix_age, fix_str);
}

// ============================================================================
// DIAGNOSTICS & REPORTING
// ============================================================================

void printADCDiagnostics() {
  Serial.println(F("\n================ ADC HARDWARE DIAGNOSTIC SNAPSHOT ================"));
  Serial.printf("GPS Reading: %s | Total Run Time: %lu sec | Eff Rate: %.1f Hz\n",
                g_gps_enabled ? "ENABLED" : "DISABLED", g_total_seconds_elapsed, g_last_obs.effective_hz);
  Serial.printf("S1 ADC (GPIO 34): Mean=%6.1f | Min=%4d | Max=%4d | P2P=%4.0f | Clips=%4d (%4.1f%%) | RMS=%6.1f %s\n",
                g_last_obs.meanRaw1, g_last_obs.minRaw1, g_last_obs.maxRaw1, g_last_obs.p2p1,
                g_last_obs.s1_clip_count, g_last_obs.s1_clip_pct, g_last_obs.rms1,
                (g_last_obs.s1_clip_count > 0) ? "[CLIPPED/SATURATED]" : "[OK]");
  Serial.printf("S2 ADC (GPIO 35): Mean=%6.1f | Min=%4d | Max=%4d | P2P=%4.0f | Clips=%4d (%4.1f%%) | RMS=%6.1f %s\n",
                g_last_obs.meanRaw2, g_last_obs.minRaw2, g_last_obs.maxRaw2, g_last_obs.p2p2,
                g_last_obs.s2_clip_count, g_last_obs.s2_clip_pct, g_last_obs.rms2,
                (g_last_obs.s2_clip_count > 0) ? "[CLIPPED/SATURATED]" : "[OK]");
  printMemoryDiagnostics("ADC_SNAPSHOT");
  Serial.println(F("------------------------------------------------------------------\n"));
}

void printStatusReport() {
  Serial.println(F("\n================ SYSTEM STATUS REPORT ================"));
  Serial.printf("State: %s | Total Run Time: %lu sec\n",
                (g_system_state == STATE_CALIBRATING) ? "CALIBRATING" :
                (g_system_state == STATE_MONITORING_NORMAL) ? "MONITORING_NORMAL" :
                (g_system_state == STATE_SUSPECTED_ANOMALY) ? "SUSPECTED_ANOMALY" :
                (g_system_state == STATE_CONFIRMED_LEAK_ALARM) ? "CONFIRMED_LEAK_ALARM" : "SENSOR_FAULT",
                g_total_seconds_elapsed);
  Serial.printf("Persistence Threshold: %u / 60 seconds\n", g_persistence_req);

  if (base.ready) {
    Serial.printf("S1 Normal RMS: %.2f | Thresh: %.2f | DIFF: %.2f\n", base.rms1, base.thresholdRms1, base.diff1);
    Serial.printf("S2 Normal RMS: %.2f | Thresh: %.2f | DIFF: %.2f\n", base.rms2, base.thresholdRms2, base.diff2);
  } else {
    Serial.println(F("Baseline: NOT YET CALIBRATED / FAULT"));
  }
  printMemoryDiagnostics("STATUS_QUERY");
  Serial.println(F("======================================================\n"));
}

void printFull60SecondReport(const char* state_str, int valid, int invalid,
                             float medR1, float medR2, float medD1, float medD2,
                             int count1, int count2, int simultaneous,
                             int strongCorr, int lead1, int lead2,
                             const char* reasoning) {
  Serial.println(F("\n================================================================================"));
  Serial.printf("           FULL 60-SECOND MONITORING REPORT #%lu\n", g_minute_number);
  Serial.println(F("================================================================================"));
  Serial.printf("FINAL DECISION:        [%s]\n", state_str);
  Serial.printf("REASONING:             %s\n", reasoning);
  Serial.printf("VALID SECONDS:         %d/60 | Invalid: %d\n", valid, invalid);
  Serial.println(F("--------------------------------------------------------------------------------"));
  Serial.printf("S1: Median RMS %5.1f (x%.2f baseline) | DIFF %5.1f | Abnormal %d/60s\n",
                medR1, base.rms1 > 0 ? medR1 / base.rms1 : 1.0f, medD1, count1);
  Serial.printf("S2: Median RMS %5.1f (x%.2f baseline) | DIFF %5.1f | Abnormal %d/60s\n",
                medR2, base.rms2 > 0 ? medR2 / base.rms2 : 1.0f, medD2, count2);
  Serial.printf("Simultaneous abnormal seconds: %d/60\n", simultaneous);
  Serial.printf("Correlated windows: %d | S1 leads: %d | S2 leads: %d\n", strongCorr, lead1, lead2);
  Serial.println(F("================================================================================\n"));
}

// ============================================================================
// SERIAL COMMAND INTERFACE
// ============================================================================

void handleSerialCommands() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "H" || cmd == "HELP") {
      printHelp();
    } else if (cmd == "B" || cmd == "CAL") {
      Serial.println(F("\n[COMMAND] Manual Baseline Recalibration Triggered."));
      calibrate();
    } else if (cmd == "V" || cmd == "VERBOSE") {
      g_verbose_mode = !g_verbose_mode;
      Serial.printf("[COMMAND] Live Verbose Diagnostic Output: %s\n", g_verbose_mode ? "ENABLED" : "DISABLED");
    } else if (cmd == "M" || cmd == "MODE") {
      g_csv_mode = !g_csv_mode;
      Serial.printf("[COMMAND] Serial Output Format: %s\n", g_csv_mode ? "MACHINE CSV" : "HUMAN READABLE");
    } else if (cmd == "G" || cmd == "GPS") {
      g_gps_enabled = !g_gps_enabled;
      Serial.printf("[COMMAND] GPS Processing: %s\n", g_gps_enabled ? "ENABLED" : "DISABLED");
    } else if (cmd == "D" || cmd == "DIAG") {
      printADCDiagnostics();
    } else if (cmd == "F" || cmd == "FLOW") {
      printFlowDiagnostics();
    } else if (cmd == "S" || cmd == "STATUS") {
      printStatusReport();
    } else if (cmd.startsWith("P ") || cmd.startsWith("PARAM ")) {
      int space_idx = cmd.indexOf(' ');
      int val = cmd.substring(space_idx + 1).toInt();
      if (val >= 10 && val <= 60) {
        g_persistence_req = val;
        Serial.printf("[COMMAND] Persistence Threshold updated to %d/60 seconds.\n", g_persistence_req);
      }
    }
  }
}

void printHelp() {
  Serial.println(F("\n=================== SERIAL COMMAND MENU ==================="));
  Serial.println(F("  H or HELP      - Display command menu"));
  Serial.println(F("  B or CAL       - Perform 60-sec baseline recalibration"));
  Serial.println(F("  V or VERBOSE   - Toggle 1-second live preliminary diagnostics"));
  Serial.println(F("  M or MODE      - Toggle output mode (Human-Readable vs CSV)"));
  Serial.println(F("  G or GPS       - Toggle GPS UART2 reading"));
  Serial.println(F("  D or DIAG      - Print ADC hardware diagnostic snapshot"));
  Serial.println(F("  F or FLOW      - Print flow sensor diagnostics & pulse counts"));
  Serial.println(F("  S or STATUS    - Display system status & calibration metrics"));
  Serial.println(F("  P <10-60>      - Set persistence threshold seconds"));
  Serial.println(F("===========================================================\n"));
}

// ============================================================================
// ARDUINO SETUP & MAIN LOOP
// ============================================================================

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20); // Prevent 1000ms blocking timeout on partial serial commands
  while (!Serial && millis() < 3000);

  Serial2.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_S1, ADC_11db);
  analogSetPinAttenuation(PIN_S2, ADC_11db);

  pinMode(PIN_FLOW_IN, INPUT_PULLUP);
  pinMode(PIN_FLOW_OUT, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_IN), flowInletISR, FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_OUT), flowOutletISR, FALLING);

  Serial.println(F("\nESP32 PIPELINE MONITOR - RESTORED PRE-GPS DSP ARCHITECTURE"));
  Serial.printf("Steel Pipe | Sensor separation: %.2f m\n", SENSOR_SPACING_M);
  Serial.println(F("Sensor 1 -> GPIO 34 | Sensor 2 -> GPIO 35"));
  Serial.printf("Flow Meters -> Inlet GPIO %d, Outlet GPIO %d (YF-S201, 450 P/L)\n", PIN_FLOW_IN, PIN_FLOW_OUT);
  Serial.printf("GPS UART2 -> RX GPIO %d, TX GPIO %d @ %d Baud\n", PIN_GPS_RX, PIN_GPS_TX, GPS_BAUD);
  printMemoryDiagnostics("BOOT_SETUP");
  Serial.println(F("Starting initial 60-second baseline calibration..."));

  delay(2000);
  calibrate();
}

void loop() {
  handleSerialCommands();

  // CONTINUOUS TELEMETRY STREAMING: Never stop outputting 1-second CSV telemetry even if uncalibrated/faulted
  if (!base.ready) {
    uint32_t startMs = millis();
    Observation o = captureObservation();
    const TDOAResult& tdoa = captureHighSpeedTDOA();
    g_last_obs = o;
    g_total_seconds_elapsed++;

    if (g_gps_enabled) readGPS();
    handleSerialCommands();

    const char* statusStr = (g_system_state == STATE_CALIBRATING) ? "CALIBRATING" :
                            (!o.valid || o.clipped_count > 0) ? "ADC_CLIPPING_FAULT" : "CALIBRATION_FAILED";

    if (g_csv_mode) {
      Serial.printf("CSV,%lu,%lu,%.2f,%.1f,%.2f,%.2f,%.2f,%.1f,%.2f,%.2f,0,0,1,%s\n",
                    millis(), g_total_seconds_elapsed,
                    o.rms1, o.p2p1, o.rms1 * o.rms1, o.diff1,
                    o.rms2, o.p2p2, o.rms2 * o.rms2, o.diff2,
                    statusStr);
      printTDOATelemetry(tdoa);
      printADCTelemetry(o);
      if (g_gps_enabled) printGPSTelemetry();
      recordTDOAHistory(tdoa);
      evaluateFlowSensors();
    } else if (g_verbose_mode) {
      Serial.printf("[DIAG %s] S1 RMS: %5.1f P2P: %5.1f | S2 RMS: %5.1f P2P: %5.1f [%s]\n",
                    (g_system_state == STATE_CALIBRATING) ? "CALIBRATING" : "FAULT",
                    o.rms1, o.p2p1, o.rms2, o.p2p2, statusStr);
    }

    uint32_t elapsedMs = millis() - startMs;
    if (elapsedMs < 1000) {
      delay(1000 - elapsedMs);
    }
    return;
  }

  // Normal 60-Second Monitoring Loop
  for (int sec = 0; sec < SECONDS_PER_REPORT; ++sec) {
    uint32_t startMs = millis();
    Observation o = captureObservation();
    const TDOAResult& tdoa = captureHighSpeedTDOA();

    o.high1 = (o.rms1 > base.thresholdRms1) || (o.diff1 > base.thresholdDiff1);
    o.high2 = (o.rms2 > base.thresholdRms2) || (o.diff2 > base.thresholdDiff2);
    if (o.high1 && o.high2) {
      estimateDirection(o);
    }
    minuteData[sec] = o;
    g_last_obs = o;
    g_total_seconds_elapsed++;

    if (g_gps_enabled) readGPS();
    handleSerialCommands();

    const char* statusStr = !o.valid ? "ADC_CLIPPING_FAULT" :
                            (o.high1 || o.high2) ? "PRELIM_ABNORMAL" : "PRELIM_NORMAL";

    if (g_csv_mode) {
      Serial.printf("CSV,%lu,%lu,%.2f,%.1f,%.2f,%.2f,%.2f,%.1f,%.2f,%.2f,%d,%d,%d,%s\n",
                    millis(), g_total_seconds_elapsed,
                    o.rms1, o.p2p1, o.rms1 * o.rms1, o.diff1,
                    o.rms2, o.p2p2, o.rms2 * o.rms2, o.diff2,
                    o.high1 ? 1 : 0, o.high2 ? 1 : 0,
                    (!o.valid || o.clipped_count > 0) ? 1 : 0,
                    statusStr);
      printTDOATelemetry(tdoa);
      printADCTelemetry(o);
      if (g_gps_enabled) printGPSTelemetry();
      recordTDOAHistory(tdoa);
      evaluateFlowSensors();
    } else if (g_verbose_mode) {
      Serial.printf("[LIVE-DIAG %02d/60] S1 RMS: %5.1f (Th: %5.1f) | S2 RMS: %5.1f (Th: %5.1f) [%s]\n",
                    sec + 1, o.rms1, base.thresholdRms1, o.rms2, base.thresholdRms2, statusStr);
    }

    uint32_t elapsedMs = millis() - startMs;
    if (elapsedMs < 1000) {
      delay(1000 - elapsedMs);
    }
  }

  ++g_minute_number;
  analyzeMinute();
}
