# ppg_serial.py
# Collect PPG data from serial and save alongside reference HR/SpO2

import os
import sys
import csv
import time
import threading
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

import serial
from utils.serial_parser import parse_csv

SERIAL_PORT = "COM6"
BAUD_RATE = 115200

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

PPG_OUTPUT_FILE = os.path.join(DATA_DIR, "ppg_raw_KH.csv")
REF_OUTPUT_FILE = os.path.join(DATA_DIR, "ppg_ref_KH.csv")

WINDOW = 10.0  # seconds per window

# (activity label, duration in seconds)
# 7-minute protocol adapted from:
# Lin et al., "A Novel Chest-Based PPG Measurement System," IEEE JTEHM, 2024
# https://pmc.ncbi.nlm.nih.gov/articles/PMC11573410/
# See paper for full protocol details and chest placement (locations a–d)
# PROTOCOL_STEPS = [
#     ("Normal breath", 60),
#     ("Deep breath", 30),
#     ("Normal breath", 60),
#     ("Hold breath", 30),
#     ("Normal breath", 60),
#     ("Finger tap", 30),
#     ("Normal breath", 60),
#     ("Swing arm", 30),
#     ("Normal breath", 60),
# ]

PROTOCOL_STEPS = [
    ("Normal breath", 60),
    ("Deep breath", 30),
    ("Normal breath", 60),
    ("Hold breath", 30),
    ("Normal breath", 60)
]

def now_iso():
    return datetime.now().isoformat(timespec="milliseconds")

def build_window_protocol(protocol_steps, window_sec):
    # Expand protocol into one label per window
    labels = []
    for label, duration in protocol_steps:
        labels += [label] * int(round(duration / window_sec))
    return labels

WINDOW_LABELS = build_window_protocol(PROTOCOL_STEPS, WINDOW)
SETS = len(WINDOW_LABELS)

def get_first_reference(window_num, label):
    # Block until user enters first HR/SpO2 for this window
    print(f"\nWindow {window_num}: {label}")
    print("Enter HR SpO2 (e.g. 72 98)")

    while True:
        parts = input("> ").strip().split()
        if len(parts) != 2:
            continue
        try:
            return [now_iso(), window_num, float(parts[0]), float(parts[1])]
        except:
            continue

def input_thread(stop_event, window_num, ref_rows):
    # Allow additional HR/SpO2 entries during window
    while not stop_event.is_set():
        try:
            parts = input("Extra > ").strip().split()
        except EOFError:
            break

        if len(parts) != 2:
            continue

        try:
            ref_rows.append([
                now_iso(),
                window_num,
                float(parts[0]),
                float(parts[1])
            ])
        except:
            continue

def main():
    print(f"Opening {SERIAL_PORT}...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()

    with open(PPG_OUTPUT_FILE, "w", newline="") as ppg_f, \
         open(REF_OUTPUT_FILE, "w", newline="") as ref_f:

        ppg_writer = csv.writer(ppg_f)
        ref_writer = csv.writer(ref_f)

        # CSV headers
        ppg_writer.writerow(["timestamp", "window", "sample", "ir_raw", "red_raw"])
        ref_writer.writerow(["timestamp", "window", "true_hr", "true_spo2"])

        for i, label in enumerate(WINDOW_LABELS):
            window_num = i + 1

            print(f"\n--- Window {window_num}/{SETS} ---")
            print(f"Activity: {label}")

            # Get first reference before starting
            ref_rows = [get_first_reference(window_num, label)]

            ser.reset_input_buffer()

            stop_event = threading.Event()
            threading.Thread(
                target=input_thread,
                args=(stop_event, window_num, ref_rows),
                daemon=True
            ).start()

            start = time.time()
            sample_idx = 0

            # Collect PPG samples for this window
            while time.time() - start < WINDOW:
                line = ser.readline().decode(errors="ignore").strip()
                vals = parse_csv(line, expected_values=2)

                if vals is None:
                    continue

                try:
                    ir = int(vals[0])
                    red = int(vals[1])
                except:
                    continue

                ppg_writer.writerow([
                    now_iso(),
                    window_num,
                    sample_idx,
                    ir,
                    red
                ])
                sample_idx += 1

            stop_event.set()

            # Save all reference entries
            for row in ref_rows:
                ref_writer.writerow(row)

            print(f"Saved {sample_idx} samples")

    ser.close()
    print("Done.")

if __name__ == "__main__":
    main()