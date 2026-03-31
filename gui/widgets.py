# widgets.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
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

from models import SoldierInfo
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
        self.result_data = None

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

        subtitle = QLabel("Enter the soldier’s internal record information.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_DIM};")
        layout.addWidget(subtitle)

        self.sid_edit = QLineEdit()
        self.sid_edit.setPlaceholderText("Soldier ID")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")

        self.age_edit = QLineEdit()
        self.age_edit.setPlaceholderText("Age")

        self.device_edit = QLineEdit()
        self.device_edit.setPlaceholderText("Device ID")

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

        if not sid:
            QMessageBox.warning(self, "Missing Soldier ID", "Please enter a soldier ID.")
            return
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name.")
            return
        if not device_id:
            QMessageBox.warning(self, "Missing Device ID", "Please enter a device ID.")
            return

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
        self.setMinimumHeight(190)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 18, 18, 18)
        self.root_layout.setSpacing(12)

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

        self.hero_row = QHBoxLayout()
        self.hero_row.setSpacing(12)

        self.hr_box = self._make_hero_box("HR", "-- bpm")
        self.spo2_box = self._make_hero_box("SpO2", "--%")

        self.hero_row.addWidget(self.hr_box, 2)
        self.hero_row.addWidget(self.spo2_box, 2)
        self.root_layout.addLayout(self.hero_row)

        self.rows_container = QWidget()
        self.rows_container.setStyleSheet("background: transparent; border: none;")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 10, 0, 0)
        self.rows_layout.setSpacing(8)

        self.hr_zone_row = self._make_detail_row("HR Zone", "--")
        self.condition_row = self._make_detail_row("Condition", "--")
        self.link_row = self._make_detail_row("Link", "--")
        self.last_move_row = self._make_detail_row("Last Move", "--")

        self.rows_layout.addWidget(self.hr_zone_row["container"])
        self.rows_layout.addWidget(self.condition_row["container"])
        self.rows_layout.addWidget(self.link_row["container"])
        self.rows_layout.addWidget(self.last_move_row["container"])

        self.root_layout.addWidget(self.rows_container)
        self.root_layout.addStretch()

        self.apply_scale("group_3_4")
        self.apply_card_style()

    def _make_hero_box(self, label_text, value_text):
        box = QFrame()
        box.setObjectName("heroBox")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(4)

        label = QLabel(label_text)
        value = QLabel(value_text)

        box.small_label = label
        box.value_label = value

        layout.addWidget(label)
        layout.addWidget(value)
        return box

    def _make_detail_row(self, left_text, right_text):
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
        self.apply_card_style()

    def set_status(self, text: str, kind: str):
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
        border = self.status_border if self.status_kind == "CRITICAL" else BORDER_SOFT
        if self.selected:
            border = ACCENT if self.status_kind != "CRITICAL" else CRITICAL_BORDER

        card_start = CARD
        card_end = CARD_2

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

    def set_values(self, hr_text, hr_zone_text, spo2_text, condition_text, link_text, last_move_text):
        self.hr_box.value_label.setText(hr_text)
        self.spo2_box.value_label.setText(spo2_text)
        self.hr_zone_row["right"].setText(hr_zone_text)
        self.condition_row["right"].setText(condition_text)
        self.link_row["right"].setText(link_text)
        self.last_move_row["right"].setText(last_move_text)

    def apply_scale(self, scale_name: str):
        scales = {
            "group_1": {
                "sid": 30, "name": 16, "pill": 11,
                "hero_small": 12, "hero_value": 30,
                "detail_left": 17, "detail_right": 19,
                "margins": (28, 28, 28, 28),
                "spacing": 14,
                "hero_min_h": 128,
                "hero_gap": 14,
                "rows_top": 18,
                "rows_spacing": 18,
                "row_min_h": 44,
            },
            "group_2": {
                "sid": 24, "name": 13, "pill": 10,
                "hero_small": 11, "hero_value": 24,
                "detail_left": 15, "detail_right": 17,
                "margins": (22, 22, 22, 22),
                "spacing": 11,
                "hero_min_h": 102,
                "hero_gap": 12,
                "rows_top": 15,
                "rows_spacing": 15,
                "row_min_h": 38,
            },
            "group_3_4": {
                "sid": 18, "name": 11, "pill": 9,
                "hero_small": 9, "hero_value": 19,
                "detail_left": 13, "detail_right": 14,
                "margins": (16, 16, 16, 16),
                "spacing": 8,
                "hero_min_h": 82,
                "hero_gap": 10,
                "rows_top": 10,
                "rows_spacing": 10,
                "row_min_h": 36,
            },
            "group_5_8": {
                "sid": 15, "name": 9, "pill": 8,
                "hero_small": 8, "hero_value": 16,
                "detail_left": 11, "detail_right": 12,
                "margins": (13, 13, 13, 13),
                "spacing": 6,
                "hero_min_h": 68,
                "hero_gap": 8,
                "rows_top": 10,
                "rows_spacing": 10,
                "row_min_h": 28,
            },
        }

        s = scales[scale_name]
        self.root_layout.setContentsMargins(*s["margins"])
        self.root_layout.setSpacing(s["spacing"])
        self.hero_row.setSpacing(s["hero_gap"])
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

        self.hr_box.small_label.setFont(QFont("Bahnschrift SemiBold", s["hero_small"]))
        self.hr_box.small_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-weight: 700; background: transparent; border: none;"
        )

        self.spo2_box.small_label.setFont(QFont("Bahnschrift SemiBold", s["hero_small"]))
        self.spo2_box.small_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-weight: 700; background: transparent; border: none;"
        )

        self.hr_box.value_label.setFont(QFont("Consolas", s["hero_value"], QFont.Bold))
        self.hr_box.value_label.setStyleSheet(
            f"color: {TEXT}; font-weight: 800; background: transparent; border: none;"
        )

        self.spo2_box.value_label.setFont(QFont("Consolas", s["hero_value"], QFont.Bold))
        self.spo2_box.value_label.setStyleSheet(
            f"color: {TEXT}; font-weight: 800; background: transparent; border: none;"
        )

        self.hr_box.setMinimumHeight(s["hero_min_h"])
        self.spo2_box.setMinimumHeight(s["hero_min_h"])

        for row in [self.hr_zone_row, self.condition_row, self.link_row, self.last_move_row]:
            row["container"].setMinimumHeight(s["row_min_h"])
            row["left"].setFont(QFont("Bahnschrift SemiBold", s["detail_left"]))
            row["left"].setStyleSheet(
                f"color: {TEXT_DIM}; font-weight: 700; background: transparent; border: none;"
            )
            row["right"].setFont(QFont("Bahnschrift", s["detail_right"]))
            row["right"].setStyleSheet(
                f"color: {TEXT}; background: transparent; border: none;"
            )

    def mousePressEvent(self, event):
        self.clicked.emit(self.soldier_id)
        super().mousePressEvent(event)