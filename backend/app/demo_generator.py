"""
AquaGuard AI Demo Mode Data Generator
====================================
Generates realistic synthetic telemetry streams for demonstration when hardware is disconnected.
Supports 3 selectable scenarios:
- 'normal': Steady pipeline operation with baseline vibration
- 'pump_disturbance': Variable pump speed & transient impulse spikes
- 'confirmed_leak': Sustained micro-leak on Sensor 1 (20x elevation)
"""
import random
import time
import math
import datetime
from app.models import TelemetryRecord, HighResLocalizationModel, FlowTelemetryModel, WirelessTelemetryModel



class DemoGenerator:
    def __init__(self):
        self.scenario = "normal"  # "normal", "pump_disturbance", "confirmed_leak"
        self.second_index = 0
        self.esp32_ms = 0

    def set_scenario(self, scenario: str):
        if scenario in ["normal", "pump_disturbance", "confirmed_leak"]:
            self.scenario = scenario
            print(f"[DEMO] Switched scenario to '{scenario}'")

    def generate_next_second(self, s1_thresh: float = 25.0, s2_thresh: float = 24.0) -> TelemetryRecord:
        self.second_index += 1
        self.esp32_ms += 1000

        now_str = datetime.datetime.now().isoformat()
        sec_in_window = self.second_index % 60

        if self.scenario == "normal":
            s1_rms = round(random.gauss(12.0, 1.2), 2)
            s2_rms = round(random.gauss(11.5, 1.1), 2)
            s1_rms = max(5.0, s1_rms)
            s2_rms = max(5.0, s2_rms)

            s1_p2p = round(s1_rms * 2.8 + random.gauss(0, 1.5), 1)
            s2_p2p = round(s2_rms * 2.8 + random.gauss(0, 1.5), 1)

            s1_var = round(s1_rms ** 2, 2)
            s2_var = round(s2_rms ** 2, 2)

            s1_stvar = round(s1_rms * 0.4 + random.uniform(0, 0.5), 2)
            s2_stvar = round(s2_rms * 0.4 + random.uniform(0, 0.5), 2)

            is_transient = 0
            status_str = "PRELIM_NORMAL"

        elif self.scenario == "pump_disturbance":
            # High variance between sec 15..45, plus random spikes
            if 15 <= sec_in_window <= 45:
                s1_rms = round(random.uniform(20.0, 55.0), 2)
                s2_rms = round(random.uniform(18.0, 48.0), 2)
            else:
                s1_rms = round(random.gauss(12.0, 1.5), 2)
                s2_rms = round(random.gauss(11.5, 1.5), 2)

            # Random impulse spikes
            is_transient = 1 if (sec_in_window in [10, 25, 40] or random.random() < 0.1) else 0
            if is_transient:
                s1_rms += round(random.uniform(40.0, 80.0), 2)

            s1_rms = max(5.0, s1_rms)
            s2_rms = max(5.0, s2_rms)

            s1_p2p = round(s1_rms * 3.6 + random.gauss(0, 4.0), 1)
            s2_p2p = round(s2_rms * 3.6 + random.gauss(0, 4.0), 1)

            s1_var = round(s1_rms ** 2, 2)
            s2_var = round(s2_rms ** 2, 2)

            s1_stvar = round(s1_rms * 0.7 + random.uniform(0, 1.2), 2)
            s2_stvar = round(s2_rms * 0.7 + random.uniform(0, 1.2), 2)

            status_str = "PRELIM_TRANSIENT" if is_transient else ("PRELIM_ABNORMAL" if (s1_rms > s1_thresh or s2_rms > s2_thresh) else "PRELIM_NORMAL")

        elif self.scenario == "confirmed_leak":
            # Sensor 1 sustained 20x elevation (220-250 RMS counts)
            # Sensor 2 slight attenuation elevation (18-22 RMS counts)
            if sec_in_window >= 5:  # Sustained throughout window
                s1_rms = round(random.gauss(240.0, 8.0), 2)
                s2_rms = round(random.gauss(18.5, 2.0), 2)
            else:
                s1_rms = round(random.gauss(12.0, 1.2), 2)
                s2_rms = round(random.gauss(11.5, 1.1), 2)

            s1_p2p = round(s1_rms * 2.9 + random.gauss(0, 3.0), 1)
            s2_p2p = round(s2_rms * 2.8 + random.gauss(0, 2.0), 1)

            s1_var = round(s1_rms ** 2, 2)
            s2_var = round(s2_rms ** 2, 2)

            s1_stvar = round(s1_rms * 0.35 + random.uniform(0, 0.4), 2)
            s2_stvar = round(s2_rms * 0.4 + random.uniform(0, 0.4), 2)

            is_transient = 0
            status_str = "PRELIM_ABNORMAL" if (s1_rms > s1_thresh or s2_rms > s2_thresh) else "PRELIM_NORMAL"

        s1_abnormal = 1 if s1_rms > s1_thresh else 0
        s2_abnormal = 1 if s2_rms > s2_thresh else 0

        return TelemetryRecord(
            pc_timestamp=now_str,
            esp32_ms=self.esp32_ms,
            second_index=self.second_index,
            s1_rms=s1_rms,
            s1_p2p=s1_p2p,
            s1_variance=s1_var,
            s1_stvar=s1_stvar,
            s2_rms=s2_rms,
            s2_p2p=s2_p2p,
            s2_variance=s2_var,
            s2_stvar=s2_stvar,
            s1_abnormal=s1_abnormal,
            s2_abnormal=s2_abnormal,
            is_transient=is_transient,
            status_str=status_str,
            is_demo=True
        )

    def generate_localization(self) -> HighResLocalizationModel:
        now_ts = time.time()
        fs = 10000
        v_mps = 1250.0
        pipe_len = 2.0

        if self.scenario == "confirmed_leak":
            # Sustained leak located at 0.65m from Sensor 1 (1.35m from Sensor 2)
            d1_actual = 0.65 + random.gauss(0, 0.01)
            d1_actual = max(0.05, min(1.95, d1_actual))
            d2_actual = round(pipe_len - d1_actual, 2)
            d1_actual = round(d1_actual, 2)

            # delta_t = (L - 2*d1)/v
            delta_t_sec = (pipe_len - 2.0 * d1_actual) / v_mps
            delta_t_us = round(delta_t_sec * 1e6, 1)

            peak_corr = round(min(0.96, max(0.78, random.gauss(0.88, 0.03))), 3)
            psr = round(min(6.5, max(3.0, random.gauss(4.2, 0.4))), 2)

            # Synthetic dual-channel acoustic burst waveform (50 sample points)
            # Sample interval = 100 us. delta_t = 560 us is ~5.6 samples.
            delay_samples = delta_t_sec * fs
            s1_wave = []
            s2_wave = []
            center_idx = 20.0
            for i in range(50):
                # Sensor 1 packet
                env1 = math.exp(-((i - center_idx) / 6.0) ** 2)
                carrier1 = math.sin(2 * math.pi * 0.12 * (i - center_idx))
                val1 = round(env1 * carrier1 * 180.0 + random.gauss(0, 8.0), 1)
                s1_wave.append(val1)

                # Sensor 2 packet (delayed by delay_samples and attenuated by pipe travel)
                i_delayed = i - delay_samples
                env2 = math.exp(-((i_delayed - center_idx) / 6.0) ** 2)
                carrier2 = math.sin(2 * math.pi * 0.12 * (i_delayed - center_idx))
                val2 = round(env2 * carrier2 * 125.0 + random.gauss(0, 8.0), 1)
                s2_wave.append(val2)

            uncertainty = round(max(0.15, (1.0 - peak_corr) * 0.6), 3)

            return HighResLocalizationModel(
                pipe_length_m=pipe_len,
                s1_pos_m=0.0,
                s2_pos_m=pipe_len,
                delta_t_us=delta_t_us,
                sample_rate_hz=fs,
                propagation_velocity_mps=v_mps,
                propagation_velocity_status="NOMINAL_UNCALIBRATED",
                leak_distance_s1_m=d1_actual,
                leak_distance_s2_m=d2_actual,
                confidence_pct=round(peak_corr * 100.0, 1),
                uncertainty_m=uncertainty,
                correlation_peak=peak_corr,
                psr=psr,
                status="LEAK CONFIRMED BY FLOW — LOCALIZATION REVEALED",
                loc_valid=True,
                flow_confirmed_leak=True,
                leak_location_revealed=True,
                s1_waveform=s1_wave,
                s2_waveform=s2_wave,
                last_updated=now_ts
            )

        else:
            # Baseline normal or pump disturbance: diffuse noise, no coherent cross-correlation
            s1_wave = [round(random.gauss(0, 12.0), 1) for _ in range(50)]
            s2_wave = [round(random.gauss(0, 12.0), 1) for _ in range(50)]
            peak_corr = round(random.uniform(0.12, 0.35), 3)
            psr = round(random.uniform(1.0, 1.6), 2)

            return HighResLocalizationModel(
                pipe_length_m=pipe_len,
                s1_pos_m=0.0,
                s2_pos_m=pipe_len,
                delta_t_us=round(random.uniform(-400.0, 400.0), 1),
                sample_rate_hz=fs,
                propagation_velocity_mps=v_mps,
                leak_distance_s1_m=None,
                leak_distance_s2_m=None,
                confidence_pct=0.0,
                uncertainty_m=0.25,
                correlation_peak=peak_corr,
                psr=psr,
                status="LOCATION CONCEALED — AWAITING FLOW CONFIRMATION",
                loc_valid=False,
                flow_confirmed_leak=False,
                leak_location_revealed=False,
                s1_waveform=s1_wave,
                s2_waveform=s2_wave,
                last_updated=now_ts
            )

    def generate_flow(self) -> FlowTelemetryModel:
        now_ts = time.time()
        if self.scenario == "confirmed_leak":
            flow_in = round(2.85 + random.gauss(0, 0.03), 3)
            flow_out = round(2.45 + random.gauss(0, 0.03), 3)
            diff = round(flow_in - flow_out, 3)
            in_p = int(flow_in * 450.0 * 5.0 / 60.0)
            out_p = int(flow_out * 450.0 * 5.0 / 60.0)
            return FlowTelemetryModel(
                esp32_ms=self.esp32_ms,
                interval_ms=5000,
                in_pulses=in_p,
                out_pulses=out_p,
                flow_in_lpm=flow_in,
                flow_out_lpm=flow_out,
                flow_diff_lpm=diff,
                leak_progress=3,
                leak_confirmed=True,
                status="LEAK_CONFIRMED",
                last_updated=now_ts
            )
        elif self.scenario == "pump_disturbance":
            flow_in = round(3.20 + random.gauss(0, 0.05), 3)
            flow_out = round(3.18 + random.gauss(0, 0.05), 3)
            diff = round(flow_in - flow_out, 3)
            in_p = int(flow_in * 450.0 * 5.0 / 60.0)
            out_p = int(flow_out * 450.0 * 5.0 / 60.0)
            return FlowTelemetryModel(
                esp32_ms=self.esp32_ms,
                interval_ms=5000,
                in_pulses=in_p,
                out_pulses=out_p,
                flow_in_lpm=flow_in,
                flow_out_lpm=flow_out,
                flow_diff_lpm=diff,
                leak_progress=0,
                leak_confirmed=False,
                status="NO_LEAK",
                last_updated=now_ts
            )
        else:
            flow_in = round(2.45 + random.gauss(0, 0.03), 3)
            flow_out = round(2.44 + random.gauss(0, 0.03), 3)
            diff = round(flow_in - flow_out, 3)
            in_p = int(flow_in * 450.0 * 5.0 / 60.0)
            out_p = int(flow_out * 450.0 * 5.0 / 60.0)
            return FlowTelemetryModel(
                esp32_ms=self.esp32_ms,
                interval_ms=5000,
                in_pulses=in_p,
                out_pulses=out_p,
                flow_in_lpm=flow_in,
                flow_out_lpm=flow_out,
                flow_diff_lpm=diff,
                leak_progress=0,
                leak_confirmed=False,
                status="NO_LEAK",
                last_updated=now_ts
            )

    def generate_wireless(self) -> WirelessTelemetryModel:
        now_ts = time.time()
        now_iso = datetime.datetime.now().isoformat()
        if self.scenario == "confirmed_leak":
            return WirelessTelemetryModel(
                utc_timestamp=now_iso,
                node_id=1,
                packet_sequence=self.second_index,
                flow_in_lpm=17.92,
                flow_out_lpm=14.75,
                flow_diff_lpm=3.17,
                leak_alarm=True,
                rms1=0.6,
                p2p1=4,
                rms2=0.6,
                p2p2=4,
                s1_clipped=False,
                s2_clipped=False,
                vibration_invalid=False,
                gps_valid=False,
                latitude=None,
                longitude=None,
                satellites=0,
                hdop=25.5,
                gps_time=None,
                missed_packets=0,
                sequence_reset=0,
                communication_source="ARDUINO_UNO_NRF24",
                status_str="LEAK_CONFIRMED",
                is_demo=True,
                last_updated=now_ts
            )
        elif self.scenario == "pump_disturbance":
            return WirelessTelemetryModel(
                utc_timestamp=now_iso,
                node_id=1,
                packet_sequence=self.second_index,
                flow_in_lpm=15.20,
                flow_out_lpm=15.15,
                flow_diff_lpm=0.05,
                leak_alarm=False,
                rms1=2.4,
                p2p1=14,
                rms2=2.1,
                p2p2=12,
                s1_clipped=False,
                s2_clipped=False,
                vibration_invalid=False,
                gps_valid=False,
                latitude=None,
                longitude=None,
                satellites=0,
                hdop=25.5,
                gps_time=None,
                missed_packets=0,
                sequence_reset=0,
                communication_source="ARDUINO_UNO_NRF24",
                status_str="NO_LEAK",
                is_demo=True,
                last_updated=now_ts
            )
        else:
            return WirelessTelemetryModel(
                utc_timestamp=now_iso,
                node_id=1,
                packet_sequence=self.second_index,
                flow_in_lpm=16.50,
                flow_out_lpm=16.48,
                flow_diff_lpm=0.02,
                leak_alarm=False,
                rms1=0.6,
                p2p1=4,
                rms2=0.6,
                p2p2=4,
                s1_clipped=False,
                s2_clipped=False,
                vibration_invalid=False,
                gps_valid=False,
                latitude=None,
                longitude=None,
                satellites=0,
                hdop=25.5,
                gps_time=None,
                missed_packets=0,
                sequence_reset=0,
                communication_source="ARDUINO_UNO_NRF24",
                status_str="NO_LEAK",
                is_demo=True,
                last_updated=now_ts
            )

