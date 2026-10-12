/*
 * Arduino UNO Pipeline Monitor — Transmitter Node
 * GPS (NEO-6M) + 2x Piezo vibration sensors + 2x YF-S201 flow sensors -> NRF24L01
 *
 * ═══════════════════════════ PIN CONNECTIONS ═══════════════════════════════
 *  (D0 / D1 are NOT used: they are the USB serial pins)
 *
 *  NEO-6M GPS
 *    GPS TX  -> D4     (SoftwareSerial RX)  [3.3V logic, safe to connect directly]
 *    GPS RX  -> D5     (SoftwareSerial TX)  [OPTIONAL: this sketch never sends to the
 *                                            GPS, so you can leave it unconnected.
 *                                            If you do connect it, use a divider:
 *                                            D5 -> 10k -> GPS RX, GPS RX -> 20k -> GND]
 *    VCC     -> 5V     (only if your module has an onboard regulator, e.g. GY-GPS6MV2;
 *                       otherwise use 3.3V)
 *    GND     -> GND
 *
 *  NRF24L01 (same as the receiver)
 *    CE   -> D7
 *    CSN  -> D8
 *    SCK  -> D13
 *    MOSI -> D11
 *    MISO -> D12
 *    VCC  -> 3.3V ONLY  (10uF capacitor across VCC/GND at the module.
 *                        PA+LNA modules can draw >100 mA: use a separate 3.3V
 *                        supply, UNO 3.3V pin only gives ~150 mA)
 *    GND  -> GND
 *
 *  Piezo sensor 1 (vibration)  -> A0
 *  Piezo sensor 2 (vibration)  -> A1
 *     Conditioning circuit for each piezo (UNO = 5V reference, so bias is 2.5V):
 *       - 100k / 100k divider from 5V to GND -> ~2.5V DC bias at the analog pin
 *         (10k / 10k also works and gives a lower, better source impedance
 *          for the UNO's ADC)
 *       - 0.1uF AC-coupling capacitor in series with the piezo signal
 *       - 1M resistor across the piezo element
 *       - BAT54S dual Schottky clamp: one diode to 5V, one to GND
 *     Piezo signal -> cap -> analog pin (bias point). Piezo return -> GND.
 *
 *  Flow sensor INLET   (YF-S201 yellow wire) -> D2  (INT0)
 *  Flow sensor OUTLET  (YF-S201 yellow wire) -> D3  (INT1)
 *     YF-S201: red -> 5V, black -> GND. 5V logic, so no divider is needed.
 *
 *  All grounds common (UNO, GPS, NRF24, piezo circuits, flow sensors).
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Wireless: Channel 76 (2476 MHz), 250 KBPS, address "TRN01", one 32-byte packet / 2 s.
 * Libraries: RF24, TinyGPSPlus (SoftwareSerial is built in).
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <SoftwareSerial.h>
#include <TinyGPSPlus.h>

// ─── Pin Definitions ──────────────────────────────────────────────────────────
#define GPS_RX_PIN      4     // UNO D4 <- GPS TX
#define GPS_TX_PIN      5     // UNO D5 -> GPS RX (optional / unused)
#define GPS_BAUD        9600

#define NRF_CE_PIN      7
#define NRF_CSN_PIN     8

#define PIN_PIEZO1      A0
#define PIN_PIEZO2      A1
#define PIN_FLOW_IN     2     // INT0
#define PIN_FLOW_OUT    3     // INT1

// ─── Node Identity & Radio Setup ──────────────────────────────────────────────
#define NODE_ID_NUM     1
const byte radioAddress[6] = "TRN01";

// ─── Piezo (vibration) acquisition settings (UNO ADC is 10-bit: 0..1023) ──────
const int      POINTS             = 1000;  // samples per window (~0.4 s)
const uint32_t SAMPLE_INTERVAL_US = 400;   // 2.5 kHz per channel
const int      DISCARD_POINTS     = 30;    // let the high-pass filter settle
const float    HP_ALPHA           = 0.98f; // DC blocker: y = a*(y + x - xprev)
const int      CLIP_LOW           = 1;     // raw <= 1 or raw >= 1022 counts as clipped
const int      CLIP_HIGH          = 1022;

// ─── Flow sensor settings ─────────────────────────────────────────────────────
const float K_IN  = 450.0f;   // pulses per litre, inlet  (replace with calibrated value)
const float K_OUT = 450.0f;   // pulses per litre, outlet (replace with calibrated value)
const unsigned long FLOW_WINDOW_MS  = 5000;
const float LEAK_THRESHOLD_LPM      = 0.10f;
const uint8_t CONFIRM_WINDOWS       = 3;
const float MIN_FLOW_FOR_ASSESS_LPM = 0.5f;

// ─── Telemetry Packet (EXACTLY 32 bytes) ──────────────────────────────────────
// flags: bit0 = gps valid (location+date+time)   bit1 = piezo1 clipping
//        bit2 = piezo2 clipping                  bit3 = leak alarm (flow)
//        bit4 = vibration window invalid (timing overrun / heavy clipping)
struct __attribute__((packed)) SensorPacket {
  uint8_t  node_id_num;     // 1
  uint16_t sequence;        // 2   (wraps at 65535)
  int32_t  lat_e7;          // 4   latitude  * 1e7  (degrees)
  int32_t  lng_e7;          // 4   longitude * 1e7  (degrees)
  uint8_t  satellites;      // 1
  uint8_t  hdop_x10;        // 1   HDOP * 10
  uint8_t  flags;           // 1
  uint8_t  year_2000;       // 1   UTC year - 2000
  uint8_t  month;           // 1
  uint8_t  day;             // 1
  uint8_t  hour;            // 1
  uint8_t  minute;          // 1
  uint8_t  second;          // 1
  uint16_t flow_in_x100;    // 2   inlet  L/min * 100
  uint16_t flow_out_x100;   // 2   outlet L/min * 100
  uint16_t rms1_x10;        // 2   piezo 1 AC RMS (10-bit ADC counts) * 10
  uint16_t rms2_x10;        // 2   piezo 2 AC RMS (10-bit ADC counts) * 10
  uint16_t p2p1;            // 2   piezo 1 peak-to-peak (ADC counts, 0-1023)
  uint16_t p2p2;            // 2   piezo 2 peak-to-peak (ADC counts, 0-1023)
};
static_assert(sizeof(SensorPacket) == 32, "SensorPacket must be exactly 32 bytes");

// ─── TDOA Localization Packet (EXACTLY 24 bytes <= 32 bytes) ───────────────────
// Packet Type 0x02: Transmits signed TDOA and position along 2.0m pipeline
struct __attribute__((packed)) TdoaPacket {
  uint8_t  pkt_type;        // 0x02 = TDOA Localization Packet
  uint8_t  version;         // 1
  uint8_t  node_id;         // 1
  uint16_t event_id;        // Monotonic event ID
  uint32_t timestamp_ms;    // millis() on Arduino
  int16_t  delta_t_us;      // Signed TDOA (t2 - t1) in microseconds
  uint16_t est_dist_mm;     // Distance from Sensor 1 in millimeters (0..2000 mm)
  uint8_t  corr_peak_x100;  // Correlation peak * 100 (0..100)
  uint8_t  psr_x10;         // Peak-to-Sidelobe Ratio * 10
  uint8_t  flags;           // bit0: loc_valid, bit1: clip1, bit2: clip2, bit3: out_of_bounds, bit4: low_signal
  uint8_t  failure_code;    // 0=OK, 1=CLIPPING, 2=LOW_SIGNAL, 3=LOW_CORRELATION, 4=OUT_OF_BOUNDS, 5=TIMING_FAULT
  uint8_t  sample_rate_khz; // 19 (kHz)
  uint8_t  skew_us;         // 26 (us)
  uint8_t  reserved[5];     // Padding to 24 bytes
};
static_assert(sizeof(TdoaPacket) == 24, "TdoaPacket must be 24 bytes");

// ─── Global Objects ───────────────────────────────────────────────────────────
SoftwareSerial gpsSerial(GPS_RX_PIN, GPS_TX_PIN);
TinyGPSPlus    gps;
RF24           radio(NRF_CE_PIN, NRF_CSN_PIN);

uint16_t seqCounter = 0;

// Flow state
volatile uint32_t inletPulses  = 0;
volatile uint32_t outletPulses = 0;
unsigned long flowPrevMillis   = 0;
float   flowInLpm   = 0.0f;
float   flowOutLpm  = 0.0f;
uint8_t leakCount   = 0;
uint8_t normalCount = 0;
bool    leakAlarm   = false;

// Vibration result
struct VibResult {
  float    rms1;
  float    rms2;
  uint16_t p2p1;
  uint16_t p2p2;
  int      clip1;
  int      clip2;
  bool     valid;
};

// ─── Flow interrupts ──────────────────────────────────────────────────────────
void inletISR()  { inletPulses++;  }
void outletISR() { outletPulses++; }

// Evaluate a flow window every 5 s
void updateFlow() {
  unsigned long now = millis();
  unsigned long elapsed = now - flowPrevMillis;
  if (elapsed < FLOW_WINDOW_MS) return;
  flowPrevMillis = now;

  noInterrupts();
  uint32_t pIn  = inletPulses;
  uint32_t pOut = outletPulses;
  inletPulses  = 0;
  outletPulses = 0;
  interrupts();

  flowInLpm  = (pIn  * 60000.0f) / (K_IN  * elapsed);
  flowOutLpm = (pOut * 60000.0f) / (K_OUT * elapsed);
  float difference = flowInLpm - flowOutLpm;

  if (flowInLpm < MIN_FLOW_FOR_ASSESS_LPM) {
    leakCount = 0;
    normalCount = 0;
    leakAlarm = false;
    return;
  }

  if (difference >= LEAK_THRESHOLD_LPM) {
    if (leakCount < CONFIRM_WINDOWS) leakCount++;
    normalCount = 0;
    if (leakCount >= CONFIRM_WINDOWS) leakAlarm = true;
  } else {
    leakCount = 0;
    if (normalCount < CONFIRM_WINDOWS) normalCount++;
    if (normalCount >= CONFIRM_WINDOWS) leakAlarm = false;
  }
}

// ─── Vibration (piezo) capture: 2 channels, high-pass filtered RMS + P2P ──────
VibResult captureVibration() {
  VibResult r;
  r.rms1 = r.rms2 = 0;
  r.p2p1 = r.p2p2 = 0;
  r.clip1 = r.clip2 = 0;
  r.valid = false;

  float prev1 = 0, prev2 = 0, y1 = 0, y2 = 0;
  unsigned long sum1 = 0, sum2 = 0;
  int used = 0, late = 0, clipped = 0;
  int min1 = 1023, max1 = 0, min2 = 1023, max2 = 0;

  uint32_t next = micros();

  for (int i = 0; i < POINTS; ++i) {
    while ((int32_t)(micros() - next) < 0) { }
    if ((int32_t)(micros() - next) > (int32_t)(SAMPLE_INTERVAL_US / 2)) late++;
    next += SAMPLE_INTERVAL_US;

    int raw1 = analogRead(PIN_PIEZO1);
    int raw2 = analogRead(PIN_PIEZO2);

    if (raw1 < min1) min1 = raw1;
    if (raw1 > max1) max1 = raw1;
    if (raw2 < min2) min2 = raw2;
    if (raw2 > max2) max2 = raw2;

    bool c1 = (raw1 <= CLIP_LOW || raw1 >= CLIP_HIGH);
    bool c2 = (raw2 <= CLIP_LOW || raw2 >= CLIP_HIGH);
    if (c1) r.clip1++;
    if (c2) r.clip2++;
    if (c1 || c2) clipped++;

    if (i == 0) { prev1 = raw1; prev2 = raw2; }

    y1 = HP_ALPHA * (y1 + raw1 - prev1);
    y2 = HP_ALPHA * (y2 + raw2 - prev2);
    prev1 = raw1;
    prev2 = raw2;

    if (i >= DISCARD_POINTS) {
      sum1 += (unsigned long)(y1 * y1);
      sum2 += (unsigned long)(y2 * y2);
      used++;
    }
  }

  r.rms1  = used > 0 ? sqrt((float)sum1 / used) : 0;
  r.rms2  = used > 0 ? sqrt((float)sum2 / used) : 0;
  r.p2p1  = (uint16_t)(max1 - min1);
  r.p2p2  = (uint16_t)(max2 - min2);
  r.valid = (late <= POINTS / 50) && (clipped <= POINTS / 20);
  return r;
}

// ─── Arduino Uno High-Speed Burst Dual-Channel Sampling & TDOA Estimation ────
const float    PIPE_LENGTH_M      = 2.0f;
const float    WAVE_VELOCITY_MPS  = 1250.0f; // Nominal / uncalibrated acoustic velocity (m/s)
const uint8_t  TDOA_BURST_SAMPLES = 96;     // 96 sample pairs (~4.99 ms acquisition)
const int8_t   MAX_TDOA_LAG       = 32;     // ±32 lags * 52 us = ±1664 us (covers full 2.0m pipe)
uint16_t tdoaEventCounter = 0;

// Static BSS buffers to prevent runtime stack exhaustion
static int8_t   tdoa_b1[TDOA_BURST_SAMPLES];
static int8_t   tdoa_b2[TDOA_BURST_SAMPLES];
static uint16_t tdoa_raw1[TDOA_BURST_SAMPLES];
static uint16_t tdoa_raw2[TDOA_BURST_SAMPLES];
static int32_t  tdoa_rArray[2 * MAX_TDOA_LAG + 1];

TdoaPacket captureTdoaBurst(bool isTransient = false) {
  TdoaPacket pkt;
  memset(&pkt, 0, sizeof(pkt));
  pkt.pkt_type        = 0x02;
  pkt.version         = 1;
  pkt.node_id         = NODE_ID_NUM;
  pkt.event_id        = ++tdoaEventCounter;
  pkt.timestamp_ms    = millis();
  pkt.sample_rate_khz = 19;
  pkt.skew_us         = 26;
  if (isTransient) pkt.flags |= 0x20; // bit5 = is_transient trigger

  // Configure ADC prescaler to 32 (500 kHz ADC clock -> 26 us per conversion)
  uint8_t oldADCSRA = ADCSRA;
  ADCSRA = (ADCSRA & ~0x07) | 0x05;

  int clipCount1 = 0;
  int clipCount2 = 0;
  int32_t sumRaw1 = 0;
  int32_t sumRaw2 = 0;

  for (uint8_t i = 0; i < TDOA_BURST_SAMPLES; ++i) {
    uint16_t r1 = analogRead(PIN_PIEZO1);
    uint16_t r2 = analogRead(PIN_PIEZO2);
    tdoa_raw1[i] = r1;
    tdoa_raw2[i] = r2;
    sumRaw1 += r1;
    sumRaw2 += r2;
    if (r1 <= CLIP_LOW || r1 >= CLIP_HIGH) clipCount1++;
    if (r2 <= CLIP_LOW || r2 >= CLIP_HIGH) clipCount2++;
  }

  // Restore default ADC prescaler
  ADCSRA = oldADCSRA;

  // Rail saturation check (> 5% of samples)
  if (clipCount1 > (TDOA_BURST_SAMPLES / 20)) pkt.flags |= 0x02;
  if (clipCount2 > (TDOA_BURST_SAMPLES / 20)) pkt.flags |= 0x04;
  if ((pkt.flags & 0x02) || (pkt.flags & 0x04)) {
    pkt.failure_code = 1; // CLIPPING
    return pkt;
  }

  int16_t mean1 = sumRaw1 / TDOA_BURST_SAMPLES;
  int16_t mean2 = sumRaw2 / TDOA_BURST_SAMPLES;

  int32_t varSum1 = 0;
  int32_t varSum2 = 0;

  for (uint8_t i = 0; i < TDOA_BURST_SAMPLES; ++i) {
    int16_t d1 = (int16_t)tdoa_raw1[i] - mean1;
    int16_t d2 = (int16_t)tdoa_raw2[i] - mean2;
    tdoa_b1[i] = (int8_t)constrain(d1 / 2, -127, 127);
    tdoa_b2[i] = (int8_t)constrain(d2 / 2, -127, 127);
    varSum1 += (int32_t)tdoa_b1[i] * tdoa_b1[i];
    varSum2 += (int32_t)tdoa_b2[i] * tdoa_b2[i];
  }

  // Low signal power check
  if (varSum1 < 100 || varSum2 < 100) {
    pkt.failure_code = 2; // LOW_SIGNAL
    pkt.flags |= 0x10;
    return pkt;
  }

  const float PAIR_INTERVAL_US = 52.0f;
  const float SKEW_US          = 26.0f;

  int8_t bestLag = 0;
  int32_t maxDot = -2147483647L;

  for (int8_t lag = -MAX_TDOA_LAG; lag <= MAX_TDOA_LAG; ++lag) {
    int32_t dot = 0;
    int32_t e1 = 0;
    int32_t e2 = 0;
    uint8_t start1 = (lag < 0) ? -lag : 0;
    uint8_t start2 = (lag > 0) ? lag : 0;
    uint8_t count = TDOA_BURST_SAMPLES - abs(lag);

    for (uint8_t k = 0; k < count; ++k) {
      int8_t v1 = tdoa_b1[start1 + k];
      int8_t v2 = tdoa_b2[start2 + k];
      dot += (int32_t)v1 * v2;
      e1  += (int32_t)v1 * v1;
      e2  += (int32_t)v2 * v2;
    }

    uint8_t idx = lag + MAX_TDOA_LAG;
    int32_t normScore = 0;
    float denom = sqrt((float)e1 * (float)e2);
    if (denom > 1.0f) {
      normScore = (int32_t)((dot / denom) * 1000.0f);
    }
    tdoa_rArray[idx] = normScore;

    if (normScore > maxDot) {
      maxDot = normScore;
      bestLag = lag;
    }
  }

  float bestR = (float)maxDot / 1000.0f;
  pkt.corr_peak_x100 = (bestR > 0) ? (uint8_t)constrain(bestR * 100.0f, 0, 100) : 0;

  // Peak-to-Sidelobe Ratio (PSR)
  int32_t sideSum = 0;
  uint8_t sideCount = 0;
  for (int8_t l = -MAX_TDOA_LAG; l <= MAX_TDOA_LAG; ++l) {
    if (abs(l - bestLag) >= 2) {
      sideSum += tdoa_rArray[l + MAX_TDOA_LAG];
      sideCount++;
    }
  }
  float meanSide = sideCount > 0 ? (float)sideSum / sideCount : 0.0f;
  float psr = (meanSide < maxDot) ? ((float)maxDot - meanSide) / 300.0f : 1.0f;
  pkt.psr_x10 = (uint8_t)constrain(psr * 10.0f, 0, 255);

  if (bestR < 0.65f) {
    pkt.failure_code = 3; // LOW_CORRELATION
    return pkt;
  }

  // Sub-sample parabolic interpolation
  float delta = 0.0f;
  uint8_t bIdx = bestLag + MAX_TDOA_LAG;
  if (bIdx > 0 && bIdx < (2 * MAX_TDOA_LAG)) {
    float yL = tdoa_rArray[bIdx - 1];
    float yM = tdoa_rArray[bIdx];
    float yR = tdoa_rArray[bIdx + 1];
    float denom = 2.0f * (2.0f * yM - yL - yR);
    if (abs(denom) > 1.0f) {
      delta = (yR - yL) / denom;
      if (delta < -0.5f) delta = -0.5f;
      if (delta > 0.5f) delta = 0.5f;
    }
  }

  float refinedLag = (float)bestLag + delta;
  // Timing calibration: A1 is sampled 26 us later than A0, so true delay is (lag * Tpair) + SKEW_US
  float dt_us = (refinedLag * PAIR_INTERVAL_US) + SKEW_US;
  pkt.delta_t_us = (int16_t)round(dt_us);

  // Physical formula: d1 = (L - velocity * delta_t) / 2
  float dt_sec = dt_us * 1e-6f;
  float d1 = (PIPE_LENGTH_M - (WAVE_VELOCITY_MPS * dt_sec)) / 2.0f;

  if (d1 < 0.0f || d1 > PIPE_LENGTH_M || isnan(d1)) {
    pkt.failure_code = 4; // OUT_OF_BOUNDS
    pkt.flags |= 0x08;
    return pkt;
  }

  pkt.flags |= 0x01; // loc_valid = true
  pkt.failure_code = 0; // OK
  pkt.est_dist_mm = (uint16_t)round(d1 * 1000.0f);
  return pkt;
}

// ─── Adaptive Transient Detection State & Trigger ─────────────────────────────
const int           TRANSIENT_DEV_THRESHOLD     = 60;  // ADC counts deviation from quiescent bias (~0.3V jump)
const unsigned long TRANSIENT_REFRACTORY_MS     = 600; // Refractory interval after a trigger event (ms)
static unsigned long lastTransientCheckMicros   = 0;
static unsigned long lastTransientTriggerMillis = 0;
static int16_t      baselineA0                  = 512;
static int16_t      baselineA1                  = 512;
static bool         hasPendingTdoa              = false;
static TdoaPacket   pendingTdoaPkt;

void checkTransientTrigger() {
  uint32_t nowMicros = micros();
  if ((uint32_t)(nowMicros - lastTransientCheckMicros) < 2000) return;
  lastTransientCheckMicros = nowMicros;

  uint32_t nowMillis = millis();
  if ((uint32_t)(nowMillis - lastTransientTriggerMillis) < TRANSIENT_REFRACTORY_MS) return;

  // Fast analog read using prescaler 32 (500 kHz ADC clock -> 26 us per channel)
  uint8_t oldADCSRA = ADCSRA;
  ADCSRA = (ADCSRA & ~0x07) | 0x05;
  int raw1 = analogRead(PIN_PIEZO1);
  int raw2 = analogRead(PIN_PIEZO2);
  ADCSRA = oldADCSRA;

  // Slow baseline tracking for ~2.5V DC bias (~512)
  baselineA0 = (int16_t)(((int32_t)baselineA0 * 63 + raw1) / 64);
  baselineA1 = (int16_t)(((int32_t)baselineA1 * 63 + raw2) / 64);

  int dev1 = abs(raw1 - baselineA0);
  int dev2 = abs(raw2 - baselineA1);

  if (dev1 > TRANSIENT_DEV_THRESHOLD || dev2 > TRANSIENT_DEV_THRESHOLD) {
    lastTransientTriggerMillis = nowMillis;

    // Transient detected! Acquire 96-sample high-speed TDOA burst immediately
    gpsSerial.stopListening();
    pendingTdoaPkt = captureTdoaBurst(true); // true = transient triggered (flag 0x20 set)
    gpsSerial.listen();
    hasPendingTdoa = true;

    // Transmit the transient TDOA packet immediately over nRF24!
    radio.write(&pendingTdoaPkt, sizeof(pendingTdoaPkt));
    while (radio.isAckPayloadAvailable()) {
      uint8_t dummy[32];
      radio.read(&dummy, radio.getDynamicPayloadSize());
    }

    Serial.print(F("[TRANSIENT TRIGGER #"));
    Serial.print(pendingTdoaPkt.event_id);
    Serial.print(F("] dt="));
    Serial.print(pendingTdoaPkt.delta_t_us);
    Serial.print(F("us R="));
    Serial.println((float)pendingTdoaPkt.corr_peak_x100 / 100.0f, 2);
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
uint16_t clampU16(float v) {
  if (isnan(v) || v < 0) return 0;
  if (v > 65535.0f) return 65535;
  return (uint16_t)(v + 0.5f);
}

// TinyGPS raw degrees -> degrees * 1e7 as int32 (full precision; AVR 'double' is only 32-bit)
int32_t rawToE7(const RawDegrees &d) {
  int32_t v = (int32_t)d.deg * 10000000L + (int32_t)(d.billionths / 100UL);
  return d.negative ? -v : v;
}

void print2(uint8_t v) {
  if (v < 10) Serial.print('0');
  Serial.print(v);
}

void printE7(int32_t v) {
  if (v < 0) { Serial.print('-'); v = -v; }
  Serial.print(v / 10000000L);
  Serial.print('.');
  uint32_t frac = v % 10000000L;
  for (uint32_t d = 1000000UL; d > 1 && frac < d; d /= 10) Serial.print('0');
  Serial.print(frac);
}

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println(F("\n=============================================="));
  Serial.println(F(" Arduino UNO GPS + Piezo + Flow Transmitter"));
  Serial.println(F(" Piezo A0/A1 | Flow D2/D3 | GPS D4 | NRF CE D7 CSN D8"));
  Serial.println(F("=============================================="));

  // Flow sensor inputs (YF-S201)
  pinMode(PIN_FLOW_IN,  INPUT_PULLUP);
  pinMode(PIN_FLOW_OUT, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_IN),  inletISR,  FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_OUT), outletISR, FALLING);
  flowPrevMillis = millis();

  // GPS (SoftwareSerial)
  gpsSerial.begin(GPS_BAUD);
  Serial.println(F("[GPS] SoftwareSerial started on D4 (RX), 9600 baud"));

  // NRF24L01
  if (!radio.begin()) {
    Serial.println(F("[NRF24] ERROR: NRF24 NOT DETECTED! Check wiring and 3.3V supply."));
  } else {
    radio.setChannel(76);
    radio.setDataRate(RF24_250KBPS);
    radio.setPALevel(RF24_PA_HIGH);
    radio.enableAckPayload();
    radio.enableDynamicPayloads();
    radio.setAutoAck(true);
    radio.setRetries(5, 15);
    radio.openWritingPipe(radioAddress);
    radio.stopListening();
    Serial.println(F("[NRF24] Initialized: Channel 76 (2476 MHz) | 250KBPS | PA_HIGH"));
  }

  Serial.print(F("[BOOT] Packet size: "));
  Serial.print(sizeof(SensorPacket));
  Serial.println(F(" bytes\n"));
}

// ─── Main Loop ────────────────────────────────────────────────────────────────
void loop() {
  while (gpsSerial.available()) gps.encode(gpsSerial.read());
  updateFlow();
  checkTransientTrigger();

  static unsigned long lastCycle = 0;
  const unsigned long cycleInterval = 2000; // transmit every 2 s

  if (millis() - lastCycle < cycleInterval) return;
  lastCycle = millis();
  seqCounter++;

  // 1. Vibration sampling & TDOA burst sampling. SoftwareSerial interrupts would ruin
  //    sample timing, so GPS listening is paused during both captures (~0.4 s total).
  gpsSerial.stopListening();
  VibResult vib = captureVibration();
  TdoaPacket tdoaPkt;
  if (hasPendingTdoa) {
    tdoaPkt = pendingTdoaPkt;
    hasPendingTdoa = false;
  } else {
    tdoaPkt = captureTdoaBurst(false); // Periodic diagnostic burst (is_transient = 0)
  }
  gpsSerial.listen();
  updateFlow();

  // 2. Build packet
  bool locOk  = gps.location.isValid();
  bool timeOk = gps.time.isValid() && gps.date.isValid();

  SensorPacket pkt;
  memset(&pkt, 0, sizeof(pkt));

  pkt.node_id_num = NODE_ID_NUM;
  pkt.sequence    = seqCounter;
  pkt.lat_e7      = locOk ? rawToE7(gps.location.rawLat()) : 0;
  pkt.lng_e7      = locOk ? rawToE7(gps.location.rawLng()) : 0;
  pkt.satellites  = gps.satellites.isValid() ? (uint8_t)gps.satellites.value() : 0;

  if (gps.hdop.isValid()) {
    int32_t h = gps.hdop.value() / 10;   // value() is HDOP * 100
    pkt.hdop_x10 = (h > 255) ? 255 : (uint8_t)h;
  } else {
    pkt.hdop_x10 = 255;
  }

  if (timeOk) {
    pkt.year_2000 = (uint8_t)(gps.date.year() - 2000);
    pkt.month     = gps.date.month();
    pkt.day       = gps.date.day();
    pkt.hour      = gps.time.hour();
    pkt.minute    = gps.time.minute();
    pkt.second    = gps.time.second();
  }

  pkt.flow_in_x100  = clampU16(flowInLpm  * 100.0f);
  pkt.flow_out_x100 = clampU16(flowOutLpm * 100.0f);
  pkt.rms1_x10      = clampU16(vib.rms1 * 10.0f);
  pkt.rms2_x10      = clampU16(vib.rms2 * 10.0f);
  pkt.p2p1          = vib.p2p1;
  pkt.p2p2          = vib.p2p2;

  uint8_t flags = 0;
  if (locOk)                   flags |= 0x01; // bit0 = GPS location valid
  if (vib.clip1 > POINTS / 20) flags |= 0x02;
  if (vib.clip2 > POINTS / 20) flags |= 0x04;
  if (leakAlarm)               flags |= 0x08;
  if (!vib.valid)              flags |= 0x10;
  pkt.flags = flags;

  // 3. Transmit SensorPacket (32 bytes)
  bool ok = radio.write(&pkt, sizeof(pkt));

  // Discard any ack payload so the RX FIFO never fills up
  while (radio.isAckPayloadAvailable()) {
    uint8_t dummy[32];
    radio.read(&dummy, radio.getDynamicPayloadSize());
  }

  // 3b. Transmit TDOA Localization Packet (24 bytes)
  bool tdoaOk = radio.write(&tdoaPkt, sizeof(tdoaPkt));
  while (radio.isAckPayloadAvailable()) {
    uint8_t dummy[32];
    radio.read(&dummy, radio.getDynamicPayloadSize());
  }

  // 4. Serial log
  Serial.print(F("[TX #")); Serial.print(seqCounter); Serial.print(F("] "));
  if (flags & 0x01) {
    Serial.print(2000 + pkt.year_2000); Serial.print('-');
    print2(pkt.month);  Serial.print('-');
    print2(pkt.day);    Serial.print(' ');
    print2(pkt.hour);   Serial.print(':');
    print2(pkt.minute); Serial.print(':');
    print2(pkt.second);
    Serial.print(F(" UTC | Lat=")); printE7(pkt.lat_e7);
    Serial.print(F(" Lng="));       printE7(pkt.lng_e7);
    Serial.print(F(" | Sats="));    Serial.print(pkt.satellites);
  } else {
    Serial.print(F("No GPS fix | Sats=")); Serial.print(pkt.satellites);
    Serial.print(F(" Chars="));            Serial.print(gps.charsProcessed());
  }
  Serial.print(F(" | Flow in=")); Serial.print(flowInLpm, 2);
  Serial.print(F(" out="));       Serial.print(flowOutLpm, 2);
  Serial.print(F(" L/min"));
  if (leakAlarm) Serial.print(F(" [LEAK ALARM]"));
  Serial.print(F(" | Piezo1 RMS=")); Serial.print(vib.rms1, 1);
  Serial.print(F(" P2P="));         Serial.print(vib.p2p1);
  Serial.print(F(" | Piezo2 RMS=")); Serial.print(vib.rms2, 1);
  Serial.print(F(" P2P="));         Serial.print(vib.p2p2);
  if (!vib.valid) Serial.print(F(" [VIB INVALID]"));
  if (tdoaPkt.flags & 0x01) {
    Serial.print(F(" | TDOA: S1="));
    Serial.print((float)tdoaPkt.est_dist_mm / 1000.0f, 2);
    Serial.print(F("m dt=")); Serial.print(tdoaPkt.delta_t_us);
    Serial.print(F("us R=")); Serial.print((float)tdoaPkt.corr_peak_x100 / 100.0f, 2);
  } else {
    Serial.print(F(" | TDOA: UNAVAIL(Fail="));
    Serial.print(tdoaPkt.failure_code);
    Serial.print(F(")"));
  }
  Serial.print(F(" | NRF: "));
  Serial.println((ok && tdoaOk) ? F("SUCCESS") : (ok ? F("SENSOR_OK_TDOA_FAIL") : F("FAILED (No ACK)")));
}
