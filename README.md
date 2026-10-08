# ESP32 Pipeline Leakage Detection System

A robust, DSP-driven, experimentally testable pipeline leakage monitoring and acoustic vibration analysis system for ESP32 microcontrollers. 

Designed specifically to solve false alarm issues, acoustic attenuation anomalies, transient spike misclassifications, and safe analog signal conditioning on steel water pipelines.

---

## Hardware Architecture & Conditioning Circuit

### Pin Mapping
- **Microcontroller**: ESP32 Dev Module (3.3V Logic)
- **Sensor 1 Input**: GPIO 34 (ADC1_CH6, Input-Only Pin)
- **Sensor 2 Input**: GPIO 35 (ADC1_CH7, Input-Only Pin)
- **Transducers**: Two Piezoelectric Vibration Sensors
- **Pipeline Setup**: 2.0 Meter Steel Water Pipeline with active inline pump
- **Serial Interface**: 115200 Baud

> **CRITICAL ADC PROTECTION NOTE**: Raw piezoelectric elements generate voltage spikes (±10V to ±50V when mechanically shocked) and negative voltages relative to ground. Connecting raw piezo discs directly to ESP32 GPIO 34/35 WILL clip signals, cause non-linear ADC distortion, and permanently destroy the ESP32 ADC input protection.

### Mandatory Signal Conditioning Circuit Schematic

Connect the conditioning circuit below between each piezo sensor and the ESP32 ADC pin:

```
        3.3V Rail
           │
          ┌┴┐ R1 (100kΩ)
          └┬┘
           ├───────┬───────────────────────────┐
          ┌┴┐ R2   │ C_bias (10µF)             │
          └┬┘(100k)│                           │
           │      ─┴─                          │
          GND     ───                          │
                   │                           │
                  GND                   V_REF (~1.65V Bias)
                                               │
                                               │
  PIEZO SENSOR                                 │
┌──────────────┐     C_ac (0.1µF)              │
│              ├───────┤├───┬──────────────────┼────────┬───────────────┐
│  (+) SIGNAL  │            │                  │        │               │
│              │           ┌┴┐ R_in (1MΩ)     ┌┴┐ D1   ┌┴┐ D2           │
└──────┬───────┘           └┬┘                └┬┘BAT54S└┬┘(Schottky)   ┌┴┐ R_lp (10kΩ)
       │                    │                 ─┴─ Clamps│              └┬┘
       │                   GND                 ▲        │               │
       │                                       ├────────┘               ├───► GPIO 34/35 (ESP32 ADC)
       │                                       │                        │
       │                                       │                       ─┴─ C_lp (10nF)
       │                                       ▼                        ─── Anti-Aliasing (fc=1.59kHz)
       │                                      3.3V                      │
       └────────────────────────────────────────────────────────────────┴───► GND
```

#### Conditioning Components Rationale:
1. **DC Bias Divider ($R_1 = 100\text{ k}\Omega, R_2 = 100\text{ k}\Omega, C_{\text{bias}} = 10\,\mu\text{F}$)**: Establishes a quiet $V_{\text{ref}} \approx 1.65\text{V}$ mid-rail offset so AC vibration swings are centered within the 0.0V–3.3V ESP32 ADC range.
2. **AC Coupling ($C_{\text{ac}} = 0.1\,\mu\text{F}, R_{\text{in}} = 1\text{ M}\Omega$)**: High-pass filter ($f_c \approx 1.6\text{ Hz}$) that removes DC offsets and prevents static charge build-up on the ceramic element.
3. **Schottky Clamp Diodes ($D_1, D_2$ BAT54S)**: Clamps high transient voltage spikes to $-0.3\text{V} \le V_{\text{pin}} \le 3.6\text{V}$, shielding the ESP32 input stage.
4. **Anti-Aliasing Low-Pass Filter ($R_{\text{lp}} = 10\text{ k}\Omega, C_{\text{lp}} = 10\text{ nF}$)**: Low-pass filter ($f_c = 1.59\text{ kHz}$) suppressing high-frequency electromagnetic noise above the Nyquist rate for $1000\text{ Hz}$ sampling.

---

## DSP Algorithm & Decision Engine Architecture

Earlier programs gave false alarms or reported NORMAL during real leakage due to two main mistakes:
1. **Relying on single-sample spikes**: Mechanical taps or valve movements caused momentary RMS spikes.
2. **Requiring both sensors to show abnormal vibration**: Because acoustic waves attenuate rapidly along metal pipes (especially near fittings or elbow joints), Sensor 1 can increase **20x or more** while Sensor 2 stays near baseline.

### Primary Design Rules

1. **60-Second Windowed Multi-Criteria Analysis**:
   - The system samples ADC channels at $1000\text{ Hz}$ per channel with microsecond-measured sampling loops.
   - Computes per-second DC-removed RMS, Variance, Peak-to-Peak (P2P), Short-Term Signal Variation (Line Length), Zero Crossing Rate (ZCR), and Crest Factor.
   - Stores 60 consecutive 1-second records in a circular buffer.
   - Evaluates full decisions only after analyzing complete 60-second windows.

2. **Independent Sensor Anomaly Detection (Either-Sensor Rule)**:
   - Evaluates Sensor 1 and Sensor 2 independently against noise-aware baseline thresholds.
   - If Sensor 1 exhibits sustained vibration elevation ($\ge 42/60$ seconds) while Sensor 2 remains baseline, the system correctly flags a **SUSTAINED VIBRATION ANOMALY / POSSIBLE LEAK**.

3. **Noise-Aware Dynamic Thresholding**:
   - Baseline statistics are computed during an initial 60-second NO-LEAK calibration:
     $$T_{\text{rms}} = \max\left(B_{\text{rms\_med}} + 3.5 \times \text{MAD}_{\text{rms}}, \; 2.2 \times B_{\text{rms\_med}}, \; \text{MIN\_FLOOR}\right)$$
   - Uses Median and Median Absolute Deviation (MAD) to ignore outlier noise during baseline setup.

4. **Variability & Transient Spike Filtering**:
   - Computes Noise Variability Ratio ($\sigma / \mu$). High variability ratio ($> 0.48$) indicates pump speed changes or turbulent handling rather than steady broadband leakage noise.
   - Crest Factor $> 7.0$ isolates short impulse spikes (water hammer, dropped tool) from continuous leakage vibration.

5. **Alarm Hysteresis & Baseline Protection**:
   - Baseline parameters **NEVER** adapt while suspected leakage is occurring.
   - Clearing a confirmed alarm back to NORMAL requires **2 consecutive 60-second windows** returning below threshold bounds.

6. **Honest Uncertainty in Localization**:
   - For a 2.0 meter steel pipe with speed of sound $c \approx 1200\text{ m/s}$, max acoustic delay is $\Delta t = 1.67\text{ ms}$.
   - At $1000\text{ Hz}$ sampling rate (1 sample period = $1\text{ ms}$), time delay resolution is coarse.
   - Cross-correlation is performed, but location is ONLY reported if peak correlation coefficient $R_{\max} \ge 0.65$. Otherwise, the report explicitly states **`LOCATION NOT VERIFIED`** rather than outputting misleading coordinates.

---

## File Structure

- [`pipeline_monitor/pipeline_monitor.ino`](file:///d:/pipeline/pipeline_monitor/pipeline_monitor.ino): Complete C++ firmware implementation for ESP32 Arduino framework.
- [`serial_logger.py`](file:///d:/pipeline/serial_logger.py): Python pyserial script to log real-time ESP32 CSV measurements.
- [`analyze_experiments.py`](file:///d:/pipeline/analyze_experiments.py): Python script using Pandas & Matplotlib to generate comparison tables and multi-panel figures.
- [`tests/test_decision_logic.py`](file:///d:/pipeline/tests/test_decision_logic.py): Pytest unit test suite covering 7 physical test scenarios.
- [`requirements.txt`](file:///d:/pipeline/requirements.txt): Python dependencies.

---

## Quick Start & Usage

### 1. Compiling & Uploading Firmware

Using `arduino-cli`:
```bash
arduino-cli compile --fqbn esp32:esp32:esp32 pipeline_monitor
arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32 pipeline_monitor
```

Or open `pipeline_monitor/pipeline_monitor.ino` in the Arduino IDE, select **ESP32 Dev Module**, and click **Upload**.

### 2. Running Real-Time Logger

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Run logger:
```bash
python serial_logger.py --port COM3 --baud 115200 --output leak_test_01.csv
```

### 3. Interactive Serial Commands

Open Serial Monitor at **115200 baud**. Commands (Case-insensitive):
- `H` or `HELP`: Display command menu.
- `B` or `CAL`: Trigger 60-second NO-LEAK baseline recalibration (only when pipeline is leak-free).
- `V` or `VERBOSE`: Toggle 1-second preliminary live diagnostics ON/OFF.
- `M` or `MODE`: Toggle human-readable vs CSV machine format.
- `S` or `STATUS`: Display current baseline calibration & system timing metrics.
- `P <10-60>`: Set persistence requirement threshold (Default: 42 seconds).

### 4. Running Unit Tests

Run the decision logic unit test suite:
```bash
python -m pytest tests/test_decision_logic.py -v
```

### 5. Analyzing Experimental Data & Generating Graphs

Generate comparison graphs and summary statistics from recorded CSV files:
```bash
python analyze_experiments.py --generate-demo
```
This produces `experiment_analysis.png` comparing Normal Baseline vs Pump Disturbance vs Confirmed Leakage.

---

## Threshold Tuning & Diagnostic Guide

| System Classification | Sensor 1 / 2 Status | Noise Variability ($\sigma/\mu$) | Action / Recommended Response |
| :--- | :--- | :--- | :--- |
| **NORMAL** | $< 42$ abn sec | $\le 0.48$ | Pipeline operating within calibrated noise bounds. |
| **TRANSIENT DISTURBANCE** | Spikes or $> 12$ trans sec | $> 0.48$ | Inspect pump speed controller, valve operations, or mechanical tapping. |
| **SUSTAINED ANOMALY / LEAK** | $\ge 42/60$ abn sec | $\le 0.48$ | Sustained vibration elevation detected. Inspect pipeline segment near indicated sensor. |
| **SENSOR / CAL FAULT** | Raw mean $< 400$ or $> 3700$ | N/A | Check wiring, DC bias divider resistors, or piezo sensor connections. |

---

## Alternative Non-Leak Vibration Sources
1. **Pump Speed Changes**: Causes temporary broad-spectrum noise shifts. Identified by high variability ratio ($\sigma/\mu > 0.48$).
2. **Cavitation**: Produces irregular transient burst spikes. Filtered by Crest Factor $> 7.0$.
3. **Fluid Flow Turbulence**: High flow velocity creates elevated baseline noise. Resolved by performing baseline calibration (`'B'`) at normal flow rates.
4. **Mains Electrical Hum (50/60 Hz)**: Prevented by anti-aliasing RC filter and DC bias decoupling capacitor.
