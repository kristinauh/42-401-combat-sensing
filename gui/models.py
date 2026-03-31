# models.py

from dataclasses import dataclass
from typing import Optional

def display_motion_label(value):
    mapping = {
        "STATIONARY": "No Movement",
        "WALKING": "Walking",
        "RUNNING": "Running",
        "PRONE": "On Ground",
        "NO DATA": "Signal Lost",
        "IDLE_FALL": "Unresponsive",
    }
    if value is None:
        return "--"
    return mapping.get(str(value), str(value).replace("_", " ").title())

def calculate_hr_zone(age, hr):
    if age is None or hr is None:
        return "--"

    try:
        age = int(age)
        hr = float(hr)
    except (TypeError, ValueError):
        return "--"

    if age <= 0:
        return "--"

    max_hr = 220 - age
    if max_hr <= 0:
        return "--"

    pct = hr / max_hr
    if pct < 0.50:
        return "Below Zone 1"
    elif pct < 0.60:
        return "Zone 1"
    elif pct < 0.70:
        return "Zone 2"
    elif pct < 0.80:
        return "Zone 3"
    elif pct < 0.90:
        return "Zone 4"
    elif pct <= 1.00:
        return "Zone 5"
    else:
        return "Above Zone 5"

@dataclass
class SoldierInfo:
    name: str
    age: Optional[int]
    device_id: str