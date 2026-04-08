# main.py
import sys
import os

# Ensure the app directory is on the path so all local modules resolve correctly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

import threading
import asyncio

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from gui.triage_gui import DashboardWindow
from ble_monitor import PacketParser, DEVICE_NAME, TX_CHAR_UUID, STATE_NAMES
from utils.ble_runner import run_ble

# Must match the device_id assigned to this soldier in the GUI roster
DEVICE_ID = "DEV_001"

# How often the UI refreshes independent of incoming BLE data (ms)
UI_REFRESH_INTERVAL_MS = 1000


class BLEBridge(QObject):
    # Qt signals are used to safely pass data from the BLE thread to the GUI thread
    ppg_received = Signal(str, object, object)  # device_id, hr, spo2
    imu_received = Signal(str, str)             # device_id, motion_state
    bat_received = Signal(str, float)           # device_id, vbat
    rr_received = Signal(str, float)
    bp_received = Signal(str, object, object)  # device_id, sbp, dbp
    link_changed = Signal(str, str)             # device_id, "ACTIVE" | "LOST"


class BLEBackend:
    def __init__(self, bridge: BLEBridge):
        self.bridge = bridge
        self.parser = PacketParser()

    def _on_reconnect(self):
        # Reset parser on reconnect so stale buffer bytes from the previous
        # session don't corrupt the first packets of the new one
        self.parser = PacketParser()
        self.bridge.link_changed.emit(DEVICE_ID, "ACTIVE")

    def _on_disconnect(self):
        self.bridge.link_changed.emit(DEVICE_ID, "LOST")

    def handle_notification(self, sender, data):
        for decoded in self.parser.feed(data):
            ptype = decoded[0]

            if ptype == "R":
                _, ts, hr, spo2 = decoded
                hr_str = "---" if hr is None else f"{hr:.2f}"
                spo2_str = "---" if spo2 is None else f"{spo2:.2f}"
                print(f"[BLE RX][PPG] hr={hr_str} bpm spo2={spo2_str} %")
                self.bridge.ppg_received.emit(DEVICE_ID, hr, spo2)

            elif ptype == "M":
                _, ts, state, event_val, impact = decoded
                state_name = STATE_NAMES.get(state, str(state))
                print(f"[BLE RX][IMU] state={state_name} event={event_val:.2f} impact={impact:.2f}")
                self.bridge.imu_received.emit(DEVICE_ID, state_name)

            elif ptype == "B":
                _, ts, vbat = decoded
                print(f"[BLE RX][BAT] vbat={vbat:.2f} V")
                self.bridge.bat_received.emit(DEVICE_ID, vbat)
            
            elif ptype == "W":
                _, ts, rr = decoded
                if rr is not None:
                    print(f"[BLE RX][RR] rr={rr:.1f} BrPM")
                    self.bridge.rr_received.emit(DEVICE_ID, rr)

            elif ptype == "P":
                _, ts, sbp, dbp = decoded
                print(f"[BLE RX][BP] sbp={sbp} mmHg dbp={dbp} mmHg")
                self.bridge.bp_received.emit(DEVICE_ID, sbp, dbp)

    async def _run(self):
        await run_ble(
            DEVICE_NAME,
            TX_CHAR_UUID,
            self.handle_notification,
            on_reconnect=self._on_reconnect,
            on_disconnect=self._on_disconnect,
        )

    def start(self):
        # Blocking call — intended to run in its own thread
        asyncio.run(self._run())


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = DashboardWindow()
    window.show()

    bridge = BLEBridge()
    backend = BLEBackend(bridge)

    # Connect BLE signals to GUI handlers — Qt queues these across threads automatically
    bridge.ppg_received.connect(
        lambda device_id, hr, spo2: window.handle_incoming_packet(
            device_id=device_id,
            hr=hr,
            spo2=spo2,
        )
    )
    bridge.imu_received.connect(
        lambda device_id, motion_state: window.handle_incoming_packet(
            device_id=device_id,
            motion_state=motion_state,
        )
    )
    bridge.bat_received.connect(
        lambda device_id, vbat: window.handle_incoming_packet(
            device_id=device_id,
            vbat=vbat,
        )
    )
    bridge.rr_received.connect(
        lambda device_id, rr: window.handle_incoming_packet(
            device_id=device_id,
            rr=rr,
        )
    )
    bridge.bp_received.connect(
        lambda device_id, sbp, dbp: window.handle_incoming_packet(
            device_id=device_id,
            sbp=sbp,
            dbp=dbp,
        )
    )
    bridge.link_changed.connect(
        lambda device_id, status: window.handle_incoming_packet(
            device_id=device_id,
            link_status=status,
        )
    )

    # Periodic timer keeps the "X seconds ago" counter and live-pulse dot
    # ticking even when no BLE packets are arriving
    refresh_timer = QTimer()
    refresh_timer.setInterval(UI_REFRESH_INTERVAL_MS)
    refresh_timer.timeout.connect(window.refresh_ui_elements)
    refresh_timer.start()

    # BLE runs in a background daemon thread so it doesn't block the Qt event loop
    ble_thread = threading.Thread(target=backend.start, daemon=True)
    ble_thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()