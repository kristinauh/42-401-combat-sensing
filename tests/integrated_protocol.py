# integrated_protocol.py
import asyncio
import threading
import csv
import time
import struct
import queue
from datetime import datetime
from pathlib import Path

from protocol_ui import ProtocolUI

DEVICE_NAME  = "XIAO-SENSE"
TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

PROTOCOL_STEPS = [
    ("PPG_WARMUP",     10, "Stand still. Do not move."),
    ("BASELINE_STILL", 30, "Stand still."),
    ("WALK_SLOW",      30, "Walk at a comfortable, relaxed pace."),
    ("WALK_FAST",      30, "Walk briskly."),
    ("RECOVERY_STILL", 30, "Stand still."),
    ("RUN",            60, "Run in place or jog."),
    ("RECOVERY_STILL", 30, "Stand still."),
    ("JUMP_SINGLE",    30, "Perform one jump, then stand still."),
    ("JUMP_REPEATED",  30, "Jump repeatedly at roughly one jump per second."),
    ("RECOVERY_STILL", 30, "Stand still."),
    ("FALL_FORWARD",   30, "Controlled forward fall. Lie still after impact."),
    ("FALL_BACKWARD",  30, "Controlled backward fall. Lie still after impact."),
    ("FALL_SIDE",      30, "Controlled side fall. Lie still after impact."),
    ("SIT_QUICK",      30, "Sit down quickly from standing, then remain seated."),
]

# Precompute cumulative start time of each step by index.
# Keyed by index so duplicate labels (RECOVERY_STILL x3) are handled correctly.
PROTOCOL_CUMULATIVE = []  # cumulative start time of step i
PROTOCOL_DURATIONS  = []  # duration of step i
_acc = 0
for _label, _dur, _ in PROTOCOL_STEPS:
    PROTOCOL_CUMULATIVE.append(_acc)
    PROTOCOL_DURATIONS.append(_dur)
    _acc += _dur

STATE_NAMES = {
    0: "IDLE_FALL",
    1: "CHECK_FALL",
    2: "ANALYZE_IMPACT",
    3: "DETECTED_FALL",
    4: "STATIONARY_POST_FALL",
    5: "WALKING",
    6: "RUNNING",
    7: "JUMPING",
    8: "LIMPING",
    9: "SITTING",
    10: "SQUATTING",
}

FIELDNAMES = [
    "time", "activity_label",
    "ble_hr", "ble_spo2",
    "imu_state", "imu_event_val", "imu_impact",
    "ble_rr", "ble_sbp", "ble_dbp", "ble_vbat", "v_percent",
    "ref_hr", "ref_spo2",
]

data_rows: list[dict]  = []
current_label: str     = "IDLE"
ble_connected: bool    = False
row_lock               = threading.Lock()
ref_queue: queue.Queue = queue.Queue()

csv_path: Path = None
ui: ProtocolUI = None

# Protocol clock state
p_running:        bool = False
current_step_idx: int  = -1   # index into PROTOCOL_STEPS, -1 = not started
current_remaining: int = 0    # remaining seconds in current step as reported by on_tick
last_tick_wall: float = 0.0

def vbat_to_percent(vbat):
    if vbat is None:
        return None

    if vbat >= 3.5:
        pct = 7 + (vbat - 3.5) / (4.2 - 3.5) * 93
    else:
        pct = (vbat - 2.5) / (3.5 - 2.5) * 7

    return max(0, min(100, int(pct)))
    
def get_protocol_time() -> float:
    if not p_running or current_step_idx < 0 or current_remaining <= 0:
        return 0.0
    dur             = PROTOCOL_DURATIONS[current_step_idx]
    wall_offset     = min(time.time() - last_tick_wall, 1.0)
    elapsed_in_step = (dur - current_remaining) + wall_offset
    return PROTOCOL_CUMULATIVE[current_step_idx] + elapsed_in_step

class PacketParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)
        decoded = []

        while self.buf:
            ptype = chr(self.buf[0])

            if ptype == "R":  # PPG packet: ts(u32) hr(i16 x100) spo2(i16 x100)
                if len(self.buf) < 9:
                    break
                pkt = bytes(self.buf[:9])
                del self.buf[:9]
                ts     = struct.unpack_from("<I", pkt, 1)[0]
                hr_i   = struct.unpack_from("<h", pkt, 5)[0]
                spo2_i = struct.unpack_from("<h", pkt, 7)[0]
                hr   = None if hr_i   < 0 else hr_i   / 100.0
                spo2 = None if spo2_i < 0 else spo2_i / 100.0
                decoded.append(("R", ts, hr, spo2))

            elif ptype == "M":  # IMU packet: ts(u32) state(u8) event(i16 x100) impact(i16 x100)
                if len(self.buf) < 10:
                    break
                pkt = bytes(self.buf[:10])
                del self.buf[:10]
                ts       = struct.unpack_from("<I", pkt, 1)[0]
                state    = pkt[5]
                event_i  = struct.unpack_from("<h", pkt, 6)[0]
                impact_i = struct.unpack_from("<h", pkt, 8)[0]
                decoded.append(("M", ts, state, event_i / 100.0, impact_i / 100.0))

            elif ptype == "W":  # RR packet: ts(u32) rr(i16 x100)
                if len(self.buf) < 7:
                    break
                pkt = bytes(self.buf[:7])
                del self.buf[:7]
                ts   = struct.unpack_from("<I", pkt, 1)[0]
                rr_i = struct.unpack_from("<h", pkt, 5)[0]
                rr   = None if rr_i < 0 else rr_i / 100.0
                decoded.append(("W", ts, rr))

            elif ptype == "P":  # BP packet: ts(u32) sbp(i16 x10) dbp(i16 x10)
                if len(self.buf) < 9:
                    break
                pkt = bytes(self.buf[:9])
                del self.buf[:9]
                ts    = struct.unpack_from("<I", pkt, 1)[0]
                sbp_i = struct.unpack_from("<h", pkt, 5)[0]
                dbp_i = struct.unpack_from("<h", pkt, 7)[0]
                sbp   = None if sbp_i < 0 else sbp_i / 10.0
                dbp   = None if dbp_i < 0 else dbp_i / 10.0
                decoded.append(("P", ts, sbp, dbp))

            elif ptype == "B":  # Battery packet: ts(u32) vbat(i16 x100)
                if len(self.buf) < 7:
                    break
                pkt = bytes(self.buf[:7])
                del self.buf[:7]
                ts     = struct.unpack_from("<I", pkt, 1)[0]
                vbat_i = struct.unpack_from("<h", pkt, 5)[0]
                vbat   = vbat_i / 100.0
                decoded.append(("B", ts, vbat))

            else:
                del self.buf[0]

        return decoded


parser = PacketParser()


def handle_notification(sender, data: bytearray):
    # Ignore everything outside an active protocol window
    if not p_running or current_remaining <= 0:
        return

    ts_time = get_protocol_time()

    for pkt in parser.feed(bytes(data)):
        ptype = pkt[0]
        row = {k: "" for k in FIELDNAMES}
        row["time"]           = ts_time
        row["activity_label"] = current_label

        if ptype == "R":
            _, ts, hr, spo2 = pkt
            row["ble_hr"]   = "" if hr   is None else f"{hr:.2f}"
            row["ble_spo2"] = "" if spo2 is None else f"{spo2:.2f}"
            print(f"[PPG] HR={row['ble_hr']} bpm  SpO2={row['ble_spo2']}%")

        elif ptype == "M":
            _, ts, state, event_val, impact = pkt
            row["imu_state"]     = STATE_NAMES.get(state, str(state))
            row["imu_event_val"] = f"{event_val:.2f}"
            row["imu_impact"]    = f"{impact:.2f}"
            print(f"[IMU] {row['imu_state']}  event={event_val:.2f}  impact={impact:.2f}")

        elif ptype == "W":
            _, ts, rr = pkt
            row["ble_rr"] = "" if rr is None else f"{rr:.2f}"
            print(f"[RR] {row['ble_rr']} BrPM")

        elif ptype == "P":
            _, ts, sbp, dbp = pkt
            row["ble_sbp"] = "" if sbp is None else f"{sbp:.1f}"
            row["ble_dbp"] = "" if dbp is None else f"{dbp:.1f}"
            print(f"[BP] SBP={row['ble_sbp']}  DBP={row['ble_dbp']} mmHg")

        elif ptype == "B":  # Battery packet
            _, ts, vbat = pkt
            row["ble_vbat"] = f"{vbat:.2f}"

            v_pct = vbat_to_percent(vbat)
            row["v_percent"] = "" if v_pct is None else str(v_pct)

            print(f"[BAT] {row['ble_vbat']} V  ({row['v_percent']}%)")

        with row_lock:
            data_rows.append(row)


async def run_ble_async(stop_event: asyncio.Event):
    global ble_connected
    from bleak import BleakScanner, BleakClient

    print("Scanning for device...")
    device = None
    while device is None:
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=5.0)
        if device is None:
            print(f"  {DEVICE_NAME} not found, retrying...")

    print(f"Connecting to {DEVICE_NAME}...")
    async with BleakClient(device) as client:
        ble_connected = True
        ui.set_ble_status(True)
        print("Connected.\n")
        await client.start_notify(TX_CHAR_UUID, handle_notification)
        await stop_event.wait()
        await client.stop_notify(TX_CHAR_UUID)

    ble_connected = False
    ui.set_ble_status(False)


def ble_thread_main(stop_event: asyncio.Event, loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_ble_async(stop_event))


def on_start(initials: str) -> bool:
    global csv_path

    out_dir  = Path("tests/data")
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"integrated_{initials}.csv"

    ble_loop = asyncio.new_event_loop()
    async def make_event(): return asyncio.Event()
    stop_event = ble_loop.run_until_complete(make_event())

    ble_t = threading.Thread(target=ble_thread_main, args=(stop_event, ble_loop), daemon=True)
    ble_t.start()

    timeout, elapsed = 30, 0
    while not ble_connected and elapsed < timeout:
        time.sleep(0.5)
        elapsed += 0.5

    return ble_connected


def on_ref(value: str) -> dict:
    if not p_running:
        return {"ok": False, "display": "No active window"}
    parts = value.split()
    if len(parts) == 2:
        try:
            spo2_ref, hr_ref = float(parts[0]), float(parts[1])
            ref_queue.put((hr_ref, spo2_ref))
            print(f"[REF] SpO2={spo2_ref}  HR={hr_ref}")
            return {"ok": True, "display": f"SpO2={spo2_ref}  HR={hr_ref}"}
        except ValueError:
            pass
    return {"ok": False}

def on_tick(label: str, remaining: int):
    global current_label, p_running, current_step_idx, current_remaining, last_tick_wall

    prev_label     = current_label
    p_running      = (label != "IDLE")

    if p_running and label != prev_label:
        search_from = current_step_idx + 1 if current_step_idx >= 0 else 0
        for i in range(search_from, len(PROTOCOL_STEPS)):
            if PROTOCOL_STEPS[i][0] == label:
                current_step_idx = i
                break

    current_label     = label
    current_remaining = remaining
    last_tick_wall    = time.time()
    flush_ref_queue()

def on_done(partial: bool = False):
    flush_ref_queue()
    path = csv_path
    if partial and path:
        path = path.with_stem(path.stem + "_partial")
    if path:
        save_csv(path)


def flush_ref_queue():
    if not p_running or current_remaining <= 0:
        while not ref_queue.empty():
            ref_queue.get_nowait()
        return

    ts_time = get_protocol_time()
    while not ref_queue.empty():
        hr_ref, spo2_ref = ref_queue.get_nowait()
        row = {k: "" for k in FIELDNAMES}
        row["time"]           = ts_time
        row["activity_label"] = current_label
        row["ref_hr"]         = f"{hr_ref:.1f}"
        row["ref_spo2"]       = f"{spo2_ref:.1f}"
        with row_lock:
            data_rows.append(row)


def save_csv(path: Path):
    with row_lock:
        rows_copy = list(data_rows)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows_copy)
    print(f"\nSaved {path}  ({len(rows_copy)} rows)")


if __name__ == "__main__":
    ui = ProtocolUI(
        steps           = PROTOCOL_STEPS,
        title           = "Integrated PPG & IMU Protocol",
        ref_placeholder = "spo2 hr  e.g. 98 72",
        on_start        = on_start,
        on_ref          = on_ref,
        on_tick         = on_tick,
        on_done         = on_done,
    )
    ui.run()