# widgets.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from gui.models import SoldierInfo
from theme import (
    ACCENT,
    ACCENT_HOVER,
    BG,
    BORDER,
    BORDER_SOFT,
    CARD,
    CARD_2,
    CRITICAL_BG,
    CRITICAL_BORDER,
    CRITICAL_FG,
    DIVIDER,
    HERO_BG,
    LOST_BG,
    LOST_BORDER,
    LOST_FG,
    MONITOR_BG,
    MONITOR_BORDER,
    MONITOR_FG,
    STABLE_BG,
    STABLE_BORDER,
    STABLE_FG,
    SURFACE,
    TEXT,
    TEXT_DIM,
)


class AddSoldierDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Soldier")
        self.setModal(True)
        self.result_data = None  # Populated with form data on successful save

        self.setStyleSheet(f"""
            QDialog {{
                background: {SURFACE};
                color: {TEXT};
            }}
            QLabel {{
                color: {TEXT};
                background: transparent;
            }}
            QLineEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT};
            }}
            QPushButton {{
                border: none;
                border-radius: 10px;
                padding: 10px 14px;
                font-weight: 700;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("ADD SOLDIER")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {TEXT};")
        layout.addWidget(title)

        subtitle = QLabel("Enter the soldier's internal record information.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_DIM};")
        layout.addWidget(subtitle)

        self.sid_edit = QLineEdit()
        self.sid_edit.setPlaceholderText("Soldier ID")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")

        self.age_edit = QLineEdit()
        self.age_edit.setPlaceholderText("Age")

        self.device_edit = QLineEdit()
        self.device_edit.setPlaceholderText("Device ID")  # Must match DEVICE_ID in main.py

        layout.addWidget(self.sid_edit)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.age_edit)
        layout.addWidget(self.device_edit)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #07111d;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
            }}
        """)
        self.save_btn.clicked.connect(self.save)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: #172336;
                color: {TEXT};
                border: 1px solid {BORDER};
            }}
            QPushButton:hover {{
                background: #1d2c43;
            }}
        """)
        self.cancel_btn.clicked.connect(self.reject)

        row.addWidget(self.save_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch()
        layout.addLayout(row)

        self.fit_to_screen()

    def fit_to_screen(self):
        # Size the dialog relative to screen size with sensible min/max bounds
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(460, 320)
            return

        avail = screen.availableGeometry()
        target_w = min(460, max(360, avail.width() - 80))
        target_h = min(360, max(280, avail.height() - 80))
        self.resize(target_w, target_h)

    def save(self):
        sid = self.sid_edit.text().strip()
        name = self.name_edit.text().strip()
        age_raw = self.age_edit.text().strip()
        device_id = self.device_edit.text().strip()

        # Validate required fields before accepting
        if not sid:
            QMessageBox.warning(self, "Missing Soldier ID", "Please enter a soldier ID.")
            return
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name.")
            return
        if not device_id:
            QMessageBox.warning(self, "Missing Device ID", "Please enter a device ID.")
            return

        # Age is optional but must be a valid positive integer if provided
        age = None
        if age_raw:
            try:
                age = int(age_raw)
                if age <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Invalid Age", "Age must be a positive whole number.")
                return

        self.result_data = {
            "sid": sid,
            "name": name,
            "age": age,
            "device_id": device_id,
        }
        self.accept()


class SoldierCard(QFrame):
    # Emits the soldier_id when the card is clicked
    clicked = Signal(str)

    def __init__(self, soldier_id: str, info: SoldierInfo, parent=None):
        super().__init__(parent)
        self.soldier_id = soldier_id
        self.info = info
        self.selected = False
        self.status_kind = "STABLE"
        self.status_border = BORDER_SOFT

        self.setObjectName("soldierCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(280)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 18, 18, 18)
        self.root_layout.setSpacing(12)

        # Header row: soldier ID, name, status pill
        header = QHBoxLayout()
        header.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.sid_label = QLabel(soldier_id)
        self.name_label = QLabel(info.name)

        title_col.addWidget(self.sid_label)
        title_col.addWidget(self.name_label)

        header.addLayout(title_col)
        header.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.status_pill = QLabel("INIT")
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setMinimumWidth(96)
        header.addWidget(self.status_pill)

        self.root_layout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {DIVIDER}; border: none;")
        self.root_layout.addWidget(divider)

        # Hero boxes: large HR and SpO2 values
        self.hero_grid = QGridLayout()
        self.hero_grid.setSpacing(8)
        self.hr_box   = self._make_hero_box("HR", "-- bpm")
        self.spo2_box = self._make_hero_box("SpO2", "--%")
        self.rr_box   = self._make_hero_box("Resp", "-- BrPM")
        self.bp_box   = self._make_hero_box("BP", "--/--")
        self.hero_grid.addWidget(self.hr_box,   0, 0)
        self.hero_grid.addWidget(self.spo2_box, 0, 1)
        self.hero_grid.addWidget(self.rr_box,   1, 0)
        self.hero_grid.addWidget(self.bp_box,   1, 1)
        self.hero_grid.setColumnStretch(0, 1)
        self.hero_grid.setColumnStretch(1, 1)
        self.root_layout.addLayout(self.hero_grid)

        # Detail rows: HR zone, condition, link, last movement
        self.rows_container = QWidget()
        self.rows_container.setStyleSheet("background: transparent; border: none;")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 10, 0, 0)
        self.rows_layout.setSpacing(8)

        self.hr_zone_row = self._make_detail_row("HR Zone", "--")
        self.condition_row = self._make_detail_row("Activity", "--")
        self.link_row = self._make_detail_row("Link", "--")
        self.last_move_row = self._make_detail_row("Last Move", "--")
        self.vbat_row = self._make_detail_row("Battery", "--")

        self.rows_layout.addWidget(self.hr_zone_row["container"])
        self.rows_layout.addWidget(self.condition_row["container"])
        self.rows_layout.addWidget(self.link_row["container"])
        self.rows_layout.addWidget(self.last_move_row["container"])
        self.rows_layout.addWidget(self.vbat_row["container"])

        self.root_layout.addWidget(self.rows_container)
        self.rows_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.root_layout.addStretch()

        self.apply_scale("group_3_4")
        self.apply_card_style()

    def _make_hero_box(self, label_text, value_text):
        # Large metric box used for HR and SpO2 — label on top, big value below
        box = QFrame()
        box.setObjectName("heroBox")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(4)

        label = QLabel(label_text)
        value = QLabel(value_text)

        # Store references so set_values() can update them directly
        box.small_label = label
        box.value_label = value

        layout.addWidget(label)
        layout.addWidget(value)
        return box

    def _make_detail_row(self, left_text, right_text):
        # Key-value row used for secondary metrics at the bottom of each card
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(14)

        left = QLabel(left_text)
        left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        right = QLabel(right_text)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.setWordWrap(False)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right.setMinimumWidth(140)

        layout.addWidget(left)
        layout.addStretch(1)
        layout.addWidget(right)

        return {"container": container, "left": left, "right": right}

    def set_selected(self, selected: bool):
        self.selected = selected
        self.apply_card_style()  # Border color changes to reflect selection

    def set_status(self, text: str, kind: str):
        # Update the status pill color and text based on triage classification
        self.status_kind = kind

        if kind == "STABLE":
            bg, fg, border = STABLE_BG, STABLE_FG, STABLE_BORDER
        elif kind == "MONITOR":
            bg, fg, border = MONITOR_BG, MONITOR_FG, MONITOR_BORDER
        elif kind == "CRITICAL":
            bg, fg, border = CRITICAL_BG, CRITICAL_FG, CRITICAL_BORDER
        elif kind == "LOST":
            bg, fg, border = LOST_BG, LOST_FG, LOST_BORDER
        else:
            bg, fg, border = LOST_BG, LOST_FG, LOST_BORDER

        self.status_border = border
        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 4px 10px;
                font-weight: 800;
            }}
        """)
        self.apply_card_style()

    def apply_card_style(self):
        # Card border and background shift based on status and selection state
        border = self.status_border if self.status_kind == "CRITICAL" else BORDER_SOFT
        if self.selected:
            border = ACCENT if self.status_kind != "CRITICAL" else CRITICAL_BORDER

        card_start = CARD
        card_end = CARD_2

        # Signal-lost cards get a dimmer background to visually indicate no data
        if self.status_kind == "LOST":
            card_start = "#0d131b"
            card_end = "#101722"
            border = LOST_BORDER if not self.selected else "#4a5a70"

        self.setStyleSheet(f"""
            QFrame#soldierCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {card_start},
                    stop:1 {card_end}
                );
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QFrame#heroBox {{
                background: {HERO_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

    def set_values(self, hr_text, hr_zone_text, spo2_text, rr_text, bp_text, condition_text, link_text, last_move_text, vbat_text, vbat_color=None, injury_probs=None,):
        # Update all displayed values — called by refresh_ui_elements in triage_gui
        self.hr_box.value_label.setText(hr_text)
        self.spo2_box.value_label.setText(spo2_text)
        self.rr_box.value_label.setText(f"{rr_text} BrPM" if rr_text != "--" else "--")
        self.bp_box.value_label.setText(bp_text)
        self.hr_zone_row["right"].setText(hr_zone_text)
        self.condition_row["right"].setText(condition_text)
        self.link_row["right"].setText(link_text)
        self.last_move_row["right"].setText(last_move_text)
        self.vbat_row["right"].setText(vbat_text)
        if vbat_color:
            self.vbat_row["right"].setStyleSheet(
                f"color: {vbat_color}; background: transparent; border: none;"
            )
        if injury_probs:
            self._update_injury_display(injury_probs)

    def set_hero_alerts(self, hr, spo2):
        # Color each hero box independently based on how critical that value is
        hr_bg = HERO_BG
        spo2_bg = HERO_BG
        hr_border = BORDER
        spo2_border = BORDER

        try:
            hr = float(hr)
            if hr > 130:
                hr_bg, hr_border = CRITICAL_BG, CRITICAL_BORDER
            elif hr > 100:
                hr_bg, hr_border = MONITOR_BG, MONITOR_BORDER
        except (TypeError, ValueError):
            pass

        try:
            spo2 = float(spo2)
            if spo2 < 92:
                spo2_bg, spo2_border = CRITICAL_BG, CRITICAL_BORDER
            elif spo2 < 95:
                spo2_bg, spo2_border = MONITOR_BG, MONITOR_BORDER
        except (TypeError, ValueError):
            pass

        box_style = """
            QFrame#heroBox {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """

        self.hr_box.setStyleSheet(box_style.format(bg=hr_bg, border=hr_border))
        self.spo2_box.setStyleSheet(box_style.format(bg=spo2_bg, border=spo2_border))
        self.rr_box.setStyleSheet(box_style.format(bg=HERO_BG, border=BORDER))
        self.bp_box.setStyleSheet(box_style.format(bg=HERO_BG, border=BORDER))

    def apply_scale(self, scale_name: str):
        # Font sizes and spacing scale down as more cards are shown simultaneously
        # group_1 = 1 card (largest), group_5_8 = 5–8 cards (smallest)
        scales = {
        "group_1": {
            "sid": 30, "name": 16, "pill": 11,
            "hero_small": 12, "hero_value": 30,
            "detail_left": 17, "detail_right": 19,
            "margins": (28, 28, 28, 28),
            "spacing": 14,
            "hero_min_h": 90,
            "hero_gap": 14,
            "rows_top": 12,
            "rows_spacing": 12,
            "row_min_h": 36,
        },
        "group_2": {
            "sid": 24, "name": 13, "pill": 10,
            "hero_small": 11, "hero_value": 24,
            "detail_left": 15, "detail_right": 17,
            "margins": (22, 22, 22, 22),
            "spacing": 11,
            "hero_min_h": 72,
            "hero_gap": 12,
            "rows_top": 10,
            "rows_spacing": 10,
            "row_min_h": 30,
        },
            "group_3_4": {
                "sid": 18, "name": 11, "pill": 9,
                "hero_small": 9, "hero_value": 14,
                "detail_left": 12, "detail_right": 13,
                "margins": (12, 12, 12, 12),
                "spacing": 5,
                "hero_min_h": 44,
                "hero_gap": 6,
                "rows_top": 4,
                "rows_spacing": 4,
                "row_min_h": 24,
            },
            "group_5_8": {
                "sid": 14, "name": 9, "pill": 8,
                "hero_small": 7, "hero_value": 12,
                "detail_left": 10, "detail_right": 10,
                "margins": (10, 10, 10, 10),
                "spacing": 6,
                "hero_min_h": 44,
                "hero_gap": 5,
                "rows_top": 6,
                "rows_spacing": 5,
                "row_min_h": 20,
            },
        }

        s = scales[scale_name]

        # Apply layout spacing for this scale
        self.root_layout.setContentsMargins(*s["margins"])
        self.root_layout.setSpacing(s["spacing"])
        self.hero_grid.setSpacing(s["hero_gap"])
        self.rows_layout.setContentsMargins(0, s["rows_top"], 0, 0)
        self.rows_layout.setSpacing(s["rows_spacing"])

        self.sid_label.setFont(QFont("Bahnschrift SemiBold", s["sid"]))
        self.sid_label.setStyleSheet(
            f"color: {TEXT}; font-weight: 800; background: transparent; border: none;"
        )

        self.name_label.setFont(QFont("Bahnschrift", s["name"]))
        self.name_label.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; border: none;"
        )

        self.status_pill.setFont(QFont("Bahnschrift SemiBold", s["pill"]))
        
        for box in [self.hr_box, self.spo2_box, self.rr_box, self.bp_box]:
            box.small_label.setFont(QFont("Bahnschrift SemiBold", s["hero_small"]))
            box.small_label.setStyleSheet(
                f"color: {TEXT_DIM}; font-weight: 700; background: transparent; border: none;"
            )
            box.value_label.setFont(QFont("Consolas", s["hero_value"], QFont.Bold))
            box.value_label.setStyleSheet(
                f"color: {TEXT}; font-weight: 800; background: transparent; border: none;"
            )
            box.setMinimumHeight(s["hero_min_h"])

        padding = 2 if scale_name in ("group_5_8", "group_3_4") else 6
        for row in [self.hr_zone_row, self.condition_row, self.link_row, self.last_move_row, self.vbat_row]:
            row["container"].layout().setContentsMargins(0, padding, 0, padding)
            row["left"].setFont(QFont("Bahnschrift SemiBold", s["detail_left"]))
            row["left"].setStyleSheet(
                f"color: {TEXT_DIM}; font-weight: 700; background: transparent; border: none;"
            )
            row["right"].setFont(QFont("Bahnschrift", s["detail_right"]))
            row["right"].setStyleSheet(
                f"color: {TEXT}; background: transparent; border: none;"
            )

        # At the end of apply_scale(), after the padding block:
        for i in range(self.rows_layout.count()):
            self.rows_layout.setStretch(i, 1)

        for i in range(self.root_layout.count()):
            item = self.root_layout.itemAt(i)
            if item and item.spacerItem():
                self.root_layout.removeItem(item)
                break

        if scale_name == "group_5_8":
            # Remove stretch so content fills the card evenly
            for i in range(self.root_layout.count()):
                item = self.root_layout.itemAt(i)
                if item and item.spacerItem():
                    self.root_layout.removeItem(item)
                    break
        else:
            # Make sure stretch exists for other scales
            if self.root_layout.itemAt(self.root_layout.count() - 1) and \
            not self.root_layout.itemAt(self.root_layout.count() - 1).spacerItem():
                self.root_layout.addStretch()

    def mousePressEvent(self, event):
        # Forward click to the dashboard so it can toggle selection in the roster list
        self.clicked.emit(self.soldier_id)
        super().mousePressEvent(event)