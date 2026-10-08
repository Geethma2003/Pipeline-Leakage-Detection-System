#!/usr/bin/env python3
"""
ESP32 Pipeline Leakage Detection System - Serial Data Logger
============================================================
Saves real-time serial measurements from the ESP32 pipeline monitor into CSV format
for offline analysis and visualization.

Usage:
    python serial_logger.py --port COM3 --baud 115200 --output experiment_data.csv
"""

import argparse
import sys
import time
import datetime
import csv
import os

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] 'pyserial' package is not installed. Install via: pip install pyserial")
    sys.exit(1)


def auto_detect_port():
    """Attempt to auto-detect connected ESP32 / USB Serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "CP210" in port.description or "CH340" in port.description or "USB Serial" in port.description or "ESP32" in port.description:
            return port.device
    if ports:
        return ports[0].device
    return None


def main():
    parser = argparse.ArgumentParser(description="Serial Logger for ESP32 Pipeline Leakage Detection")
    parser.add_argument("--port", type=str, default=None, help="Serial port (e.g. COM3, /dev/ttyUSB0). Auto-detects if omitted.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filename. Generates timestamped name if omitted.")
    parser.add_argument("--mode-cmd", action="store_true", help="Send 'M' command on startup to ensure CSV mode")
    args = parser.parse_args()

    port = args.port or auto_detect_port()
    if not port:
        print("[ERROR] No serial port found. Please specify --port <COM_PORT>.")
        sys.exit(1)

    if not args.output:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"pipeline_log_{timestamp_str}.csv"
    else:
        output_filename = args.output

    print(f"==================================================")
    print(f"   ESP32 PIPELINE MONITOR SERIAL DATA LOGGER      ")
    print(f"==================================================")
    print(f" Serial Port : {port}")
    print(f" Baud Rate   : {args.baud}")
    print(f" Output File : {output_filename}")
    print(f" Press Ctrl+C to stop logging safely.")
    print(f"==================================================\n")

    # CSV Header definition matching ESP32 firmware output
    csv_header = [
        "pc_timestamp", "esp32_ms", "second_index",
        "s1_rms", "s1_p2p", "s1_variance", "s1_stvar",
        "s2_rms", "s2_p2p", "s2_variance", "s2_stvar",
        "s1_abnormal", "s2_abnormal", "is_transient", "status_str"
    ]

    file_exists = os.path.isfile(output_filename)

    try:
        ser = serial.Serial(port, args.baud, timeout=1.0)
        print(f"[INFO] Connected to {port} at {args.baud} baud.")
        time.sleep(2.0)  # Allow ESP32 reset stabilization

        if args.mode_cmd:
            print("[INFO] Sending 'M' command to switch ESP32 to CSV output mode...")
            ser.write(b"M\n")
            ser.flush()

        with open(output_filename, mode="a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(csv_header)
                csvfile.flush()

            line_count = 0
            while True:
                if ser.in_waiting > 0:
                    raw_line = ser.readline()
                    try:
                        line_str = raw_line.decode("utf-8", errors="replace").strip()
                    except Exception:
                        continue

                    if not line_str:
                        continue

                    pc_ts = datetime.datetime.now().isoformat()

                    # Print line to terminal console
                    print(f"[{pc_ts}] {line_str}")

                    # If line starts with CSV prefix, parse and save
                    if line_str.startswith("CSV,"):
                        parts = line_str.split(",")
                        if len(parts) >= 14:
                            # CSV format: CSV,esp32_ms,sec_idx,s1_rms,s1_p2p,s1_var,s1_stvar,s2_rms,s2_p2p,s2_var,s2_stvar,s1_abn,s2_abn,trans,status
                            row_data = [pc_ts] + parts[1:]
                            writer.writerow(row_data)
                            csvfile.flush()
                            line_count += 1
                    elif line_str.startswith("CAL,") or line_str.startswith("LOG,"):
                        parts = line_str.split(",")
                        row_data = [pc_ts] + parts[1:]
                        writer.writerow(row_data)
                        csvfile.flush()
                        line_count += 1

                time.sleep(0.01)

    except serial.SerialException as e:
        print(f"\n[ERROR] Serial Port Error: {e}")
    except KeyboardInterrupt:
        print(f"\n[INFO] Logging stopped by user. Total rows logged: {line_count}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("[INFO] Serial port closed safely.")


if __name__ == "__main__":
    main()
