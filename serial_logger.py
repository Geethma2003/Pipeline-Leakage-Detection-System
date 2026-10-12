#!/usr/bin/env python3
"""
ESP32 Pipeline Leakage Detection System - Serial Data Logger
============================================================
Saves real-time serial measurements from the ESP32 pipeline monitor into CSV format
for offline analysis and visualization.

Usage:
    python serial_logger.py --port COM13 --baud 115200 --output real_normal.csv --mode-cmd
"""

import argparse
import sys
import time
import datetime
import csv
import os
import re
from typing import Dict, Any, Optional, List, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] 'pyserial' package is not installed. Install via: pip install pyserial")
    sys.exit(1)


CSV_HEADER = [
    "pc_timestamp", "esp32_ms", "second_index",
    "s1_rms", "s1_p2p", "s1_variance", "s1_stvar",
    "s2_rms", "s2_p2p", "s2_variance", "s2_stvar",
    "s1_abnormal", "s2_abnormal", "is_transient", "status_str"
]


def auto_detect_port() -> Optional[str]:
    """Attempt to auto-detect connected ESP32 / USB Serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(keyword in port.description for keyword in ["CP210", "CH340", "USB Serial", "ESP32"]):
            return port.device
    if ports:
        return ports[0].device
    return None


def parse_serial_line(line_str: str, pc_ts: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses a single raw serial line from the ESP32 firmware.
    
    Returns a dictionary with:
    - 'status_code': 'CSV_VALID', 'LEGACY_RAW', 'PARSE_ERROR', or 'INFO'
    - 'row_data': list of 15 strings matching CSV_HEADER, or None
    - 'message': formatted description for stdout logging
    - 'warnings': list of active validation/hardware warnings
    """
    if pc_ts is None:
        pc_ts = datetime.datetime.now().isoformat()

    line_clean = line_str.strip()
    warnings: List[str] = []

    # 1. Standard Machine-Readable CSV Line Output from pipeline_monitor.ino
    if line_clean.startswith("CSV,"):
        parts = line_clean.split(",")
        if len(parts) == 15:
            try:
                esp32_ms = int(parts[1])
                sec_idx = int(parts[2])
                s1_rms = float(parts[3])
                s1_p2p = float(parts[4])
                s1_var = float(parts[5])
                s1_stvar = float(parts[6])
                s2_rms = float(parts[7])
                s2_p2p = float(parts[8])
                s2_var = float(parts[9])
                s2_stvar = float(parts[10])
                s1_abn = int(parts[11])
                s2_abn = int(parts[12])
                transient = int(parts[13])
                status_str = parts[14]

                # Validation & Hardware Warning Checks
                if s1_p2p > 4000.0 or s2_p2p > 4000.0:
                    warnings.append("ADC Clipping Warning: Peak-to-Peak ADC counts close to 12-bit max (4095).")
                if s1_var < 0.1 or s2_var < 0.1:
                    warnings.append("Flatline Variance Warning: Disconnected sensor pin or flatline signal detected.")
                if status_str == "FAULT":
                    warnings.append("Firmware FAULT Status: Sensor DC rail offset out of valid 0.32V-2.98V range.")

                row_data = [pc_ts] + parts[1:]
                msg = f"[{pc_ts}] CSV Record #{sec_idx}: S1_RMS={s1_rms:.2f} S2_RMS={s2_rms:.2f} Status={status_str}"
                return {
                    "status_code": "CSV_VALID",
                    "row_data": row_data,
                    "message": msg,
                    "warnings": warnings
                }

            except ValueError as ve:
                err_msg = f"[{pc_ts}] [PARSER ERROR] Numeric conversion failed ({ve}) on line: '{line_clean}'"
                return {
                    "status_code": "PARSE_ERROR",
                    "row_data": None,
                    "message": err_msg,
                    "warnings": [f"Numeric conversion error: {ve}"]
                }
        else:
            err_msg = f"[{pc_ts}] [PARSER ERROR] Field count mismatch: expected 15 fields, got {len(parts)} in line: '{line_clean}'"
            return {
                "status_code": "PARSE_ERROR",
                "row_data": None,
                "message": err_msg,
                "warnings": [f"Expected 15 CSV fields, got {len(parts)}"]
            }

    # 2. Legacy Raw Unstructured Serial Line (e.g., 'Sensor 1: 2782    Sensor 2: 2865')
    raw_match = re.search(r"Sensor\s*1:\s*(\d+)\s+Sensor\s*2:\s*(\d+)", line_clean, re.IGNORECASE)
    if raw_match:
        s1_raw_adc = int(raw_match.group(1))
        s2_raw_adc = int(raw_match.group(2))
        warn_str = (
            f"[{pc_ts}] [WARNING] Legacy raw ADC format detected ('Sensor 1: {s1_raw_adc}  Sensor 2: {s2_raw_adc}'). "
            f"ESP32 is running legacy/unstructured firmware. Please compile and flash 'pipeline_monitor.ino' to COM port."
        )
        return {
            "status_code": "LEGACY_RAW",
            "row_data": None,
            "message": warn_str,
            "warnings": ["Unstructured raw serial output format - firmware update required."]
        }

    # 3. Legacy CAL or LOG lines
    if line_clean.startswith("CAL,") or line_clean.startswith("LOG,"):
        info_msg = f"[{pc_ts}] [INFO] Received status line: '{line_clean}'"
        return {
            "status_code": "INFO",
            "row_data": None,
            "message": info_msg,
            "warnings": []
        }

    # 4. Firmware Print Messages / Menu / Diagnostics
    info_msg = f"[{pc_ts}] [ESP32 PRINT] {line_clean}"
    return {
        "status_code": "INFO",
        "row_data": None,
        "message": info_msg,
        "warnings": []
    }


def main():
    parser = argparse.ArgumentParser(description="Serial Logger for ESP32 Pipeline Leakage Detection")
    parser.add_argument("--port", type=str, default=None, help="Serial port (e.g. COM13, /dev/ttyUSB0). Auto-detects if omitted.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filename. Generates timestamped name if omitted.")
    parser.add_argument("--mode-cmd", action="store_true", help="Send 'M' command on startup to switch ESP32 to machine CSV output mode")
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

    print("==================================================")
    print("   ESP32 PIPELINE MONITOR SERIAL DATA LOGGER      ")
    print("==================================================")
    print(f" Serial Port : {port}")
    print(f" Baud Rate   : {args.baud}")
    print(f" Output File : {output_filename}")
    print(f" Mode Cmd    : {'ENABLED (Sending M command)' if args.mode_cmd else 'DISABLED'}")
    print(" Press Ctrl+C to stop logging safely.")
    print("==================================================\n")

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
                writer.writerow(CSV_HEADER)
                csvfile.flush()

            line_count = 0
            unparsed_count = 0

            while True:
                if ser.in_waiting > 0:
                    raw_line = ser.readline()
                    try:
                        line_str = raw_line.decode("utf-8", errors="replace").strip()
                    except Exception:
                        continue

                    if not line_str:
                        continue

                    result = parse_serial_line(line_str)
                    print(result["message"])

                    for w in result["warnings"]:
                        print(f"  └─> [WARNING] {w}")

                    if result["status_code"] == "CSV_VALID" and result["row_data"]:
                        writer.writerow(result["row_data"])
                        csvfile.flush()
                        line_count += 1
                    elif result["status_code"] in ["LEGACY_RAW", "PARSE_ERROR"]:
                        unparsed_count += 1

                time.sleep(0.01)

    except serial.SerialException as e:
        print(f"\n[ERROR] Serial Port Error: {e}")
        if "Access is denied" in str(e) or "PermissionError" in str(e):
            print(f"[HINT] Port {port} is locked by another process (Arduino Serial Monitor, IDE, or AquaGuard backend). Close other apps first.")
    except KeyboardInterrupt:
        print(f"\n[INFO] Logging stopped by user. Total valid rows logged: {line_count} (Unparsed/legacy lines: {unparsed_count})")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("[INFO] Serial port closed safely.")


if __name__ == "__main__":
    main()
