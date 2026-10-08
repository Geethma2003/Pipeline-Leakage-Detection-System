# IoT-Based Pipeline Leakage Detection & Localization System

An intelligent, IoT-driven monitoring system designed to detect, verify, and precisely localize pipeline leaks in real-time. By combining dual vibration sensors with a flow sensor, the system eliminates false positives (such as routine pump station flow drops) while accurately pinpointing the distance of a leak relative to sensor nodes.

---

## 🚀 Key Features

* **Dual-Vibration Localization:** Utilizes two vibration sensors allocated on either side of a monitored zone to capture abnormal impact signatures and calculate exact leak distances using differential arrival logic.
* **Smart False-Positive Filtering:** Integrates a flow sensor to cross-verify anomalies. A flow drop without a corresponding abnormal vibration spike (e.g., normal pump station adjustments) is ignored, preventing false alarms.
* **Universal Pipeline Support:** Mechanism adapts seamlessly across linear pipes, slot pipelines, and complex bendings.
* **Interactive Monitoring Web Application:** 
  * Real-time visual representation of the pipeline network and sensor layouts.
  * Live alert system displaying exact leak coordinates and distances from each sensor node.
  * Dynamic graph plots tracking live vibration values and flow rates for deep diagnostics.

---

## 📐 System Architecture & Logic
