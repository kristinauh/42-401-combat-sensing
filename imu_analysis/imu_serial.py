# imu_serial.py
# logs data over serial port for IMU calibration

import os
import csv
import time
from datetime import datetime
from typing import Optional, Tuple

import serial

SERIAL_PORT = "COM5"
BAUD_RATE = 115200

PERSON = "test"
ACTIVITY = "random"
TRIAL = 0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data", "raw", PERSON)
os.makedirs(DATA_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(
    DATA_DIR,
    f"{PERSON}_{ACTIVITY}_{TRIAL:02d}.csv"
)

def parse_line(line: str) -> Optional[Tuple[float, float, float, float, float, float, float, float, int, float, str]]:
    line = line.strip()
    if not line:
        return None

    parts = line.split(",")

    # Expect exactly 11 fields from Arduino
    if len(parts) != 11:
        return None

    try:
        ax = float(parts[0])
        ay = float(parts[1])
        az = float(parts[2])
        gx = float(parts[3])
        gy = float(parts[4])
        gz = float(parts[5])
        asvm = float(parts[6])
        gsvm = float(parts[7])
        mcu_time = int(parts[8])
        fall_event = float(parts[9])
        label = parts[10].strip()

        return ax, ay, az, gx, gy, gz, asvm, gsvm, mcu_time, fall_event, label

    except ValueError:
        return None


def main():
    print(f"Opening serial port {SERIAL_PORT}...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()
    print("Connected.\n")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "AX", "AY", "AZ",
            "GX", "GY", "GZ",
            "ASVM", "GSVM",
            "MCU_TIME",
            "FALL_EVENT",
            "FALL_STATE"
        ])

        print("Recording… Press Ctrl+C to stop.")

        lines_to_print = 0

        try:
            while True:
                line = ser.readline().decode(errors="ignore")
                parsed = parse_line(line)
                if parsed is None:
                    continue

                *_, label = parsed
                # Trigger printing for the next 2 lines after ANALYZE_IMPACT
                if label == "ANALYZE_IMPACT":
                    print(f"  >> ANALYZE_IMPACT detected — watching next 2 states...")
                    lines_to_print = 2

                elif lines_to_print > 0:
                    print(f"  >> Post-impact state: {label}")
                    lines_to_print -= 1

                writer.writerow([
                    datetime.now().isoformat(timespec="milliseconds"),
                    *parsed
                ])

        except KeyboardInterrupt:
            print("\nStopped by user.")

    ser.close()
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()