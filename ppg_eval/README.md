# PPG Evaluation

This folder contains the PPG evaluation pipeline for BLE-transmitted HR and SpO2 estimates.

Workflow:
1. Flash ppg_ble_stream.ino to collect HR and SpO2 estimates
2. Run ppg_ble.py to receive BLE data and save estimated and reference readings
3. Run ppg_analysis.m to compare estimated HR and SpO2 against the reference data