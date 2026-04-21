# ppg_serial.py
# Collect PPG data from serial and save alongside reference HR/SpO2

import os
import sys
import csv
import time
import threading
import queue
import logging
from datetime import datetime
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

import serial
from flask import Flask, jsonify, request, render_template_string
from utils.serial_parser import parse_csv

SERIAL_PORT = "COM6"
BAUD_RATE   = 115200
WINDOW      = 10.0  # seconds per window

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

PPG_OUTPUT_FILE = os.path.join(DATA_DIR, "ppg_raw_loc_a.csv")
REF_OUTPUT_FILE = os.path.join(DATA_DIR, "ppg_ref_loc_a.csv")

# (activity label, duration in seconds)
# 7-minute protocol adapted from:
# Lin et al., "A Novel Chest-Based PPG Measurement System," IEEE JTEHM, 2024
# https://pmc.ncbi.nlm.nih.gov/articles/PMC11573410/
# PROTOCOL_STEPS = [
#     ("Normal breath", 60,  "Breathe normally. Stay still."),
#     ("Deep breath",   30,  "Take slow, deep breaths."),
#     ("Normal breath", 60,  "Breathe normally. Stay still."),
#     ("Hold breath",   30,  "Hold your breath."),
#     ("Normal breath", 60,  "Breathe normally. Stay still."),
#     ("Finger tap",    30,  "Tap your fingers on a surface."),
#     ("Normal breath", 60,  "Breathe normally. Stay still."),
#     ("Swing arm",     30,  "Swing your arm back and forth."),
#     ("Normal breath", 60,  "Breathe normally. Stay still."),
# ]

# Shortened protocol for parameter selection testing
PROTOCOL_STEPS = [
    ("Normal breath", 60, "Breathe normally. Stay still."),
    ("Deep breath",   30, "Take slow, deep breaths."),
    ("Normal breath", 30, "Breathe normally. Stay still."),
    ("Hold breath",   30, "Hold your breath."),
    ("Normal breath", 30, "Breathe normally. Stay still."),
    ("Swing arm",     60, "Swing your arm back and forth."),
    ("Normal breath", 30, "Breathe normally. Stay still."),
    ("Jog in place",  60, "Jog in place at a steady pace."),
    ("Normal breath", 60, "Breathe normally. Stay still."),
]

HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PPG Collection</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, sans-serif;
    background: #0f1117;
    color: #e8eaf0;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
    padding: 40px 20px;
  }
  h1 { font-size: 1.1rem; font-weight: 500; color: #888; margin-bottom: 32px;
       letter-spacing: 0.05em; text-transform: uppercase; }

  #setup { display: flex; flex-direction: column; align-items: center; gap: 16px;
           width: 100%; max-width: 360px; }
  #setup input {
    width: 100%; padding: 12px 16px; border-radius: 8px;
    background: #1c1f2b; border: 1px solid #2e3249; color: #e8eaf0;
    font-size: 1rem; text-align: center; letter-spacing: 0.1em; text-transform: uppercase;
  }
  #setup input:focus { outline: none; border-color: #5c6bc0; }

  #main { width: 100%; max-width: 560px; display: none; flex-direction: column;
          align-items: center; gap: 24px; }

  #serial-badge {
    font-size: 0.75rem; padding: 4px 12px; border-radius: 20px;
    background: #1c1f2b; border: 1px solid #2e3249; color: #888;
  }
  #serial-badge.connected { border-color: #43a047; color: #66bb6a; }

  #step-counter { font-size: 0.8rem; color: #555; }

  #label {
    font-size: 1.6rem; font-weight: 700; letter-spacing: 0.04em;
    color: #c5cae9; text-align: center;
  }

  #instruction { font-size: 1rem; color: #9fa8da; text-align: center; min-height: 1.4em; }

  #timer-ring { position: relative; width: 160px; height: 160px; }
  #timer-ring svg { transform: rotate(-90deg); }
  #timer-ring circle.track    { fill: none; stroke: #1c1f2b; stroke-width: 10; }
  #timer-ring circle.progress {
    fill: none; stroke: #5c6bc0; stroke-width: 10;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.9s linear;
  }
  #timer-text {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.4rem; font-weight: 700; color: #e8eaf0;
  }

  .btn {
    padding: 13px 36px; border-radius: 8px; border: none;
    font-size: 1rem; font-weight: 600; cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
  }
  .btn:active { transform: scale(0.97); }
  .btn:disabled { opacity: 0.3; cursor: default; }

  #btn-start  { background: #5c6bc0; color: #fff; }
  #btn-skip   { background: #1c1f2b; color: #888; border: 1px solid #2e3249; }
  #btn-repeat { background: #1c1f2b; color: #888; border: 1px solid #2e3249; }
  #btn-row    { display: flex; gap: 12px; }

  #ref-row { display: flex; gap: 8px; width: 100%; }
  #ref-input {
    flex: 1; padding: 11px 14px; border-radius: 8px;
    background: #1c1f2b; border: 1px solid #2e3249; color: #e8eaf0;
    font-size: 0.95rem;
  }
  #ref-input:focus { outline: none; border-color: #5c6bc0; }
  #ref-input::placeholder { color: #444; }
  #ref-log {
    width: 100%; max-height: 120px; overflow-y: auto;
    font-size: 0.78rem; color: #666; display: flex; flex-direction: column; gap: 4px;
  }
  #ref-log span { color: #7986cb; }

  #sample-count { font-size: 0.78rem; color: #555; }
  #done-msg { font-size: 1.2rem; color: #66bb6a; display: none; text-align: center; }
</style>
</head>
<body>
<h1>PPG Data Collection</h1>

<div id="setup">
  <input id="initials-input" maxlength="4" placeholder="Participant initials" autofocus>
  <button class="btn" id="btn-start-session" style="background:#5c6bc0;color:#fff;width:100%">Connect &amp; Start</button>
  <div id="connect-status" style="font-size:0.8rem;color:#555;min-height:1.2em;text-align:center"></div>
</div>

<div id="main">
  <div id="serial-badge">Serial: connecting…</div>
  <div id="step-counter"></div>
  <div id="label">—</div>
  <div id="instruction"></div>

  <div id="timer-ring">
    <svg width="160" height="160" viewBox="0 0 160 160">
      <circle class="track"    cx="80" cy="80" r="70"/>
      <circle class="progress" cx="80" cy="80" r="70" id="ring-path"
              stroke-dasharray="439.8" stroke-dashoffset="439.8"/>
    </svg>
    <div id="timer-text">—</div>
  </div>

  <div id="btn-row">
    <button class="btn" id="btn-repeat">Repeat prev</button>
    <button class="btn" id="btn-start">Start</button>
    <button class="btn" id="btn-skip">Skip</button>
  </div>

  <div id="ref-row">
    <input id="ref-input" placeholder="hr spo2  e.g. 72 98" autocomplete="off">
  </div>
  <div id="ref-log"></div>
  <div id="sample-count"></div>

  <div id="done-msg">Session complete. CSV saved.</div>
</div>

<script>
const CIRCUMFERENCE = 2 * Math.PI * 70;
let pollInterval = null;

document.getElementById("btn-start-session").addEventListener("click", startSession);
document.getElementById("initials-input").addEventListener("keydown", e => {
  if (e.key === "Enter") startSession();
});

async function startSession() {
  const initials = document.getElementById("initials-input").value.trim().toUpperCase();
  if (!initials) return;
  document.getElementById("connect-status").textContent = "Opening serial port…";
  document.getElementById("btn-start-session").disabled = true;

  const res  = await fetch("/api/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initials })
  });
  const data = await res.json();

  if (data.ok) {
    document.getElementById("setup").style.display = "none";
    document.getElementById("main").style.display  = "flex";
    pollInterval = setInterval(poll, 500);
  } else {
    document.getElementById("connect-status").textContent = data.error || "Connection failed.";
    document.getElementById("btn-start-session").disabled = false;
  }
}

async function poll() {
  const s = await (await fetch("/api/state")).json();

  const badge = document.getElementById("serial-badge");
  badge.textContent = s.serial_ok ? "Serial connected" : "Serial disconnected";
  badge.className   = s.serial_ok ? "connected" : "";

  document.getElementById("step-counter").textContent =
    s.done ? "" : `Window ${s.step} / ${s.total}`;
  document.getElementById("label").textContent       = s.label       || "—";
  document.getElementById("instruction").textContent = s.instruction || "";
  document.getElementById("sample-count").textContent =
    s.running ? `${s.samples} samples collected` : "";

  const frac = s.duration > 0 ? s.remaining / s.duration : 0;
  document.getElementById("ring-path").style.strokeDashoffset = CIRCUMFERENCE * (1 - frac);
  document.getElementById("timer-text").textContent =
    s.running ? s.remaining : (s.done ? "✓" : "—");

  document.getElementById("btn-start").disabled  = s.running || s.done || !s.waiting;
  document.getElementById("btn-skip").disabled   = s.running || s.done;
  document.getElementById("btn-repeat").disabled = s.running || s.done || s.step <= 1;

  if (s.done) {
    document.getElementById("done-msg").style.display = "block";
    document.getElementById("btn-row").style.display  = "none";
    document.getElementById("ref-row").style.display  = "none";
    clearInterval(pollInterval);
  }
}

document.getElementById("btn-start").addEventListener("click",  () => sendCmd("start"));
document.getElementById("btn-skip").addEventListener("click",   () => sendCmd("skip"));
document.getElementById("btn-repeat").addEventListener("click", () => sendCmd("repeat"));

async function sendCmd(cmd) {
  await fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd })
  });
}

// Submit reference reading on Enter
document.getElementById("ref-input").addEventListener("keydown", async e => {
  if (e.key !== "Enter") return;
  const val = e.target.value.trim();
  if (!val) return;

  const res  = await fetch("/api/ref", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: val })
  });
  const data = await res.json();

  if (data.ok) {
    const entry = document.createElement("div");
    entry.innerHTML = `<span>[REF]</span> ${data.display}`;
    document.getElementById("ref-log").prepend(entry);
    e.target.value = "";
  } else {
    e.target.style.borderColor = "#e53935";
    setTimeout(() => e.target.style.borderColor = "", 600);
  }
});
</script>
</body>
</html>
"""


def now_iso():
    return datetime.now().isoformat(timespec="milliseconds")


class PPGCollector:

    def __init__(self):
        self.state = {
            "step":        0,
            "total":       len(PROTOCOL_STEPS),
            "label":       "",
            "instruction": "",
            "duration":    0,
            "remaining":   0,
            "running":     False,
            "waiting":     True,
            "done":        False,
            "serial_ok":   False,
            "samples":     0,
        }

        self.action_queue = queue.Queue()
        self.ref_queue    = queue.Queue()
        self.ser          = None
        self.ppg_writer   = None
        self.ref_writer   = None
        self._ppg_f       = None
        self._ref_f       = None

    def connect_serial(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.state["serial_ok"] = True
            return True
        except Exception as e:
            print(f"Serial error: {e}")
            return False

    def open_csv_files(self):
        self._ppg_f = open(PPG_OUTPUT_FILE, "w", newline="")
        self._ref_f = open(REF_OUTPUT_FILE, "w", newline="")
        self.ppg_writer = csv.writer(self._ppg_f)
        self.ref_writer = csv.writer(self._ref_f)
        self.ppg_writer.writerow(["timestamp", "window", "activity", "sample", "ir_raw", "red_raw"])
        self.ref_writer.writerow(["timestamp", "window", "true_hr", "true_spo2"])

    def close_csv_files(self):
        if self._ppg_f: self._ppg_f.close()
        if self._ref_f: self._ref_f.close()

    def run_protocol(self):
        self.open_csv_files()
        total = len(PROTOCOL_STEPS)
        i = 0

        while i < total:
            label, duration, instruction = PROTOCOL_STEPS[i]
            window_num = i + 1

            self.state.update({
                "step":        window_num,
                "label":       label,
                "instruction": instruction,
                "duration":    duration,
                "remaining":   duration,
                "running":     False,
                "waiting":     True,
                "samples":     0,
            })

            cmd = self.action_queue.get()

            if cmd == "skip":
                print(f"  Skipping window {window_num}: {label}")
                i += 1
                continue

            if cmd == "repeat" and i > 0:
                prev_label, prev_dur, prev_instr = PROTOCOL_STEPS[i - 1]
                print(f"\nRepeating: {prev_label} ({prev_dur}s)")
                self._run_window(window_num, prev_label + "_REPEAT", prev_dur, prev_instr)

                # Re-prompt for the current step after the repeat
                self.state.update({
                    "label":       label,
                    "instruction": instruction,
                    "remaining":   duration,
                    "waiting":     True,
                    "running":     False,
                })
                cmd = self.action_queue.get()
                if cmd == "skip":
                    print(f"  Skipping window {window_num}: {label}")
                    i += 1
                    continue

            print(f"\nWindow {window_num}/{total}  {label}  ({duration}s)")
            self._run_window(window_num, label, duration, instruction)
            print(f"  Done — {self.state['samples']} samples saved")
            i += 1

        self.state["done"] = True
        self.close_csv_files()
        if self.ser:
            self.ser.close()
        print("\nProtocol complete.")

    def _run_window(self, window_num, label, duration, instruction):
        self.state.update({
            "label":       label,
            "instruction": instruction,
            "duration":    duration,
            "remaining":   duration,
            "running":     True,
            "waiting":     False,
            "samples":     0,
        })

        self.ser.reset_input_buffer()
        start      = time.time()
        sample_idx = 0
        ref_rows   = []

        # Drain any reference readings already queued before this window started
        while not self.ref_queue.empty():
            ref_rows.append(self.ref_queue.get_nowait())

        while time.time() - start < duration:
            self.state["remaining"] = max(0, int(duration - (time.time() - start)))

            # Collect any new reference entries submitted during this window
            while not self.ref_queue.empty():
                ref_rows.append(self.ref_queue.get_nowait())

            line = self.ser.readline().decode(errors="ignore").strip()
            vals = parse_csv(line, expected_values=2)

            if vals is None:
                continue

            try:
                ir  = int(vals[0])
                red = int(vals[1])
            except:
                continue

            self.ppg_writer.writerow([
                now_iso(), window_num, label, sample_idx, ir, red
            ])
            sample_idx += 1
            self.state["samples"] = sample_idx

        # Collect any final reference entries submitted at the end
        while not self.ref_queue.empty():
            ref_rows.append(self.ref_queue.get_nowait())

        # Write all reference rows for this window
        for hr, spo2 in ref_rows:
            self.ref_writer.writerow([now_iso(), window_num, hr, spo2])

        self.state["running"] = False

    def submit_ref(self, value: str):
        parts = value.strip().split()
        if len(parts) != 2:
            return None
        try:
            hr   = float(parts[0])
            spo2 = float(parts[1])
            self.ref_queue.put((hr, spo2))
            return {"ok": True, "display": f"HR={hr}  SpO2={spo2}"}
        except ValueError:
            return None


def build_app(collector: PPGCollector) -> Flask:
    app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.logger.disabled = True

    @app.route("/")
    def index():
        return render_template_string(HTML)

    @app.route("/api/state")
    def api_state():
        return jsonify(collector.state)

    @app.route("/api/init", methods=["POST"])
    def api_init():
        if collector.state.get("started"):
            return jsonify({"ok": False, "error": "Session already started."})

        ok = collector.connect_serial()
        if not ok:
            return jsonify({"ok": False, "error": f"Could not open {SERIAL_PORT}."})

        collector.state["started"] = True
        threading.Thread(target=collector.run_protocol, daemon=True).start()
        return jsonify({"ok": True})

    @app.route("/api/command", methods=["POST"])
    def api_command():
        cmd = request.get_json().get("cmd", "")
        if cmd in ("start", "skip", "repeat"):
            collector.action_queue.put(cmd)
        return jsonify({"ok": True})

    @app.route("/api/ref", methods=["POST"])
    def api_ref():
        value  = request.get_json().get("value", "")
        result = collector.submit_ref(value)
        if result:
            return jsonify(result)
        return jsonify({"ok": False})

    return app


if __name__ == "__main__":
    collector = PPGCollector()
    app       = build_app(collector)
    print("Open http://localhost:5000 in your browser.")
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        if not collector.state["done"]:
            print("\nInterrupted — closing files.")
            collector.close_csv_files()
            if collector.ser:
                collector.ser.close()