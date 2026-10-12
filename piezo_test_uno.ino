
const byte FLOW_IN_PIN = 2;
const byte FLOW_OUT_PIN = 3;

// Replace these with measured calibration values
const float K_IN = 450.0; 
const float K_OUT = 450.0; 

const unsigned long WINDOW_MS = 5000;

// Leak threshold: 0.3 litres per minute
const float LEAK_THRESHOLD_LPM = 0.10;

// Require 3 consecutive windows (about 15 seconds)
const byte CONFIRM_WINDOWS = 3;

volatile unsigned long inletPulses = 0;
volatile unsigned long outletPulses = 0;

unsigned long previousMillis = 0;
byte leakCount = 0;
byte normalCount = 0;
bool leakAlarm = false;

void inletISR() {
  inletPulses++;
}

void outletISR() {
  outletPulses++;
}

void setup() {
  Serial.begin(9600);

  pinMode(FLOW_IN_PIN, INPUT_PULLUP);
  pinMode(FLOW_OUT_PIN, INPUT_PULLUP);

  attachInterrupt(
    digitalPinToInterrupt(FLOW_IN_PIN),
    inletISR, FALLING
  );

  attachInterrupt(
    digitalPinToInterrupt(FLOW_OUT_PIN),
    outletISR, FALLING
  );

  previousMillis = millis();

  Serial.println("Water Leakage Detection System");
  Serial.println("Monitoring flow...");
}

void loop() {
  unsigned long now = millis();
  unsigned long elapsed = now - previousMillis;

  if (elapsed < WINDOW_MS) {
    return;
  }

  previousMillis = now;

  noInterrupts();
  unsigned long pIn = inletPulses;
  unsigned long pOut = outletPulses;
  inletPulses = 0;
  outletPulses = 0;
  interrupts();

  float flowIn =
    (pIn * 60000.0) / (K_IN * elapsed);

  float flowOut =
    (pOut * 60000.0) / (K_OUT * elapsed);

  float difference = flowIn - flowOut;

  Serial.println("----------------------");

  Serial.print("Inlet: ");
  Serial.print(flowIn, 3);
  Serial.println(" L/min");

  Serial.print("Outlet: ");
  Serial.print(flowOut, 3);
  Serial.println(" L/min");

  Serial.print("Difference: ");
  Serial.print(difference, 3);
  Serial.println(" L/min");

  // Do not assess a leak when no water is flowing
  if (flowIn < 0.5) {
    leakCount = 0;
    normalCount = 0;
    leakAlarm = false;

    Serial.println("Low flow: monitoring only.");
    return;
  }

  if (difference >= LEAK_THRESHOLD_LPM) {
    if (leakCount < CONFIRM_WINDOWS) {
      leakCount++;
    }

    normalCount = 0;

    Serial.print("Leak confirmation: ");
    Serial.print(leakCount);
    Serial.print("/");
    Serial.println(CONFIRM_WINDOWS);

    if (leakCount >= CONFIRM_WINDOWS) {
      leakAlarm = true;
    }
  } else {
    leakCount = 0;

    if (normalCount < CONFIRM_WINDOWS) {
      normalCount++;
    }

    if (normalCount >= CONFIRM_WINDOWS) {
      leakAlarm = false;
    }
  }

  if (leakAlarm) {
    Serial.println("!!! WARNING: POSSIBLE WATER LEAK !!!");
  } else {
    Serial.println("Status: No confirmed leak");
  }
}
