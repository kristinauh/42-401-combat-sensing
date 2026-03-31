# PPG Analysis

This folder contains the PPG calibration and analysis pipeline.

Workflow:
1. Flash ppg_serial_stream.ino to collect PPG data
2. Run ppg_serial.py to save raw and reference data
3. Run ppg_analysis.m to compute HR, SpO2, and calibration