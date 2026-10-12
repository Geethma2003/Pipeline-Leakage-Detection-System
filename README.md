# ESP32 Pipeline Leakage Detection System & AquaGuard AI Web SaaS

A robust, DSP-driven, experimentally testable pipeline leakage monitoring and acoustic vibration analysis system for ESP32 microcontrollers paired with a modern real-time industrial IoT web application connected to Firebase Cloud Firestore.

Designed specifically to solve false alarm issues, acoustic attenuation anomalies, transient spike misclassifications, and safe analog signal conditioning on steel water pipelines.

---

## AquaGuard AI — Real-Time Industrial IoT Web Application

AquaGuard AI is a full-stack real-time web application suitable for university embedded systems and IoT demonstrations.

### Tech Stack
- **Frontend**: React 19, Vite, TypeScript, Tailwind CSS v4, Recharts, Lucide Icons, Framer Motion, React Router
- **Backend**: Python FastAPI, WebSockets, PySerial, SQLite3, Firebase Admin SDK (Cloud Firestore), Pandas, NumPy, Pydantic
- **Testing**: Pytest (20 unit and integration tests)

---

## ☁️ Firebase Cloud Firestore Integration (`aquaguard-pipeline`)

The Python backend connects to your Google Firebase Cloud Firestore project **`aquaguard-pipeline`** using the **Firebase Admin SDK**.

### Security & Credential Isolation
- Credentials are handled **EXCLUSIVELY** in the Python backend. Private service account keys are **NEVER** exposed to the React frontend or client browsers.
- Service account JSON keys are ignored by `.gitignore` and never committed to Git repositories.
- Loaded dynamically via environment variables:
  ```cmd
  set FIREBASE_CREDENTIALS_PATH=firebase_service_account.json
  ```

### Firestore Collections & Data Model
1. **`measurements`**: Reduced frequency ESP32 telemetry records (stored once every 5 seconds or immediately when an anomaly spike occurs to protect database write quotas).
2. **`window_reports`**: Completed 60-second vibration analysis reports containing window medians, MAD, abnormal counts, noise variability, TDOA, and decisions.
3. **`sensor_health`**: Real-time hardware connection status, sampling rate (1000 Hz), and dynamic baseline thresholds (`current_status` document).
4. **`leak_events`**: Suspected leak alarms, severity ratings (`CRITICAL`, `HIGH`), and operator confirmation statuses (`UNCONFIRMED`, `ACKNOWLEDGED`, `CONFIRMED_LEAK`, `FALSE_ALARM`).

---

## Running the Web Application on Windows

### 1. Set Environment Variables & Start FastAPI Backend
In a terminal at the project root (`d:\pipeline`):
```cmd
set FIREBASE_CREDENTIALS_PATH=firebase_service_account.json
python -m uvicorn app.main:app --reload --port 8000
```
Or set `PYTHONPATH=backend` if executing directly:
```cmd
set PYTHONPATH=backend
python -m uvicorn app.main:app --reload --port 8000
```
- REST API: `http://localhost:8000/api`
- WebSockets: `ws://localhost:8000/ws/telemetry`
- Firebase Status Endpoint: `http://localhost:8000/api/firebase/status`

### 2. Start the React Frontend
In a second terminal:
```cmd
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Web Application Modules (7 Pages)

1. **Page 1: Overview Dashboard (`/`)**
   - Live system state badge: `NORMAL`, `INVESTIGATING ANOMALY`, `POSSIBLE LEAK ALARM`, `SENSOR FAULT`
   - Animated Sensor 1 (@ 0.0m) and Sensor 2 (@ 2.0m) status cards
   - Real-time dual-line vibration RMS chart (Recharts) with threshold overlays
   - 60-second window analysis progress bar & alert metrics
   - Cloud Firestore sync badge (`Firestore: aquaguard-pipeline`)

2. **Page 2: Live Sensor Analytics (`/analytics`)**
   - Detailed time-series graphs for Sensor 1 RMS, Sensor 2 RMS, and Peak-to-Peak amplitude
   - Adjustable time window filters: 1 min, 5 min, 15 min, All History
   - Pause / Resume streaming control
   - Export telemetry data as CSV

3. **Page 3: Interactive Pipeline Monitor (`/pipeline`)**
   - Custom responsive SVG diagram of a 2.0-meter steel water pipeline
   - Sensor 1 @ 0.0m and Sensor 2 @ 2.0m clickable nodes
   - Animated water pump impeller & fluid flow waves
   - Acoustic vibration waves on anomaly
   - Honest acoustic localization display: Displays distance estimate ONLY when cross-correlation peak coefficient $R \ge 0.65$; otherwise states *"Leak location not verified"*.

4. **Page 4: 60-Second Leak Detection Workflow (`/detection`)**
   - 60-second window collection progress (0 to 60s)
   - Final classification badge & step-by-step decision reasoning audit
   - Feature comparison table (RMS Median, Abnormal Seconds Count, Max Consecutive Run Length, Noise Variability Ratio)
   - Scientific uncertainty disclosure notice

5. **Page 5: Historical Events (`/history`)**
   - Searchable and filterable anomaly event log persisted in SQLite database (`aquaguard.db`) and Firebase Cloud Firestore (`leak_events`)
   - Operator confirmation actions: *Acknowledge*, *Confirm Leak*, or *Mark False Alarm*
   - Export complete history to CSV

6. **Page 6: Experimental Data Analysis (`/experiments`)**
   - Statistical comparison matrix comparing `exp_normal.csv`, `exp_pump_disturbance.csv`, `exp_confirmed_leak.csv`, and real logged datasets
   - Multi-panel time-series comparison plots
   - CSV dataset uploader for custom experimental files
   - Clear type tags: `SIMULATED` vs `REAL LOGGED`

7. **Page 7: Settings & Hardware (`/settings`)**
   - ESP32 USB Serial port scanner and connection controls (Baud rate 115200)
   - Serial port single-owner constraint notice & error handling (explaining exclusive port access)
   - Baseline Recalibration control (Sending `'B'` command) with mandatory safety confirmation checkbox requiring user to verify that pump is running normally and NO leak is present
   - Configurable Persistence Parameter (Sending `'P 42'` command)
   - Physical pipe specifications display (2.0m length)

---

## Hardware Architecture & Conditioning Circuit

### Pin Mapping
- **Microcontroller**: ESP32 Dev Module (3.3V Logic)
- **Sensor 1 Input**: GPIO 34 (ADC1_CH6, Input-Only Pin)
- **Sensor 2 Input**: GPIO 35 (ADC1_CH7, Input-Only Pin)
- **Transducers**: Two Piezoelectric Vibration Sensors
- **Pipeline Setup**: 2.0 Meter Steel Water Pipeline with active inline pump
- **Serial Interface**: 115200 Baud

---

## Running Automated Test Suite

Run pytest across decision logic, backend REST endpoints, and Firebase integration tests:
```bash
python -m pytest tests/ -v
```

---

## Demo Mode vs Live Hardware Mode

When hardware is disconnected, the web app automatically defaults to **DEMO MODE**.
- Prominent banner clearly labels all data as synthetic time-series simulation
- Scenario selector allows testing 3 scenarios:
  1. **Normal State**: Baseline steady vibration
  2. **Pump Disturbance**: Variable pump speed and transient spikes
  3. **Sustained Anomaly**: Sensor 1 20x sustained vibration elevation
- In Live Mode, raw ESP32 measurements stream directly from the USB serial interface without synthetic substitution.
