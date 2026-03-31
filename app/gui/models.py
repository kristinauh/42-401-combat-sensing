# models.py

from dataclasses import dataclass
from typing import Optional


# Maps raw firmware motion state strings to human-readable display labels
def display_motion_label(value):
    mapping = {
        # Active states
        "WALKING": "Walking",
        "RUNNING": "Running",
        "JUMPING_OR_QUICK_SIT": "Jump / Quick Sit",
        # Fall pipeline states
        "IDLE_FALL": "Monitoring",
        "CHECK_FALL": "Checking...",
        "ANALYZE_IMPACT": "Analysing...",
        "DETECTED_FALL": "Fall Detected",
        "STATIONARY_POST_FALL": "Down — Not Moving",
        # Link states
        "NO DATA": "Signal Lost",
    }
    if value is None:
        return "--"
    # Fall back to a title-cased version of the raw string for any unmapped states
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

    # Standard age-predicted maximum heart rate formula
    max_hr = 220 - age
    if max_hr <= 0:
        return "--"

    # Express current HR as a fraction of max and map to training zones
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
    age: Optional[int]   # Used for HR zone calculation — None if not provided
    device_id: str       # Must match the BLE device ID in main.py