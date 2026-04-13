# App

Wearable triage monitoring system - firmware streams vitals over BLE, Python GUI displays live triage status.

## Structure

```
app/
├── main.py                       # Entry point - connects BLE backend to GUI
├── ble_monitor.py                # Standalone BLE packet parser / logger
├── gui/
│   ├── triage_gui.py             # Dashboard window and triage logic
│   ├── widgets.py                # Soldier card and dialog components
│   ├── theme.py
│   ├── injury_classification.py  # Injury probability engine
│   ├── models.py                 # Data models (SoldierInfo, motion labels, HR zones)
│   └── demo.py                   # Fake data generator for testing without hardware
├── firmware/
│   ├── ble_stream.ino            # Main sketch (setup/loop)
│   ├── defines.h                 # Constants, thresholds, state enums
│   ├── ppg.ino                   # Heart rate and SpO2 from MAX30102
│   ├── imu.ino                   # Motion classification and fall detection
│   ├── rr.ino                    # Respiratory rate from accelerometer
│   ├── bp.ino                    # Blood pressure estimation via BCG/PPG
│   └── battery.ino               # Battery voltage reporting
```

## Setup

**Firmware:**
1. Open the `firmware/` folder in Arduino IDE
2. Install board support for XIAO nRF52840 Sense
3. Install libraries: `LSM6DS3`, `MAX30105`
4. Flash to device

**Python:**
```bash
pip install PySide6 bleak
python main.py
```

## Usage

1. Power on the wearable device
2. Run `main.py` - it will scan and connect over BLE automatically
3. Import a roster CSV or add soldiers manually in the sidebar
4. Assign the device ID (`DEV_001` by default in `main.py`) to match a roster entry

To test the GUI without hardware, run `demo.py` instead.

## BLE Packet Types

| Prefix | Source       | Contents                          |
|--------|-------------|-----------------------------------|
| `R`    | ppg.ino     | Heart rate, SpO2                  |
| `M`    | imu.ino     | Motion state, event value, impact |
| `W`    | rr.ino      | Respiratory rate                  |
| `P`    | bp.ino      | Systolic/diastolic blood pressure |
| `B`    | battery.ino | Battery voltage                   |