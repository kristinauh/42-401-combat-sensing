import math
import random
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from triage_gui import DashboardWindow
from models import SoldierInfo
from theme import DEMO_MIN_UPDATE_MS, DEMO_MAX_UPDATE_MS

class DemoController:
    def __init__(self, window: DashboardWindow):
        self.window = window
        self.timer = QTimer(window)
        self.timer.timeout.connect(self.update_display_loop)

    def start(self):
        self.seed_demo_data()
        self.window.rebuild_device_mapping()
        self.window.refresh_roster_list(select_first=True)
        self.schedule_next_demo_update()

    def seed_demo_data(self):
        demo = [
            ("A-201", "Atlas", 24, "DEV007"),
            ("B-147", "Nova", 29, "DEV012"),
            ("C-052", "Echo", 33, "DEV003"),
            ("D-311", "Orion", 27, "DEV015"),
            ("E-087", "Vega", 31, "DEV021"),
            ("F-221", "Sable", 26, "DEV018"),
            ("G-118", "Rook", 35, "DEV009"),
            ("H-064", "Kite", 23, "DEV004"),
            ("I-019", "Flint", 30, "DEV031"),
            ("J-302", "Halo", 28, "DEV025"),
        ]

        for sid, name, age, device_id in demo:
            self.window.roster[sid] = SoldierInfo(name=name, age=age, device_id=device_id)
            self.window.soldier_state[sid] = self.window.make_default_state()

    def simulate_updates(self):
        if not self.window.device_to_soldier:
            return

        motion_states = ["STATIONARY", "WALKING", "RUNNING", "PRONE", "NO DATA", "IDLE_FALL"]
        link_states = ["ACTIVE", "ACTIVE", "ACTIVE", "DEGRADED", "ACTIVE"]

        device_ids = list(self.window.device_to_soldier.keys())
        num_updates = random.randint(1, min(3, len(device_ids)))
        chosen_devices = random.sample(device_ids, num_updates)

        for device_id in chosen_devices:
            soldier_id = self.window.device_to_soldier[device_id]
            state = self.window.soldier_state.setdefault(
                soldier_id, self.window.make_default_state()
            )

            info = self.window.roster.get(soldier_id)
            age = info.age if info and info.age is not None else 25

            max_hr = 220 - age
            zone_choice = random.choice([1, 2, 3, 4, 5])

            if zone_choice == 1:
                hr_low, hr_high = int(max_hr * 0.50), int(max_hr * 0.60)
            elif zone_choice == 2:
                hr_low, hr_high = int(max_hr * 0.60), int(max_hr * 0.70)
            elif zone_choice == 3:
                hr_low, hr_high = int(max_hr * 0.70), int(max_hr * 0.80)
            elif zone_choice == 4:
                hr_low, hr_high = int(max_hr * 0.80), int(max_hr * 0.90)
            else:
                hr_low, hr_high = int(max_hr * 0.90), int(max_hr * 0.98)

            hr_low = max(45, hr_low)
            hr_high = max(hr_low, hr_high)

            new_hr = random.randint(hr_low, hr_high)
            new_motion = random.choice(motion_states)
            new_spo2 = max(87, min(100, state["spo2"] + random.randint(-1, 1)))
            new_link = random.choice(link_states)

            if new_motion == "RUNNING" and zone_choice <= 2:
                new_hr = random.randint(int(max_hr * 0.70), int(max_hr * 0.88))
            if new_motion == "STATIONARY" and zone_choice >= 5:
                new_hr = random.randint(int(max_hr * 0.65), int(max_hr * 0.85))

            self.window.handle_incoming_packet(
                device_id=device_id,
                hr=new_hr,
                spo2=new_spo2,
                motion_state=new_motion,
                link_status=new_link,
            )

    def schedule_next_demo_update(self):
        interval = random.randint(DEMO_MIN_UPDATE_MS, DEMO_MAX_UPDATE_MS)
        self.timer.start(interval)

    def update_display_loop(self):
        self.timer.stop()
        self.simulate_updates()
        self.window.refresh_ui_elements()
        self.schedule_next_demo_update()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = DashboardWindow()
    demo = DemoController(window)
    demo.start()

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()