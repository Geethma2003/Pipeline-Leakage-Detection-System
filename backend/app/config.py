"""
AquaGuard AI Backend Configuration
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = os.path.join(BASE_DIR, "aquaguard.db")

# Serial Port Defaults (Arduino Uno nRF24 Receiver)
DEFAULT_SERIAL_PORT = os.getenv("AQUAGUARD_SERIAL_PORT", "COM14")
DEFAULT_BAUD_RATE = int(os.getenv("AQUAGUARD_BAUD_RATE", "115200"))

# Pipeline System Physical Constants
PIPE_LENGTH_METERS = 2.0
SENSOR_1_POSITION = 0.0
SENSOR_2_POSITION = 2.0
SAMPLE_RATE_HZ = 2500
ACOUSTIC_SPEED_MPS = 1200.0

# 60-Second Analysis Window Defaults
ANALYSIS_WINDOW_SEC = 60
DEFAULT_PERSISTENCE_REQ = 42
MIN_CONSECUTIVE_ABN = 15
MAD_MULTIPLIER = 3.5
RMS_FACTOR_MULTIPLIER = 2.2
MIN_RMS_ABSOLUTE_FLOOR = 15.0
MAX_VARIABILITY_RATIO = 0.48
MIN_CORRELATION_PEAK = 0.65
