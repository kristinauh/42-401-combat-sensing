# triage_gui.py
import csv
import math
import os
import sys

# Add both the gui folder and app folder to path so local modules resolve correctly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, CURRENT_DIR)
sys.path.insert(0, APP_DIR)

import time
from typing import Dict, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.models import SoldierInfo, calculate_hr_zone, display_motion_label
from theme import (
    ACCENT,
    ACCENT_HOVER,
    BG,
    BORDER,
    DIVIDER,
    LIVE,
    MAX_DISPLAYED_SOLDIERS,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_DIM,
    TEXT_SOFT,
)
from widgets import AddSoldierDialog, SoldierCard

# Alert thresholds — adjust these to tune sensitivity
SPO2_MONITOR_THRESHOLD = 95       # SpO2 below this → MONITOR after delay
SPO2_CRITICAL_THRESHOLD = 90      # SpO2 below this → CRITICAL after delay
SPO2_ALERT_DURATION_SEC = 30      # How long SpO2 must be low before flagging
FALL_CRITICAL_DURATION_SEC = 60   # Seconds person must be still after fall → CRITICAL


class DashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tactical Triage Monitor")

        # Size the window relative to screen size with sensible min/max bounds
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None

        if avail:
            win_w = min(1360, max(980, avail.width() - 40))
            win_h = min(860, max(620, avail.height() - 40))
            self.resize(win_w, win_h)

            # Minimum size that supports 5–8 panels without clipping
            self.setMinimumSize(1260, 820)

            x = avail.x() + (avail.width() - win_w) // 2
            y = avail.y() + (avail.height() - win_h) // 2
            self.move(x, y)
        else:
            self.resize(1200, 760)
            self.setMinimumSize(900, 560)

        # Core data stores
        self.roster: Dict[str, SoldierInfo] = {}            # soldier_id → SoldierInfo
        self.device_to_soldier: Dict[str, str] = {}         # device_id → soldier_id
        self.soldier_state: Dict[str, dict] = {}            # soldier_id → live state dict
        self.card_widgets: Dict[str, SoldierCard] = {}      # soldier_id → card widget
        self.selected_ids: List[str] = []                   # currently displayed soldier IDs
        self.live_pulse_on = True                           # toggled each refresh for pulse animation

        self._build_ui()
        self._apply_styles()
        self.refresh_roster_list(select_first=False)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(10)

        roster_title = QLabel("ROSTER")
        roster_title.setStyleSheet(f"color: {TEXT}; font-weight: 800; font-size: 13px;")
        sidebar_layout.addWidget(roster_title)

        roster_desc = QLabel("Import personnel or add them manually.")
        roster_desc.setWordWrap(True)
        roster_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        sidebar_layout.addWidget(roster_desc)

        self.import_btn = QPushButton("Import CSV")
        self.import_btn.clicked.connect(self.load_roster_csv)
        self.import_btn.setObjectName("primaryButton")
        sidebar_layout.addWidget(self.import_btn)

        self.add_btn = QPushButton("Add Soldier")
        self.add_btn.clicked.connect(self.open_add_soldier_dialog)
        self.add_btn.setObjectName("secondaryButton")
        sidebar_layout.addWidget(self.add_btn)

        self.deselect_btn = QPushButton("Deselect All")
        self.deselect_btn.clicked.connect(self.deselect_all)
        self.deselect_btn.setObjectName("secondaryButton")
        sidebar_layout.addWidget(self.deselect_btn)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {DIVIDER}; border: none;")
        sidebar_layout.addWidget(divider)

        select_label = QLabel("SELECT IDS")
        select_label.setStyleSheet(f"color: {TEXT_SOFT}; font-weight: 800; font-size: 12px;")
        sidebar_layout.addWidget(select_label)

        # Multi-select list — selecting items here triggers card rendering
        self.soldier_list = QListWidget()
        self.soldier_list.setSelectionMode(QListWidget.MultiSelection)
        self.soldier_list.itemSelectionChanged.connect(self.on_roster_select)
        sidebar_layout.addWidget(self.soldier_list, 1)

        limit_label = QLabel(f"Display limit: {MAX_DISPLAYED_SOLDIERS}")
        limit_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        sidebar_layout.addWidget(limit_label)

        # Main panel
        self.main_panel = QFrame()
        self.main_panel.setObjectName("mainPanel")

        main_layout = QVBoxLayout(self.main_panel)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        title = QLabel("TRIAGE DASHBOARD")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 24px; font-weight: 900; letter-spacing: 1px;"
        )
        subtitle = QLabel("Live monitoring view for selected personnel")
        subtitle.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        # Pulsing dot in the header to indicate live data flow
        live_row = QHBoxLayout()
        live_row.setSpacing(5)

        self.pulse_dot = QLabel("●")
        self.pulse_dot.setStyleSheet(f"color: {LIVE}; font-size: 14px; font-weight: 800;")
        self.live_label = QLabel("LIVE")
        self.live_label.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 11px; font-weight: 800;")

        live_row.addWidget(self.pulse_dot)
        live_row.addWidget(self.live_label)
        header.addLayout(live_row)

        main_layout.addLayout(header)

        # Shown only when no soldiers are selected
        self.empty_label = QLabel("Select up to eight IDs from the roster.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")

        # Grid that holds the soldier cards — rebuilt whenever selection changes
        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(10)
        self.cards_layout.setVerticalSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.cards_container)

        main_layout.addWidget(self.empty_label)
        main_layout.addWidget(self.scroll, 1)

        root.addWidget(self.sidebar)
        root.addWidget(self.main_panel, 1)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BG};
                color: {TEXT};
                font-family: Bahnschrift, Segoe UI, Arial;
            }}

            QFrame#sidebar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SURFACE_2},
                    stop:1 {SURFACE}
                );
                border: 1px solid {BORDER};
                border-radius: 16px;
            }}

            QFrame#mainPanel {{
                background: transparent;
                border: none;
            }}

            QListWidget {{
                background: {BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 4px;
                color: {TEXT};
                font-size: 13px;
                outline: none;
            }}

            QListWidget::item {{
                padding: 9px 10px;
                border-radius: 8px;
                margin: 2px 0;
            }}

            QListWidget::item:selected {{
                background: #16283d;
                color: {TEXT};
                border: 1px solid {ACCENT};
            }}

            QPushButton#primaryButton {{
                background: {ACCENT};
                color: #07111d;
                border: none;
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 800;
                font-size: 12px;
                text-align: center;
            }}

            QPushButton#primaryButton:hover {{
                background: {ACCENT_HOVER};
            }}

            QPushButton#secondaryButton {{
                background: #132033;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 700;
                font-size: 12px;
                text-align: center;
            }}

            QPushButton#secondaryButton:hover {{
                background: #192941;
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}
        """)

    def make_default_state(self):
        # Used when a soldier is added before any BLE data has arrived
        return {
            "hr": 70,
            "spo2": 98,
            "motion_state": "IDLE_FALL",
            "fall_detected": False,
            "last_motion_time": time.time(),
            "data_link_status": "ACTIVE",
            "spo2_low_since": None,       # Timestamp when SpO2 first dropped below monitor threshold
            "fall_detected_since": None,  # Timestamp when a confirmed fall was first seen
        }

    def rebuild_device_mapping(self):
        # Rebuild the device_id → soldier_id lookup used by handle_incoming_packet
        self.device_to_soldier.clear()
        for sid, info in self.roster.items():
            device_id = str(info.device_id).strip()
            if device_id:
                self.device_to_soldier[device_id] = sid

    def refresh_roster_list(self, select_first=False, selected_ids=None):
        if selected_ids is None:
            selected_ids = []

        # Block signals while rebuilding to avoid triggering on_roster_select mid-update
        self.soldier_list.blockSignals(True)
        self.soldier_list.clear()

        roster_ids = list(self.roster.keys())
        for sid in roster_ids:
            item = QListWidgetItem(f"{sid}  |  {self.roster[sid].name}")
            item.setData(Qt.UserRole, sid)
            self.soldier_list.addItem(item)

        if select_first and roster_ids:
            # Auto-select up to the display limit on first load
            limit = min(MAX_DISPLAYED_SOLDIERS, len(roster_ids))
            for i in range(limit):
                self.soldier_list.item(i).setSelected(True)
        else:
            for i in range(self.soldier_list.count()):
                item = self.soldier_list.item(i)
                sid = item.data(Qt.UserRole)
                item.setSelected(sid in selected_ids)

        self.soldier_list.blockSignals(False)
        self.on_roster_select()

    def deselect_all(self):
        self.soldier_list.blockSignals(True)
        for i in range(self.soldier_list.count()):
            self.soldier_list.item(i).setSelected(False)
        self.soldier_list.blockSignals(False)
        self.selected_ids = []
        self.render_cards()

    def open_add_soldier_dialog(self):
        dlg = AddSoldierDialog(self)

        # Centre the dialog over the parent window
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            dlg_w = min(460, max(360, avail.width() - 80))
            dlg_h = min(360, max(280, avail.height() - 80))
            dlg.resize(dlg_w, dlg_h)

            parent_geo = self.frameGeometry()
            x = parent_geo.center().x() - dlg_w // 2
            y = parent_geo.center().y() - dlg_h // 2

            x = max(avail.left(), min(x, avail.right() - dlg_w))
            y = max(avail.top(), min(y, avail.bottom() - dlg_h))
            dlg.move(x, y)

        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result_data
        sid = data["sid"]
        name = data["name"]
        age = data["age"]
        device_id = data["device_id"]

        if sid in self.roster:
            QMessageBox.warning(self, "Duplicate Soldier ID", f"Soldier ID '{sid}' already exists.")
            return

        if device_id in self.device_to_soldier:
            QMessageBox.warning(self, "Duplicate Device ID", f"Device ID '{device_id}' is already assigned.")
            return

        current_selected = self.selected_ids[:]

        self.roster[sid] = SoldierInfo(name=name, age=age, device_id=device_id)
        self.soldier_state[sid] = self.make_default_state()
        self.rebuild_device_mapping()

        # Auto-select the new soldier if there's room in the display
        if len(current_selected) < MAX_DISPLAYED_SOLDIERS:
            current_selected.append(sid)

        self.refresh_roster_list(selected_ids=current_selected)

    def load_roster_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select roster CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return

        try:
            new_roster = {}
            seen_devices = set()

            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Support multiple common column name variants
                    sid = (row.get("soldier_id") or row.get("id") or "").strip()
                    name = (row.get("name") or row.get("callsign") or sid).strip()
                    device_id = (
                        row.get("device_id") or row.get("DeviceID") or row.get("device") or ""
                    ).strip()
                    age_raw = str(row.get("age") or row.get("Age") or row.get("AGE") or "").strip()

                    if not sid:
                        continue
                    if not device_id:
                        raise ValueError(f"Missing device_id for soldier '{sid}'.")

                    if device_id in seen_devices:
                        raise ValueError(f"Duplicate device_id found in CSV: '{device_id}'")
                    seen_devices.add(device_id)

                    age = None
                    if age_raw:
                        try:
                            age = int(float(age_raw))
                        except ValueError:
                            age = None

                    new_roster[sid] = SoldierInfo(name=name, age=age, device_id=device_id)

            if not new_roster:
                raise ValueError("No valid rows found. Expected soldier_id/id and device_id columns.")

            self.roster = new_roster
            # Preserve existing live state for soldiers that were already loaded
            self.soldier_state = {
                sid: self.soldier_state.get(sid, self.make_default_state())
                for sid in self.roster
            }
            self.rebuild_device_mapping()
            self.refresh_roster_list(selected_ids=[])

        except Exception as e:
            QMessageBox.critical(self, "CSV Import Failed", str(e))

    def on_roster_select(self):
        items = self.soldier_list.selectedItems()
        selected_ids = [item.data(Qt.UserRole) for item in items]

        # Enforce display limit — deselect the last item if over the cap
        if len(selected_ids) > MAX_DISPLAYED_SOLDIERS:
            self.soldier_list.blockSignals(True)
            items[-1].setSelected(False)
            self.soldier_list.blockSignals(False)
            QMessageBox.information(
                self,
                "Display Limit",
                f"You can display up to {MAX_DISPLAYED_SOLDIERS} soldiers at once.",
            )
            selected_ids = [item.data(Qt.UserRole) for item in self.soldier_list.selectedItems()]

        self.selected_ids = selected_ids
        self.render_cards()

    def get_grid_columns(self, count):
        # Column count determines card size — fewer cards = larger cards
        if count <= 1:
            return 1
        if count == 2:
            return 2
        if count <= 4:
            return 2
        return 4

    def get_scale_name(self, count):
        # Scale name passed to each card so it can adjust font sizes accordingly
        if count == 1:
            return "group_1"
        if count == 2:
            return "group_2"
        if 3 <= count <= 4:
            return "group_3_4"
        return "group_5_8"

    def clear_cards(self):
        # Remove all card widgets from the grid before rebuilding
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.card_widgets.clear()

    def render_cards(self):
        self.clear_cards()

        if not self.selected_ids:
            self.empty_label.show()
            return

        self.empty_label.hide()

        count = len(self.selected_ids)
        cols = self.get_grid_columns(count)
        rows = math.ceil(count / cols)
        scale_name = self.get_scale_name(count)

        # Reset all stretch factors before applying new ones
        for i in range(6):
            self.cards_layout.setColumnStretch(i, 0)
            self.cards_layout.setRowStretch(i, 0)

        for c in range(cols):
            self.cards_layout.setColumnStretch(c, 1)
        for r in range(rows):
            self.cards_layout.setRowStretch(r, 1)

        for idx, sid in enumerate(self.selected_ids):
            card = SoldierCard(sid, self.roster[sid])
            card.apply_scale(scale_name)
            card.clicked.connect(self.toggle_card_selection)

            row = idx // cols
            col = idx % cols
            self.cards_layout.addWidget(card, row, col)
            self.card_widgets[sid] = card

        self.refresh_ui_elements()

    def toggle_card_selection(self, sid):
        # Clicking a card toggles its selection in the sidebar list
        for i in range(self.soldier_list.count()):
            item = self.soldier_list.item(i)
            if item.data(Qt.UserRole) == sid:
                item.setSelected(not item.isSelected())
                break
        self.on_roster_select()

    def resizeEvent(self, event):
        # Re-render cards on window resize so layout stays correct
        super().resizeEvent(event)
        self.render_cards()

    def get_status_for_state(self, state):
        spo2 = state.get("spo2", 100)
        motion = state.get("motion_state", "")
        link = state.get("data_link_status", "ACTIVE")
        spo2_low_since = state.get("spo2_low_since")
        fall_detected_since = state.get("fall_detected_since")
        now = time.time()

        # BLE connection dropped — driven by ble_runner.py on_disconnect
        if link == "LOST":
            return "SIGNAL LOST", "LOST"

        # How long SpO2 has been below the monitor threshold
        spo2_low_duration = (now - spo2_low_since) if spo2_low_since else 0

        # How long since a confirmed fall was first detected
        fall_duration = (now - fall_detected_since) if fall_detected_since else 0

        # CRITICAL: SpO2 critically low for extended period
        if spo2 < SPO2_CRITICAL_THRESHOLD and spo2_low_duration >= SPO2_ALERT_DURATION_SEC:
            return "CRITICAL", "CRITICAL"

        # CRITICAL: person has been still on the ground for too long after a fall
        if motion == "STATIONARY_POST_FALL" and fall_duration >= FALL_CRITICAL_DURATION_SEC:
            return "CRITICAL", "CRITICAL"

        # MONITOR: SpO2 low for extended period but not yet critical
        if spo2 < SPO2_MONITOR_THRESHOLD and spo2_low_duration >= SPO2_ALERT_DURATION_SEC:
            return "MONITOR", "MONITOR"

        # MONITOR: fall confirmed — watch until person gets up or escalates
        if motion in ("DETECTED_FALL", "STATIONARY_POST_FALL"):
            return "MONITOR", "MONITOR"

        # All active motion states are stable — person is moving normally
        return "STABLE", "STABLE"

    def refresh_ui_elements(self):
        # Toggle pulse dot color each call to create a blinking animation
        self.live_pulse_on = not self.live_pulse_on
        live_color = LIVE if self.live_pulse_on else TEXT_DIM
        self.pulse_dot.setStyleSheet(f"color: {live_color}; font-size: 14px; font-weight: 800;")

        for sid, card in self.card_widgets.items():
            state = self.soldier_state.get(sid, {})
            info = self.roster.get(sid)

            status_text, status_kind = self.get_status_for_state(state)
            hr_val = state.get("hr", "--")
            spo2_val = state.get("spo2", "--")
            motion_text = display_motion_label(state.get("motion_state"))
            link_text = state.get("data_link_status", "--")
            last_move_sec = max(0, int(time.time() - state.get("last_motion_time", time.time())))
            age_val = info.age if info else None
            hr_zone_text = calculate_hr_zone(age_val, hr_val)

            card.set_values(
                "-- bpm" if hr_val == "--" else f"{hr_val} bpm",
                hr_zone_text,
                "--%" if spo2_val == "--" else f"{spo2_val}%",
                motion_text,
                link_text,
                f"{last_move_sec}s ago",
            )
            card.set_hero_alerts(hr_val, spo2_val)
            card.set_status(status_text, status_kind)
            card.set_selected(sid in self.selected_ids)

    def update_soldier_data(self, soldier_id, **kwargs):
        if soldier_id not in self.soldier_state:
            self.soldier_state[soldier_id] = self.make_default_state()

        state = self.soldier_state[soldier_id]
        for key, value in kwargs.items():
            state[key] = value
            # Update last_motion_time for active motion states only
            if key == "motion_state" and value in ("WALKING", "RUNNING", "JUMPING_OR_QUICK_SIT"):
                state["last_motion_time"] = time.time()

        # Track how long SpO2 has been below the monitor threshold
        spo2 = state.get("spo2", 100)
        if spo2 < SPO2_MONITOR_THRESHOLD:
            if state.get("spo2_low_since") is None:
                state["spo2_low_since"] = time.time()
        else:
            state["spo2_low_since"] = None  # Reset if SpO2 recovers

        # Track how long since a confirmed fall was first detected
        motion = state.get("motion_state", "")
        if motion in ("DETECTED_FALL", "STATIONARY_POST_FALL"):
            if state.get("fall_detected_since") is None:
                state["fall_detected_since"] = time.time()
        else:
            state["fall_detected_since"] = None  # Reset once person is moving again

    def handle_incoming_packet(
        self,
        device_id,
        hr=None,
        spo2=None,
        motion_state=None,
        link_status="ACTIVE",
    ):
        if not device_id:
            return

        # Look up which soldier this device belongs to
        soldier_id = self.device_to_soldier.get(device_id)
        if soldier_id is None:
            return  # Unknown device — not in the current roster

        updates = {"data_link_status": link_status}
        if hr is not None:
            updates["hr"] = hr
        if spo2 is not None:
            updates["spo2"] = spo2
        if motion_state is not None:
            updates["motion_state"] = motion_state
            updates["fall_detected"] = (motion_state in ("DETECTED_FALL", "STATIONARY_POST_FALL"))

        self.update_soldier_data(soldier_id, **updates)
        self.refresh_ui_elements()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DashboardWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()