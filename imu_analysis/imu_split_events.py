from pathlib import Path
import csv
from typing import List

# --- Configuration ---
PRE_ROWS = 1
POST_ROWS = 5
TARGET_STATE = "CHECK_FALL"
REQUIRED_LEN = 200
MIN_POST_CHECK_ROWS = 2

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPT_DIR / "data" / "raw"
SPLIT_DIR = SCRIPT_DIR / "data" / "split"


# --- Helpers ---
def find_check_fall_windows(states):
    windows = []
    i = 0
    n = len(states)

    while i < n:
        if states[i] == TARGET_STATE:
            start = i
            while i + 1 < n and states[i + 1] == TARGET_STATE:
                i += 1
            end = i
            windows.append((start, end))
        i += 1

    return windows


def expand_window(start, end, n_rows):
    return max(0, start - PRE_ROWS), min(n_rows - 1, end + POST_ROWS)


# --- Core processing ---
def process_csv_file(input_path: Path, output_dir: Path):
    base_name = input_path.stem
    print(f"\nProcessing: {input_path}")

    with input_path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    if not rows:
        print("empty file")
        return

    states = [row[11] for row in rows]
    raw_windows = find_check_fall_windows(states)
    print(f"Found {len(raw_windows)} CHECK_FALL segments")

    file_idx = 0

    for start, end in raw_windows:
        block_len = end - start + 1

        if block_len < REQUIRED_LEN:
            continue

        s, e = expand_window(start, end, len(rows))
        post_rows = e - end

        if post_rows < MIN_POST_CHECK_ROWS:
            print("Not enough rows after CHECK_FALL section")
            continue

        out_path = output_dir / f"{base_name}_event_{file_idx:02d}.csv"
        file_idx += 1

        with out_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows[s:e+1])


def process_folders(people: List[str]):
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)

    for person in people:
        input_dir = RAW_DIR / person
        output_dir = SPLIT_DIR / person

        if not input_dir.exists():
            raise FileNotFoundError(f"Input folder not found: {input_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)

        for csv_file in input_dir.glob("*.csv"):
            process_csv_file(csv_file, output_dir)


# --- Entry point ---
if __name__ == "__main__":
    people = [
        "harry2"
    ]

    process_folders(people)