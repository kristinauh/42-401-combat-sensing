// rr.ino
// Respiratory rate estimation from chest-worn IMU accelerometer (y-axis)
// Method: 1st order Butterworth bandpass 0.1–0.7 Hz -> peak counting over 25s window
// Based on: Romano et al. (2022), Biosensors 12, 834
// https://doi.org/10.3390/bios12100834

#include "defines.h"

// RR estimation settings
#define RR_FS_HZ         100.0f   // IMU sample rate (must match LOOP_DELAY = 10ms)
#define RR_WINDOW_SEC    25.0f    // Window length in seconds (sweet spot per Romano 2022)
#define RR_N_SAMPLES     2500     // RR_FS_HZ * RR_WINDOW_SEC
#define RR_MIN_PEAK_DIST 60       // Min samples between peaks (~0.3s, caps at 200 BrPM)
#define RR_PEAK_THRESH   0.002f   // Minimum peak height — filters noise peaks
#define RR_MIN_BrPM      4.0f    // Sanity floor, reject implausible values
#define RR_MAX_BrPM      60.0f   // Sanity ceiling

// Butterworth bandpass biquad coefficients: 0.1–0.5 Hz at 100 Hz
// Stage 1 (highpass at 0.1 Hz)
#define RR_BPF_B0_1  0.96906173f
#define RR_BPF_B1_1 -1.93812347f
#define RR_BPF_B2_1  0.96906173f
#define RR_BPF_A1_1 -1.93774049f
#define RR_BPF_A2_1  0.93850644f
// Stage 2 (lowpass at 0.5 Hz)
#define RR_BPF_B0_2  0.00024136f
#define RR_BPF_B1_2  0.00048272f
#define RR_BPF_B2_2  0.00024136f
#define RR_BPF_A1_2 -1.97641455f
#define RR_BPF_A2_2  0.97737999f

// Filter state (persistent across calls, biquad needs memory between ticks)
static float rr_z1_s1 = 0.0f;
static float rr_z2_s1 = 0.0f;
static float rr_z1_s2 = 0.0f;
static float rr_z2_s2 = 0.0f;

// Sample buffer for the 25s window
static float rr_buf[RR_N_SAMPLES];
static int   rr_sample_idx = 0;
static bool  rr_buf_full = false;

// Last computed RR, NAN until first valid window completes
static float rr_last = NAN;
static uint32_t rr_ts = 0;

// Filter

static float biquad_step(float x,
                         float b0, float b1, float b2,
                         float a1, float a2,
                         float *z1, float *z2) {
    float y = b0 * x + *z1;
    *z1 = b1 * x - a1 * y + *z2;
    *z2 = b2 * x - a2 * y;
    return y;
}

static float rr_bandpass(float x) {
    float s1 = biquad_step(x,
                           RR_BPF_B0_1, RR_BPF_B1_1, RR_BPF_B2_1,
                           RR_BPF_A1_1, RR_BPF_A2_1,
                           &rr_z1_s1, &rr_z2_s1);
    return biquad_step(s1,
                       RR_BPF_B0_2, RR_BPF_B1_2, RR_BPF_B2_2,
                       RR_BPF_A1_2, RR_BPF_A2_2,
                       &rr_z1_s2, &rr_z2_s2);
}

// Peak counting

static float mean_ipi_sec(const float *x, int n, int min_dist) {
    int peaks[RR_N_SAMPLES];
    int count = 0;

    for (int i = 1; i < n - 1; i++) {
        if (x[i] > x[i - 1] && x[i] >= x[i + 1] && x[i] > RR_PEAK_THRESH) {
            if (count == 0) {
                peaks[count++] = i;
            } else {
                int prev = peaks[count - 1];
                if ((i - prev) >= min_dist) {
                    peaks[count++] = i;
                } else if (x[i] > x[prev]) {
                    peaks[count - 1] = i;  // keep taller peak
                }
            }
        }
    }

    if (count < 2) return 0.0f;

    float ipi_sum = 0.0f;
    for (int i = 1; i < count; i++) {
        ipi_sum += (float)(peaks[i] - peaks[i - 1]) / RR_FS_HZ;
    }

    return ipi_sum / (float)(count - 1);
}

// Process window

static void rr_process_window() {
#if RR_SERIAL
    // Debug: count peaks to diagnose detection issues
    int dbg_count = 0;
    for (int i = 1; i < RR_N_SAMPLES - 1; i++) {
        if (rr_buf[i] > rr_buf[i-1] && rr_buf[i] >= rr_buf[i+1] && rr_buf[i] > RR_PEAK_THRESH) {
            if (dbg_count == 0 || (i - 0) >= RR_MIN_PEAK_DIST) {
                dbg_count++;
            }
        }
    }
    Serial.print("RR peak count: "); Serial.println(dbg_count);
#endif

    float mean_ipi = mean_ipi_sec(rr_buf, RR_N_SAMPLES, RR_MIN_PEAK_DIST);

#if RR_SERIAL
    Serial.print("RR mean_ipi: "); Serial.println(mean_ipi, 4);
#endif

    if (mean_ipi <= 0.0f) {
        rr_last = NAN;
        return;
    }

    float rr = 60.0f / mean_ipi;

    if (rr < RR_MIN_BrPM || rr > RR_MAX_BrPM) {
        rr_last = NAN;
        return;
    }

    rr_last = rr;
    rr_ts = millis();

#if RR_SERIAL
    Serial.print("RR BrPM: "); Serial.println(rr_last);
#endif
}

// BLE / Serial output

// W packet: ts(uint32), rr(int16 x100)
// rr scaled by 100 to avoid floats over BLE; -1 signals invalid/no reading
static void send_rr_result(float rr) {
    if (!Bluefruit.connected()) return;

    int16_t rr_i = isnan(rr) ? -1 : (int16_t)lroundf(rr * 100.0f);

    uint8_t pkt[7];
    pkt[0] = 'W';
    memcpy(&pkt[1], &rr_ts, 4);
    memcpy(&pkt[5], &rr_i, 2);

    bleuart.write(pkt, sizeof(pkt));
}

// Public interface

void rr_setup() {
    rr_sample_idx = 0;
    rr_buf_full   = false;
    rr_last       = NAN;
    rr_z1_s1 = rr_z2_s1 = 0.0f;
    rr_z1_s2 = rr_z2_s2 = 0.0f;
}

void rr_update(float ay) {
    float filtered = rr_bandpass(ay);
    rr_buf[rr_sample_idx++] = filtered;

// #if RR_SERIAL
//     Serial.print("RR_FILT:"); Serial.println(filtered, 4);
// #endif

    if (rr_sample_idx >= RR_N_SAMPLES) {
        rr_ts = millis();
        rr_process_window();
        send_rr_result(rr_last);

        int half = RR_N_SAMPLES / 2;
        memmove(rr_buf, rr_buf + half, half * sizeof(float));
        rr_sample_idx = half;
        rr_buf_full = true;
    }
}