# ppg_param.py
#
# Parameter sweep tool for MAX30102 sensor configuration
#
# Tested configurations (LED, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange):
#
#   Stage 1 — LED brightness × ADC range
#     Trial A: sensor.setup(60,  1, 2, 100, 411, 4096)
#     Trial B: sensor.setup(120, 1, 2, 100, 411, 16384)
#     Trial C: sensor.setup(150, 1, 2, 100, 411, 16384)
#     Trial D: sensor.setup(180, 1, 2, 100, 411, 16384)
#
#   Stage 2 — sample average sweep
#     Trial E: sensor.setup(150, 4, 2, 100, 411, 16384)
#     Trial F: sensor.setup(150, 2, 2, 100, 411, 16384)
#
#   Stage 3 — sample rate sweep
#     Trial G: sensor.setup(150, 1, 2, 50, 411, 16384)
#     Trial H: sensor.setup(150, 2, 2, 50, 411, 16384)
#
# Using Trial C configs

import os
import csv
import time
import serial
from datetime import datetime

SERIAL_PORT = "COM6"
BAUD_RATE   = 115200
WINDOW_SEC  = 10.0
NUM_WINDOWS = 18

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def now_iso():
    return datetime.now().isoformat(timespec="milliseconds")

def main():
    trial_name = input("Trial name (e.g. A, B, C): ").strip()

    output_file = os.path.join(DATA_DIR, f"ppg_trial_{trial_name}.csv")

    print(f"\nOpening {SERIAL_PORT}...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "window", "sample", "ir_raw", "red_raw", "true_hr"])

        for w in range(1, NUM_WINDOWS + 1):
            true_hr = float(input(f"Window {w}/{NUM_WINDOWS} — Your current HR (bpm): ").strip())
            print(f"  Collecting...")
            ser.reset_input_buffer()
            start      = time.time()
            sample_idx = 0

            while time.time() - start < WINDOW_SEC:
                line = ser.readline().decode(errors="ignore").strip()
                try:
                    parts = line.split(",")
                    if len(parts) != 2:
                        continue
                    ir  = int(parts[0])
                    red = int(parts[1])
                except:
                    continue

                writer.writerow([now_iso(), w, sample_idx, ir, red, true_hr])
                sample_idx += 1

            print(f"  {sample_idx} samples")

    ser.close()
    print(f"\nDone. Saved to {output_file}")

if __name__ == "__main__":
    main()