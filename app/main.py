# main.py
import sys
import threading
import asyncio

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from gui.triage_gui import DashboardWindow
from ble_monitor import PacketParser, DEVICE_NAME, TX_CHAR_UUID, STATE_NAMES
from utils.ble_runner import run_ble

# This is the internal ID the GUI uses to map incoming data to a soldier.
# Set this to whatever device_id you assigned that soldier in the GUI.
DEVICE_ID = "DEV_001"


class BLEBridge(QObject):
    ppg_received = Signal(str, object, object)   # device_id, hr, spo2
    imu_received = Signal(str, str)              # device_id, motion_state
    link_status = Signal(str, str)               # device_id, status


class BLEBackend:
    def __init__(self, bridge: BLEBridge):
        self.bridge = bridge
        self.parser = PacketParser()

    def handle_notification(self, sender, data):
        self.bridge.link_status.emit(DEVICE_ID, "ACTIVE")

        for decoded in self.parser.feed(data):
            ptype = decoded[0]

            if ptype == "R":
                _, ts, hr, spo2 = decoded
                self.bridge.ppg_received.emit(DEVICE_ID, hr, spo2)

            elif ptype == "M":
                _, ts, state, event_val, impact = decoded
                state_name = STATE_NAMES.get(state, str(state))
                self.bridge.imu_received.emit(DEVICE_ID, state_name)

    async def run_ble_task(self):
        try:
            await run_ble(DEVICE_NAME, TX_CHAR_UUID, self.handle_notification)
        except Exception:
            self.bridge.link_status.emit(DEVICE_ID, "LOST")

    def start(self):
        asyncio.run(self.run_ble_task())


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = DashboardWindow()
    window.show()

    bridge = BLEBridge()
    backend = BLEBackend(bridge)

    def on_ppg(device_id, hr, spo2):
        window.handle_incoming_packet(
            device_id=device_id,
            hr=hr,
            spo2=spo2,
            link_status="ACTIVE",
        )

    def on_imu(device_id, motion_state):
        window.handle_incoming_packet(
            device_id=device_id,
            motion_state=motion_state,
            link_status="ACTIVE",
        )

    def on_link_status(device_id, status):
        window.handle_incoming_packet(
            device_id=device_id,
            link_status=status,
        )

    bridge.ppg_received.connect(on_ppg)
    bridge.imu_received.connect(on_imu)
    bridge.link_status.connect(on_link_status)

    ble_thread = threading.Thread(target=backend.start, daemon=True)
    ble_thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()