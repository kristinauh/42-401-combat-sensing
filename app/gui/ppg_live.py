# ppg_live.py

import serial
import matplotlib.pyplot as plt
import numpy as np

PORT = 'COM6'
BAUD = 115200
N_SAMPLES = 1000
FS = 100.0

ser = serial.Serial(PORT, BAUD, timeout=5)

plt.ion()
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

print("Waiting for data...")

hr_est = None
spo2_est = None

while True:
    samples = []
    while len(samples) < N_SAMPLES:
        line = ser.readline().decode(errors='ignore').strip()
        if line.startswith('PPG hr:'):
            try:
                parts = line.split(',')
                hr_est = float(parts[0].split('PPG hr:')[1].strip())
                spo2_est = float(parts[1].split('spo2:')[1].strip())
            except:
                pass
            continue
        try:
            samples.append(float(line))
        except ValueError:
            continue

    samples = np.array(samples)
    x = np.arange(len(samples)) / FS

    # FFT
    N = len(samples)
    freqs = np.fft.rfftfreq(N, d=1.0/FS)
    fft_mag = np.abs(np.fft.rfft(samples)) / N

    title = 'PPG Bandpass Filtered'

    # if hr_est is not None:
    #     title += f'\nHR: {hr_est:.1f} bpm'

    # if spo2_est is not None:
    #     title += f'\nSpO2: {spo2_est:.1f} %'

    ax1.cla()
    ax1.plot(x, samples)
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Filtered IR')
    ax1.set_title(title)
    ax1.grid(True)

    ax2.cla()
    ax2.plot(freqs, fft_mag)
    ax2.set_xlim(0, 5)
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Amplitude')
    ax2.set_title('FFT Spectrum')
    ax2.grid(True)

    # # mark the estimated HR frequency
    # if hr_est is not None:
    #     ax2.axvline(x=hr_est/60.0, color='r', linestyle='--', label=f'Est HR ({hr_est:.1f} bpm)')
    #     ax2.legend()

    fig.tight_layout()
    fig.canvas.draw()
    fig.canvas.flush_events()