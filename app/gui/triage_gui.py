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

from injury_classification import InjuryClassifier

# Triage configuration
PATTERN_PERSIST_SEC = 15            # hemorrhage / pneumothorax / SI patterns
FALL_CRITICAL_DURATION_SEC = 60     # still on ground post-fall -> CRITICAL

# "Normal" baselines
SBP_NORMAL_FLOOR = 100   # SBP below this counts as "decreased" in patterns
SPO2_NORMAL_FLOOR = 96   # SpO2 below this counts as "dropping" in patterns


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
            self.setMinimumSize(1260, 820)

            x = avail.x() + (avail.width() - win_w) // 2
            y = avail.y() + (avail.height() - win_h) // 2
            self.move(x, y)
        else:
            self.resize(1200, 760)
            self.setMinimumSize(900, 560)

        # Core data stores
        self.roster: Dict[str, SoldierInfo] = {}
        self.device_to_soldier: Dict[str, str] = {}
        self.soldier_state: Dict[str, dict] = {}
        self.card_widgets: Dict[str, SoldierCard] = {}
        self.selected_ids: List[str] = []
        self.live_pulse_on = True
        self.last_battery_pct = None

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

        self.empty_label = QLabel("Select up to eight IDs from the roster.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")

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
        return {
            "hr": None,
            "spo2": None,
            "motion_state": None,
            "fall_detected": False,
            "last_motion_time": time.time(),
            "data_link_status": "ACTIVE",
            "vbat": None,
            "rr": None,
            "sbp": None,
            "dbp": None,
            "imu_impact":None,

            # Persistence timers
            "hemorrhage_monitor_since": None,
            "hemorrhage_critical_since": None,
            "pneumo_monitor_since": None,
            "pneumo_critical_since": None,
            "shock_index_monitor_since": None,
            "shock_index_critical_since": None,
            "fall_detected_since": None,

            # Injury classifier (teammate's module)
            "classifier": InjuryClassifier(),
            "injury_probs": {},
        }

    def rebuild_device_mapping(self):
        self.device_to_soldier.clear()
        for sid, info in self.roster.items():
            device_id = str(info.device_id).strip()
            if device_id:
                self.device_to_soldier[device_id] = sid

    def refresh_roster_list(self, select_first=False, selected_ids=None):
        if selected_ids is None:
            selected_ids = []

        self.soldier_list.blockSignals(True)
        self.soldier_list.clear()

        roster_ids = list(self.roster.keys())
        for sid in roster_ids:
            item = QListWidgetItem(f"{sid}  |  {self.roster[sid].name}")
            item.setData(Qt.UserRole, sid)
            self.soldier_list.addItem(item)

        if select_first and roster_ids:
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
        if count <= 1:
            return 1
        if count == 2:
            return 2
        if count <= 4:
            return 2
        return 4

    def get_scale_name(self, count):
        if count == 1:
            return "group_1"
        if count == 2:
            return "group_2"
        if 3 <= count <= 4:
            return "group_3_4"
        return "group_5_8"

    def clear_cards(self):
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
        for i in range(self.soldier_list.count()):
            item = self.soldier_list.item(i)
            if item.data(Qt.UserRole) == sid:
                item.setSelected(not item.isSelected())
                break
        self.on_roster_select()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_cards()

    # Triage status engine - multi-vital injury pattern matching
    # Patterns derived from:
    #   - ATLS hemorrhage classification (Classes I–IV)
    #   - Tension pneumothorax progression timeline
    #   - Shock index literature (HR / SBP)
    @staticmethod
    def _persisted(since_ts, required_sec):
        """Return True if the condition has been active for at least
        *required_sec* seconds."""
        if since_ts is None:
            return False
        return (time.time() - since_ts) >= required_sec

    def _check_injury_patterns(self, state):
        """Evaluate multi-vital injury patterns against the current state.

        Returns a dict of pattern_name -> bool indicating whether each
        pattern's vital criteria are currently met (ignoring persistence).
        """
        hr = state.get("hr")
        spo2 = state.get("spo2")
        rr = state.get("rr")
        sbp = state.get("sbp")
        motion = state.get("motion_state") or ""

        def _have(*vals):
            return all(v is not None for v in vals)

        bp_decreased = sbp is not None and sbp < SBP_NORMAL_FLOOR
        spo2_dropping = spo2 is not None and spo2 < SPO2_NORMAL_FLOOR

        patterns = {}

        # Hemorrhage (ATLS classification)
        # Class II - blood loss 750–1500 mL (15–30%)
        # HR 100–120, BP decreased, RR 20–30
        patterns["hemorrhage_monitor"] = (
            _have(hr, sbp, rr)
            and 100 <= hr <= 120
            and bp_decreased
            and 20 <= rr <= 30
        )

        # Class III–IV - blood loss > 1500 mL (> 30%)
        # HR > 120, BP decreased, RR > 30
        patterns["hemorrhage_critical"] = (
            _have(hr, sbp, rr)
            and hr > 120
            and bp_decreased
            and rr > 30
        )

        # Pneumothorax
        # Early - elevated HR, rising RR, SpO2 starting to drop
        patterns["pneumo_monitor"] = (
            _have(hr, rr, spo2)
            and hr >= 110
            and rr >= 25
            and spo2_dropping
        )

        # Late / tension - very high HR, high RR, SpO2 critically low,
        # BP crashing
        patterns["pneumo_critical"] = (
            _have(hr, rr, spo2, sbp)
            and hr >= 140
            and rr > 30
            and spo2 < 90
            and sbp < 80
        )

        # Shock index (HR / SBP)
        # SI 0.9+ with at least one other abnormal vital -> MONITOR
        # SI 1.0+ with at least one other abnormal vital -> CRITICAL
        if _have(hr, sbp) and sbp > 0:
            si = hr / sbp
            other_abnormal = (
                (rr is not None and (rr >= 22 or rr <= 10))
                or (spo2 is not None and spo2 < SPO2_NORMAL_FLOOR)
                or bp_decreased
            )
            patterns["shock_index_monitor"] = si >= 0.9 and other_abnormal
            patterns["shock_index_critical"] = si >= 1.0 and other_abnormal
        else:
            patterns["shock_index_monitor"] = False
            patterns["shock_index_critical"] = False

        # Fall / immobility
        # DETECTED_FALL or STATIONARY_POST_FALL -> immediate MONITOR
        # Prolonged STATIONARY_POST_FALL -> CRITICAL (via persistence timer)
        patterns["fall_monitor"] = motion in ("DETECTED_FALL", "STATIONARY_POST_FALL")
        patterns["fall_critical"] = motion == "STATIONARY_POST_FALL"

        return patterns

    def get_status_for_state(self, state):
        link = state.get("data_link_status", "ACTIVE")

        if link == "LOST":
            return "SIGNAL LOST", "LOST"

        # Check persisted critical patterns
        critical_checks = [
            ("hemorrhage_critical_since", PATTERN_PERSIST_SEC),
            ("pneumo_critical_since", PATTERN_PERSIST_SEC),
            ("shock_index_critical_since", PATTERN_PERSIST_SEC),
            ("fall_detected_since", FALL_CRITICAL_DURATION_SEC),
        ]
        for timer_key, duration in critical_checks:
            if self._persisted(state.get(timer_key), duration):
                return "CRITICAL", "CRITICAL"

        # Check persisted monitor patterns
        monitor_checks = [
            ("hemorrhage_monitor_since", PATTERN_PERSIST_SEC),
            ("pneumo_monitor_since", PATTERN_PERSIST_SEC),
            ("shock_index_monitor_since", PATTERN_PERSIST_SEC),
            ("fall_detected_since", 0),  # fall is immediately MONITOR
        ]
        for timer_key, duration in monitor_checks:
            if self._persisted(state.get(timer_key), duration):
                return "MONITOR", "MONITOR"

        return "STABLE", "STABLE"

    def get_battery_display(self, vbat_val):
        if vbat_val is None:
            return "--", TEXT_DIM

        if vbat_val >= 3.5:
            pct = int(7 + (vbat_val - 3.5) / (4.2 - 3.5) * 93)
        else:
            pct = int((vbat_val - 2.5) / (3.5 - 2.5) * 7)

        pct = max(0, min(100, pct))

        if self.last_battery_pct is None:
            self.last_battery_pct = pct
        else:
            self.last_battery_pct = int(0.8 * self.last_battery_pct + 0.2 * pct)

        p = self.last_battery_pct
        if p > 75:
            return "█████", "#4caf50"
        elif p > 50:
            return "████░", "#8bc34a"
        elif p > 25:
            return "███░░", "#f5a623"
        elif p > 10:
            return "██░░░", "#e05252"
        else:
            return "█░░░░", "#e05252"

    def refresh_ui_elements(self):
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
            vbat_val = state.get("vbat")
            rr_val = state.get("rr")
            sbp_val = state.get("sbp")
            dbp_val = state.get("dbp")
            bp_text = "--/--" if (sbp_val is None or dbp_val is None) else f"{sbp_val:.0f}/{dbp_val:.0f}"
            rr_text = "--" if rr_val is None else f"{rr_val:.0f}"

            vbat_text, vbat_color = self.get_battery_display(vbat_val)
            
            injury_probs = state.get("injury_probs") or {}
            card.set_values(
                "-- bpm" if hr_val is None else f"{hr_val} bpm",
                hr_zone_text,
                "--%" if spo2_val is None else f"{spo2_val}%",
                rr_text,
                bp_text,
                motion_text,
                link_text,
                f"{last_move_sec}s ago",
                vbat_text,
                vbat_color,
                injury_probs=injury_probs,
            )
            card.set_hero_alerts(hr_val, spo2_val)
            card.set_status(status_text, status_kind)
            card.set_selected(sid in self.selected_ids)

    # Persistence timer management
    def _update_persistence_timers(self, state):
        now = time.time()
        patterns = self._check_injury_patterns(state)

        # Map pattern names -> state timer keys (excluding fall, handled below)
        timer_map = {
            "hemorrhage_monitor":   "hemorrhage_monitor_since",
            "hemorrhage_critical":  "hemorrhage_critical_since",
            "pneumo_monitor":       "pneumo_monitor_since",
            "pneumo_critical":      "pneumo_critical_since",
            "shock_index_monitor":  "shock_index_monitor_since",
            "shock_index_critical": "shock_index_critical_since",
        }

        for pattern_name, timer_key in timer_map.items():
            if patterns.get(pattern_name, False):
                if state.get(timer_key) is None:
                    state[timer_key] = now
            else:
                state[timer_key] = None

        # Fall uses a single shared timer for both monitor and critical tiers
        fall_active = patterns.get("fall_monitor", False)
        if fall_active:
            if state.get("fall_detected_since") is None:
                state["fall_detected_since"] = now
        else:
            state["fall_detected_since"] = None

    def update_soldier_data(self, soldier_id, **kwargs):
        if soldier_id not in self.soldier_state:
            self.soldier_state[soldier_id] = self.make_default_state()

        state = self.soldier_state[soldier_id]
        for key, value in kwargs.items():
            state[key] = value
            if key == "motion_state" and value in (
                "WALKING", "RUNNING", "JUMPING", "LIMPING", "SQUATTING",
            ):
                state["last_motion_time"] = time.time()

        # Recompute all persistence timers after applying new values
        self._update_persistence_timers(state)

        # Update injury classifier with latest vitals
        classifier = state["classifier"]
        classifier.update(
            hr=state.get("hr"),
            spo2=state.get("spo2"),
            rr=state.get("rr"),
            sbp=state.get("sbp"),
            dbp=state.get("dbp"),
            motion_state=state.get("motion_state"),
            imu_impact=state.get("imu_impact"),
        )
        state["injury_probs"] = classifier.calculate_injury_probabilities()

    def handle_incoming_packet(
        self,
        device_id,
        hr=None,
        spo2=None,
        motion_state=None,
        link_status="ACTIVE",
        vbat=None,
        rr=None,
        sbp=None,
        dbp=None,
        imu_impact=None
    ):
        if not device_id:
            return

        soldier_id = self.device_to_soldier.get(device_id)
        if soldier_id is None:
            return

        updates = {"data_link_status": link_status}
        if hr is not None:
            updates["hr"] = hr
        if spo2 is not None:
            updates["spo2"] = spo2
        if motion_state is not None:
            updates["motion_state"] = motion_state
            updates["fall_detected"] = (motion_state in ("DETECTED_FALL", "STATIONARY_POST_FALL"))
        if vbat is not None:
            updates["vbat"] = vbat
        if rr is not None:
            updates["rr"] = rr
        if sbp is not None:
            updates["sbp"] = sbp
        if dbp is not None:
            updates["dbp"] = dbp
        if imu_impact is not None:
            updates["imu_impact"] = imu_impact

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