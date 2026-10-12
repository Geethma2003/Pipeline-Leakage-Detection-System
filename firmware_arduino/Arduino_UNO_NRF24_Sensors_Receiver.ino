/*
 * NRF24 Receiver Gateway — GPS + Piezo + Flow packet (Serial Monitor output)
 * Hardware: Arduino UNO (or Nano) + NRF24L01(+PA+LNA)
 *
 * Receives the 32-byte SensorPacket sent by the ESP32-C3 / UNO / Nano
 * "GPS + Sensors" transmitter and prints it on the Serial Monitor.
 *
 * Pin connections (unchanged):
 *   CE   -> D7
 *   CSN  -> D8
 *   SCK  -> D13
 *   MOSI -> D11
 *   MISO -> D12
 *   VCC  -> 3.3V ONLY (10uF capacitor across VCC/GND at the module;
 *           PA+LNA modules need a stable supply, ideally separate 3.3V)
 *   GND  -> GND
 *
 * Serial Monitor: 115200 baud
 */

#include <SPI.h>
#include <RF24.h>
#include <string.h>

#define NRF_CE_PIN  7
#define NRF_CSN_PIN 8
#define RF_CHANNEL  76

const byte radioAddress[6] = "TRN01";

/*
 * Must match the transmitter's SensorPacket exactly (32 bytes).
 * flags: bit0 = gps valid          bit1 = piezo1 clipping
 *        bit2 = piezo2 clipping    bit3 = leak alarm (flow)
 *        bit4 = vibration window invalid
 * Piezo values are in ADC counts: 0-1023 for UNO/Nano transmitters,
 * 0-4095 for the ESP32-C3 transmitter.
 */
struct __attribute__((packed)) SensorPacket {
  uint8_t  node_id_num;
  uint16_t sequence;
  int32_t  lat_e7;
  int32_t  lng_e7;
  uint8_t  satellites;
  uint8_t  hdop_x10;
  uint8_t  flags;
  uint8_t  year_2000;
  uint8_t  month;
  uint8_t  day;
  uint8_t  hour;
  uint8_t  minute;
  uint8_t  second;
  uint16_t flow_in_x100;
  uint16_t flow_out_x100;
  uint16_t rms1_x10;
  uint16_t rms2_x10;
  uint16_t p2p1;
  uint16_t p2p2;
};
static_assert(sizeof(SensorPacket) == 32,
              "SensorPacket must match the transmitter (32 bytes)");

// ─── TDOA Localization Packet (EXACTLY 24 bytes <= 32 bytes) ───────────────────
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
static_assert(sizeof(TdoaPacket) == 24,
              "TdoaPacket must match the transmitter (24 bytes)");

struct __attribute__((packed)) CmdPacket {
  uint8_t cmd_type;
  uint8_t param1;
  uint8_t param2;
  uint8_t reserved[5];
};

RF24 radio(NRF_CE_PIN, NRF_CSN_PIN);
uint32_t receivedCount = 0;
uint32_t missedTotal   = 0;
uint16_t lastSeq       = 0;
bool     haveLastSeq   = false;

// ─── Print helpers ────────────────────────────────────────────────────────────
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

void printX10(uint16_t v) {      // value * 10 -> 1 decimal
  Serial.print(v / 10);
  Serial.print('.');
  Serial.print(v % 10);
}

void printX100(uint16_t v) {     // value * 100 -> 2 decimals
  Serial.print(v / 100);
  Serial.print('.');
  if ((v % 100) < 10) Serial.print('0');
  Serial.print(v % 100);
}

void printPacket(const SensorPacket &pkt) {
  ++receivedCount;

  // Count packets lost between this one and the previous one
  uint16_t missed = 0;
  if (haveLastSeq) {
    missed = (uint16_t)(pkt.sequence - lastSeq - 1);
    missedTotal += missed;
  }
  lastSeq = pkt.sequence;
  haveLastSeq = true;

  Serial.println(F("--------------------------------------"));
  Serial.print(F("Packet #"));  Serial.print(receivedCount);
  Serial.print(F("  (Node "));  Serial.print(pkt.node_id_num);
  Serial.print(F(", Seq "));    Serial.print(pkt.sequence);
  Serial.print(F(", missed since last: ")); Serial.print(missed);
  Serial.print(F(", total missed: "));      Serial.print(missedTotal);
  Serial.println(F(")"));

  // ── GPS ──
  bool gpsOk = pkt.flags & 0x01;
  Serial.print(F("GPS Fix    : "));
  Serial.println(gpsOk ? F("YES") : F("NO (searching for satellites...)"));
  Serial.print(F("Satellites : ")); Serial.println(pkt.satellites);
  Serial.print(F("HDOP       : "));
  if (pkt.hdop_x10 == 255) Serial.println(F("--"));
  else { printX10(pkt.hdop_x10); Serial.println(); }

  if (gpsOk) {
    Serial.print(F("Date (UTC) : "));
    Serial.print(2000 + pkt.year_2000); Serial.print('-');
    print2(pkt.month); Serial.print('-'); print2(pkt.day);
    Serial.println();

    Serial.print(F("Time (UTC) : "));
    print2(pkt.hour); Serial.print(':');
    print2(pkt.minute); Serial.print(':');
    print2(pkt.second);
    Serial.println();

    Serial.print(F("Latitude   : ")); printE7(pkt.lat_e7);  Serial.println();
    Serial.print(F("Longitude  : ")); printE7(pkt.lng_e7);  Serial.println();
  }

  // ── Flow ──
  Serial.print(F("Flow inlet : ")); printX100(pkt.flow_in_x100);  Serial.println(F(" L/min"));
  Serial.print(F("Flow outlet: ")); printX100(pkt.flow_out_x100); Serial.println(F(" L/min"));
  Serial.print(F("Leak alarm : "));
  Serial.println((pkt.flags & 0x08) ? F("YES  <<< POSSIBLE LEAK >>>") : F("no"));

  // ── Piezo ──
  Serial.print(F("Piezo 1    : RMS ")); printX10(pkt.rms1_x10);
  Serial.print(F("  P2P ")); Serial.print(pkt.p2p1);
  if (pkt.flags & 0x02) Serial.print(F("  [CLIPPING]"));
  Serial.println();
  Serial.print(F("Piezo 2    : RMS ")); printX10(pkt.rms2_x10);
  Serial.print(F("  P2P ")); Serial.print(pkt.p2p2);
  if (pkt.flags & 0x04) Serial.print(F("  [CLIPPING]"));
  Serial.println();
  if (pkt.flags & 0x10) Serial.println(F("Vibration window: INVALID (timing overrun / heavy clipping)"));
}

void printTdoaPacket(const TdoaPacket &t) {
  // Machine-readable CSV line for Python SerialManager:
  // TDOA_UNO,node_id,event_id,timestamp_ms,delta_t_us,dist_mm,corr_peak_x100,psr_x10,valid,failure_code,is_transient
  Serial.print(F("TDOA_UNO,"));
  Serial.print(t.node_id); Serial.print(',');
  Serial.print(t.event_id); Serial.print(',');
  Serial.print(t.timestamp_ms); Serial.print(',');
  Serial.print(t.delta_t_us); Serial.print(',');
  Serial.print(t.est_dist_mm); Serial.print(',');
  Serial.print(t.corr_peak_x100); Serial.print(',');
  Serial.print(t.psr_x10); Serial.print(',');
  Serial.print((t.flags & 0x01) ? 1 : 0); Serial.print(',');
  Serial.print(t.failure_code); Serial.print(',');
  Serial.println((t.flags & 0x20) ? 1 : 0);

  // Human-readable diagnostic output
  Serial.print(F("[TDOA #")); Serial.print(t.event_id);
  Serial.print(F("] dt=")); Serial.print(t.delta_t_us);
  Serial.print(F(" us | Dist S1="));
  if (t.flags & 0x01) {
    Serial.print((float)t.est_dist_mm / 1000.0f, 3);
    Serial.print(F(" m"));
  } else {
    Serial.print(F("UNAVAILABLE (Code="));
    Serial.print(t.failure_code);
    Serial.print(F(")"));
  }
  Serial.print(F(" | R=")); Serial.print((float)t.corr_peak_x100 / 100.0f, 2);
  Serial.print(F(" PSR=")); Serial.print((float)t.psr_x10 / 10.0f, 1);
  Serial.println((t.flags & 0x20) ? F(" [TRANSIENT_TRIGGER]") : F(" [PERIODIC]"));
}

void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println(F("=== GPS + Sensors NRF24 Receiver ==="));

  if (!radio.begin()) {
    Serial.println(F("ERROR: NRF24 NOT DETECTED! Check wiring (CE=D7, CSN=D8, 3.3V)."));
    while (true) delay(1000);
  }

  radio.setChannel(RF_CHANNEL);
  radio.setDataRate(RF24_250KBPS);  // Must match transmitter
  radio.setPALevel(RF24_PA_LOW);
  radio.setCRCLength(RF24_CRC_16);
  radio.setPayloadSize(sizeof(SensorPacket));
  radio.enableDynamicPayloads();
  radio.enableAckPayload();
  radio.setAutoAck(true);
  radio.openReadingPipe(1, radioAddress);
  radio.startListening();

  // Queue an empty ACK payload; transmitter can continue using ACK payloads.
  CmdPacket ack;
  memset(&ack, 0, sizeof(ack));
  radio.writeAckPayload(1, &ack, sizeof(ack));

  Serial.println(F("NRF24 ready. Channel 76 (2476 MHz), 250KBPS. Waiting for packets...\n"));
}

void loop() {
  if (radio.available()) {
    uint8_t payloadSize = radio.getDynamicPayloadSize();

    if (payloadSize == sizeof(SensorPacket)) {
      SensorPacket pkt;
      radio.read(&pkt, sizeof(pkt));
      printPacket(pkt);

      CmdPacket ack;
      memset(&ack, 0, sizeof(ack));
      radio.writeAckPayload(1, &ack, sizeof(ack));
    } else if (payloadSize == sizeof(TdoaPacket)) {
      TdoaPacket tdoa;
      radio.read(&tdoa, sizeof(tdoa));
      printTdoaPacket(tdoa);

      CmdPacket ack;
      memset(&ack, 0, sizeof(ack));
      radio.writeAckPayload(1, &ack, sizeof(ack));
    } else {
      // Drain malformed payload so the radio can receive the next packet.
      uint8_t discard[32];
      if (payloadSize == 0 || payloadSize > sizeof(discard)) {
        radio.flush_rx();
      } else {
        radio.read(discard, payloadSize);
      }
      Serial.print(F("Ignored packet with unexpected size: "));
      Serial.println(payloadSize);
    }
  }
}
