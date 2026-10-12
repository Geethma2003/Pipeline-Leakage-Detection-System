"""
Temporary Python Serial Reader for AquaGuard AI Arduino Uno Receiver
Port: COM14, Baud: 115200
Captures real wireless telemetry, logs to arduino_serial.log, and parses both
structured RF24_V1 records and the multiline human-readable Arduino receiver format.
"""
import sys
import os
import time
import datetime
import argparse
import re
import serial
from verify_parser import ArduinoReceiverParser

LOG_FILE = os.path.join(os.path.dirname(__file__), "arduino_serial.log")

def parse_rf24_v1(line: str):
    """Parses RF24_V1 fixed-point machine protocol."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 22:
        return None
    try:
        node_id = int(parts[1])
        sequence = int(parts[2])
        flags = int(parts[3])
        lat_e7 = int(parts[4])
        lng_e7 = int(parts[5])
        satellites = int(parts[6])
        hdop_x10 = int(parts[7])
        flow_in_x100 = int(parts[14])
        flow_out_x100 = int(parts[15])
        rms1_x10 = int(parts[16])
        rms2_x10 = int(parts[17])
        p2p1 = int(parts[18])
        p2p2 = int(parts[19])
        missed = int(parts[20])
        seq_reset = int(parts[21])

        return {
            "protocol": "RF24_V1",
            "node_id": node_id,
            "sequence": sequence,
            "flags": flags,
            "gps_valid": bool(flags & 0x01),
            "s1_clipped": bool(flags & 0x02),
            "s2_clipped": bool(flags & 0x04),
            "flow_leak_alarm": bool(flags & 0x08),
            "vibration_invalid": bool(flags & 0x10),
            "latitude": round(lat_e7 / 10000000.0, 7) if (flags & 0x01) and (lat_e7 or lng_e7) else None,
            "longitude": round(lng_e7 / 10000000.0, 7) if (flags & 0x01) and (lat_e7 or lng_e7) else None,
            "satellites": satellites,
            "hdop": round(hdop_x10 / 10.0, 1),
            "flow_in_lpm": round(flow_in_x100 / 100.0, 2),
            "flow_out_lpm": round(flow_out_x100 / 100.0, 2),
            "flow_diff_lpm": round(abs(flow_in_x100 - flow_out_x100) / 100.0, 2),
            "rms1_counts": round(rms1_x10 / 10.0, 1),
            "rms2_counts": round(rms2_x10 / 10.0, 1),
            "p2p1_counts": p2p1,
            "p2p2_counts": p2p2,
            "missed_packets": missed,
            "sequence_reset": seq_reset
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    parser_args = argparse.ArgumentParser(description="Read Arduino Uno Receiver on COM14")
    parser_args.add_argument("--port", default="COM14", help="Serial port (default: COM14)")
    parser_args.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser_args.add_argument("--duration", type=float, default=12.0, help="Read duration in seconds (default: 12.0s, 0 for continuous)")
    args = parser_args.parse_args()

    port = args.port
    baud = args.baud
    duration = args.duration

    print(f"==================================================")
    print(f" AquaGuard AI - Temporary Arduino Serial Reader")
    print(f" Port: {port} @ {baud} baud")
    print(f" Log File: {LOG_FILE}")
    print(f" Capture Duration: {duration}s" if duration > 0 else " Continuous mode (Ctrl+C to stop)")
    print(f"==================================================")

    ser = None
    try:
        ser = serial.Serial(port, baud, timeout=1.0)
        print(f"[OK] Successfully connected to {port} at {baud} baud.")
    except Exception as e:
        print(f"[ERROR] Could not open {port}: {e}")
        sys.exit(1)

    start_time = time.time()
    line_count = 0
    rf24_count = 0
    multiline_count = 0
    receiver_parser = ArduinoReceiverParser()

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- SESSION START: {datetime.datetime.now().isoformat()} (Port: {port}, Baud: {baud}) ---\n")
        try:
            while True:
                if duration > 0 and (time.time() - start_time) > duration:
                    print(f"\n[INFO] Capture duration ({duration}s) reached. Exiting cleanly...")
                    break

                raw_line = ser.readline()
                if not raw_line:
                    continue

                line_str = raw_line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                line_count += 1
                now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                log_f.write(f"[{now_str}] {line_str}\n")
                log_f.flush()

                print(f"[{now_str}] {line_str}")

                if line_str.startswith("RF24_V1,"):
                    rf24_count += 1
                    parsed = parse_rf24_v1(line_str)
                    if parsed:
                        print(f"   --> [PARSED RF24_V1]: Node={parsed.get('node_id')} Seq={parsed.get('sequence')} "
                              f"Inlet={parsed.get('flow_in_lpm')}L/m Outlet={parsed.get('flow_out_lpm')}L/m "
                              f"Diff={parsed.get('flow_diff_lpm')}L/m LeakAlarm={parsed.get('flow_leak_alarm')} "
                              f"RMS1={parsed.get('rms1_counts')}cnt RMS2={parsed.get('rms2_counts')}cnt "
                              f"GPS_Valid={parsed.get('gps_valid')}")
                else:
                    pkt = receiver_parser.feed_line(line_str)
                    if pkt:
                        multiline_count += 1
                        print(f"   ==> [WIRELESS PACKET #{pkt['packet_sequence']} VALIDATED]: "
                              f"Node={pkt['node_id']} FlowIn={pkt['flow_in_lpm']:.2f}L/m FlowOut={pkt['flow_out_lpm']:.2f}L/m "
                              f"LeakAlarm={'YES' if pkt['leak_alarm'] else 'NO'} "
                              f"RMS1={pkt['rms1']:.1f}cnt (P2P {pkt['p2p1']}) RMS2={pkt['rms2']:.1f}cnt (P2P {pkt['p2p2']}) "
                              f"GPS={'FIX' if pkt['gps_valid'] else 'NO FIX'}")

        except KeyboardInterrupt:
            print("\n[INFO] Stopped by user (KeyboardInterrupt).")
        finally:
            if ser and ser.is_open:
                ser.close()
                print(f"[OK] Closed {port}. Serial port successfully released.")
            log_f.write(f"--- SESSION END: {datetime.datetime.now().isoformat()} (Total Lines: {line_count}, RF24 Packets: {rf24_count}, Multiline Packets: {multiline_count}) ---\n")

    print(f"\nSummary:")
    print(f"Total lines received: {line_count}")
    print(f"RF24_V1 machine records: {rf24_count}")
    print(f"Multiline wireless packets: {multiline_count}")
    print(f"Messages saved to: {LOG_FILE}")

if __name__ == "__main__":
    main()
