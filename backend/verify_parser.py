"""
Arduino Receiver Serial Parser & Offline Log Verifier
======================================================
Robust multiline parser for Arduino Uno nRF24 receiver telemetry.
Parses packets starting with 'Packet #' and extracts:
- Node ID, Sequence, Missed packets
- GPS Fix, Satellites, HDOP, Lat/Lng
- Flow inlet, Flow outlet, Leak alarm
- Piezo 1 RMS/P2P, Piezo 2 RMS/P2P
Rejects fragmented startup text, ignores separators and banners.
"""
import sys
import os
import re
import datetime
from typing import Optional, Dict, Any, List

class ArduinoReceiverParser:
    def __init__(self):
        self.current_packet: Optional[Dict[str, Any]] = None
        self.parsed_packets: List[Dict[str, Any]] = []

    def feed_line(self, line_str: str) -> Optional[Dict[str, Any]]:
        line = line_str.strip()
        if not line:
            return None

        # Clean off log timestamp prefixes like "[22:19:28.164] " if feeding from log file
        line = re.sub(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]\s*", "", line)

        # 1. Start of a new wireless packet
        # Example: Packet #1  (Node 1, Seq 103, missed since last: 0, total missed: 0)
        pkt_header = re.search(
            r"Packet\s*#\s*(\d+)\s*\(\s*Node\s*(\d+),\s*Seq\s*(\d+),\s*missed\s+since\s+last:\s*(\d+),\s*total\s+missed:\s*(\d+)\)",
            line,
            re.IGNORECASE
        )
        if pkt_header:
            self.current_packet = {
                "packet_num": int(pkt_header.group(1)),
                "node_id": int(pkt_header.group(2)),
                "sequence": int(pkt_header.group(3)),
                "missed_since_last": int(pkt_header.group(4)),
                "total_missed": int(pkt_header.group(5)),
                "gps_valid": False,
                "latitude": None,
                "longitude": None,
                "satellites": 0,
                "hdop": 99.9,
                "flow_in_lpm": None,
                "flow_out_lpm": None,
                "leak_alarm": None,
                "rms1": None,
                "p2p1": None,
                "rms2": None,
                "p2p2": None
            }
            return None

        if not self.current_packet:
            # Fragmented startup text, banners, or separators ignored
            return None

        # 2. GPS Fix line
        # Example: GPS Fix    : NO (searching for satellites...) or YES
        gps_fix_m = re.search(r"GPS\s*Fix\s*:\s*(.+)", line, re.IGNORECASE)
        if gps_fix_m:
            fix_text = gps_fix_m.group(1).strip()
            self.current_packet["gps_valid"] = ("NO" not in fix_text.upper().split()[0])
            return None

        # Satellites line
        sats_m = re.search(r"Satellites\s*:\s*(\d+)", line, re.IGNORECASE)
        if sats_m:
            self.current_packet["satellites"] = int(sats_m.group(1))
            return None

        # HDOP line
        hdop_m = re.search(r"HDOP\s*:\s*([\d\.]+)", line, re.IGNORECASE)
        if hdop_m:
            self.current_packet["hdop"] = float(hdop_m.group(1))
            return None

        # Date / Time
        date_m = re.search(r"Date\s*\(UTC\)\s*:\s*([\d\-]+)", line, re.IGNORECASE)
        if date_m:
            self.current_packet["date_utc"] = date_m.group(1).strip()
            return None

        time_m = re.search(r"Time\s*\(UTC\)\s*:\s*([\d:]+)", line, re.IGNORECASE)
        if time_m:
            self.current_packet["time_utc"] = time_m.group(1).strip()
            return None

        # GPS Coordinates if present
        coord_m = re.search(r"(?:Lat|Latitude)\s*:\s*([-\d\.]+).*?(?:Lng|Lon|Longitude)\s*:\s*([-\d\.]+)", line, re.IGNORECASE)
        if coord_m:
            lat = float(coord_m.group(1))
            lng = float(coord_m.group(2))
            if not (lat == 0.0 and lng == 0.0):
                self.current_packet["latitude"] = lat
                self.current_packet["longitude"] = lng
                self.current_packet["gps_valid"] = True
            return None

        lat_m = re.search(r"^\s*(?:Lat|Latitude)\s*:\s*([-\d\.]+)", line, re.IGNORECASE)
        if lat_m:
            lat = float(lat_m.group(1))
            if lat != 0.0:
                self.current_packet["latitude"] = lat
                if self.current_packet.get("longitude") is not None and self.current_packet["longitude"] != 0.0:
                    self.current_packet["gps_valid"] = True
            return None

        lon_m = re.search(r"^\s*(?:Lng|Lon|Longitude)\s*:\s*([-\d\.]+)", line, re.IGNORECASE)
        if lon_m:
            lng = float(lon_m.group(1))
            if lng != 0.0:
                self.current_packet["longitude"] = lng
                if self.current_packet.get("latitude") is not None and self.current_packet["latitude"] != 0.0:
                    self.current_packet["gps_valid"] = True
            return None

        # Flow inlet
        # Example: Flow inlet : 0.00 L/min
        flow_in_m = re.search(r"Flow\s*inlet\s*:\s*([\d\.]+)", line, re.IGNORECASE)
        if flow_in_m:
            self.current_packet["flow_in_lpm"] = float(flow_in_m.group(1))
            return None

        # Flow outlet
        # Example: Flow outlet: 0.00 L/min
        flow_out_m = re.search(r"Flow\s*outlet\s*:\s*([\d\.]+)", line, re.IGNORECASE)
        if flow_out_m:
            self.current_packet["flow_out_lpm"] = float(flow_out_m.group(1))
            return None

        # Leak alarm
        # Example: Leak alarm : no or yes
        leak_m = re.search(r"Leak\s*alarm\s*:\s*(yes|no)", line, re.IGNORECASE)
        if leak_m:
            self.current_packet["leak_alarm"] = (leak_m.group(1).lower() == "yes")
            return None

        # Piezo 1
        # Example: Piezo 1    : RMS 15.2  P2P 93
        p1_m = re.search(r"Piezo\s*1\s*:\s*RMS\s*([\d\.]+)\s*P2P\s*(\d+)", line, re.IGNORECASE)
        if p1_m:
            self.current_packet["rms1"] = float(p1_m.group(1))
            self.current_packet["p2p1"] = int(p1_m.group(2))
            return None

        # Piezo 2 (Packet terminal line)
        # Example: Piezo 2    : RMS 138.1  P2P 823
        p2_m = re.search(r"Piezo\s*2\s*:\s*RMS\s*([\d\.]+)\s*P2P\s*(\d+)", line, re.IGNORECASE)
        if p2_m:
            self.current_packet["rms2"] = float(p2_m.group(1))
            self.current_packet["p2p2"] = int(p2_m.group(2))

            # Check completeness
            if (
                self.current_packet["flow_in_lpm"] is not None and
                self.current_packet["flow_out_lpm"] is not None and
                self.current_packet["leak_alarm"] is not None and
                self.current_packet["rms1"] is not None and
                self.current_packet["rms2"] is not None
            ):
                fin = self.current_packet["flow_in_lpm"]
                fout = self.current_packet["flow_out_lpm"]
                diff = round(abs(fin - fout), 2)
                alarm = self.current_packet["leak_alarm"]

                if fin < 0.50:
                    status_str = "LOW_OR_NO_FLOW"
                elif alarm:
                    status_str = "LEAK_CONFIRMED"
                elif diff >= 0.10:
                    status_str = "VERIFYING_FLOW"
                else:
                    status_str = "NO_LEAK"

                buf_lat = self.current_packet.get("latitude")
                buf_lng = self.current_packet.get("longitude")
                is_zero = (buf_lat == 0.0 and buf_lng == 0.0)
                gps_valid = bool(
                    self.current_packet.get("gps_valid") and
                    buf_lat is not None and
                    buf_lng is not None and
                    not is_zero
                )
                final_lat = buf_lat if gps_valid else None
                final_lng = buf_lng if gps_valid else None
                gps_time = f"{self.current_packet['date_utc']}T{self.current_packet['time_utc']}Z" if (self.current_packet.get("date_utc") and self.current_packet.get("time_utc")) else None

                completed_record = {
                    "utc_timestamp": datetime.datetime.now().isoformat(),
                    "node_id": self.current_packet["node_id"],
                    "packet_sequence": self.current_packet["sequence"],
                    "flow_in_lpm": fin,
                    "flow_out_lpm": fout,
                    "flow_diff_lpm": diff,
                    "leak_alarm": alarm,
                    "rms1": self.current_packet["rms1"],
                    "p2p1": self.current_packet["p2p1"],
                    "rms2": self.current_packet["rms2"],
                    "p2p2": self.current_packet["p2p2"],
                    "s1_clipped": self.current_packet["p2p1"] >= 1020,
                    "s2_clipped": self.current_packet["p2p2"] >= 1020,
                    "vibration_invalid": False,
                    "gps_valid": gps_valid,
                    "latitude": final_lat,
                    "longitude": final_lng,
                    "satellites": self.current_packet["satellites"],
                    "hdop": self.current_packet["hdop"],
                    "gps_time": gps_time,
                    "missed_packets": self.current_packet["missed_since_last"],
                    "total_missed": self.current_packet["total_missed"],
                    "sequence_reset": 0,
                    "communication_source": "ARDUINO_UNO_NRF24",
                    "status_str": status_str,
                    "is_demo": False
                }
                self.parsed_packets.append(completed_record)
                self.current_packet = None
                return completed_record

        return None

def verify_log_file(log_path: str):
    parser = ArduinoReceiverParser()
    print(f"Reading and parsing log file: {log_path}")
    with open(log_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            res = parser.feed_line(line)
            if res:
                print(f"[PACKET PARSED #{len(parser.parsed_packets)}]: Node={res['node_id']} "
                      f"Seq={res['packet_sequence']} FlowIn={res['flow_in_lpm']}L/m "
                      f"FlowOut={res['flow_out_lpm']}L/m LeakAlarm={res['leak_alarm']} "
                      f"RMS1={res['rms1']}cnt P2P1={res['p2p1']} "
                      f"RMS2={res['rms2']}cnt P2P2={res['p2p2']} "
                      f"GPS_Fix={'YES' if res['gps_valid'] else 'NO'} "
                      f"Status={res['status_str']}")

    print(f"\n==========================================")
    print(f"Total complete wireless packets parsed: {len(parser.parsed_packets)}")
    if parser.parsed_packets:
        last = parser.parsed_packets[-1]
        print(f"Latest Packet:")
        print(f"  Sequence   : {last['packet_sequence']}")
        print(f"  Flow Inlet : {last['flow_in_lpm']:.2f} L/min")
        print(f"  Flow Outlet: {last['flow_out_lpm']:.2f} L/min")
        print(f"  Leak Alarm : {last['leak_alarm']}")
        print(f"  Piezo 1    : RMS {last['rms1']}, P2P {last['p2p1']}")
        print(f"  Piezo 2    : RMS {last['rms2']}, P2P {last['p2p2']}")
        print(f"  GPS Fix    : {last['gps_valid']}")
    print(f"==========================================")
    return parser.parsed_packets

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "arduino_serial.log")
    verify_log_file(log_file)
