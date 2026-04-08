// bcg.ino
// BCG-based PAT estimation for blood pressure
// J-wave detection from chest IMU (y-axis), PPG foot from IR signal -> PAT computation
// Method: Butterworth bandpass 1–20 Hz -> J-wave peak detection -> BP = α·ln(PAT) + β·HR + γ
// Based on: Marzorati et al. (2020), IEEE Access 8, 55424–55437
// https://doi.org/10.1109/ACCESS.2020.2981300

#include "defines.h"

// BCG filter: 4th-order Butterworth bandpass 1–20 Hz at 100 Hz
// Stage 1 (highpass 1 Hz)
#define BCG_B0_1  0.93913524f
#define BCG_B1_1 -1.87827047f
#define BCG_B2_1  0.93913524f
#define BCG_A1_1 -1.87612899f
#define BCG_A2_1  0.88041195f
// Stage 2 (lowpass 20 Hz)
#define BCG_B0_2  0.06745527f
#define BCG_B1_2  0.13491055f
#define BCG_B2_2  0.06745527f
#define BCG_A1_2 -1.14298050f
#define BCG_A2_2  0.41280160f

// Buffer: 5s at 100 Hz — long enough to catch several beats, short enough to be responsive
#define BCG_FS_HZ        100.0f
#define BCG_WINDOW_SEC   5.0f
#define BCG_N_SAMPLES    500
#define BCG_MIN_PEAK_DIST 30   // min samples between J-waves (~0.3s, caps at 200 bpm)
#define BCG_PEAK_THRESH   0.003f  // tune this after looking at serial output

static float bcg_z1_s1 = 0.0f, bcg_z2_s1 = 0.0f;
static float bcg_z1_s2 = 0.0f, bcg_z2_s2 = 0.0f;

static float bcg_buf[BCG_N_SAMPLES];
static uint32_t bcg_ts_buf[BCG_N_SAMPLES];  // wall-clock timestamps per sample
static int bcg_idx = 0;

// Circular buffer of recent J-wave timestamps (ms), for PAT matching against PPG feet
#define BCG_JWAVE_BUF_SIZE 16
static uint32_t jwave_ts[BCG_JWAVE_BUF_SIZE];
static int jwave_head = 0;
static int jwave_count = 0;

// Last computed PAT and BP
static float bcg_last_pat = NAN;
static float bcg_last_sbp = NAN;
static float bcg_last_dbp = NAN;

// Subject-specific calibration params (from BP = alpha*ln(PAT) + beta*HR + gamma)
// These need to be set after doing a calibration session — start with rough defaults
// and replace after collecting a few reference BP + PAT pairs
static float bp_alpha_sbp = -20.0f;
static float bp_beta_sbp  =  0.2f;
static float bp_gamma_sbp = 210.0f;

static float bp_alpha_dbp = -8.0f;
static float bp_beta_dbp  =  0.15f;
static float bp_gamma_dbp = 110.0f;

// Filter

static float bcg_biquad(float x,
                         float b0, float b1, float b2,
                         float a1, float a2,
                         float *z1, float *z2) {
    float y = b0 * x + *z1;
    *z1 = b1 * x - a1 * y + *z2;
    *z2 = b2 * x - a2 * y;
    return y;
}

static float bcg_filter(float x) {
    float s1 = bcg_biquad(x,
                           BCG_B0_1, BCG_B1_1, BCG_B2_1,
                           BCG_A1_1, BCG_A2_1,
                           &bcg_z1_s1, &bcg_z2_s1);
    return bcg_biquad(s1,
                       BCG_B0_2, BCG_B1_2, BCG_B2_2,
                       BCG_A1_2, BCG_A2_2,
                       &bcg_z1_s2, &bcg_z2_s2);
}

// J-wave detection across the completed window
// Stores detected J-wave timestamps into jwave_ts circular buffer

static void bcg_detect_jwaves() {
    for (int i = 1; i < BCG_N_SAMPLES - 1; i++) {
        if (bcg_buf[i] > bcg_buf[i-1] &&
            bcg_buf[i] >= bcg_buf[i+1] &&
            bcg_buf[i] > BCG_PEAK_THRESH) {

            bool too_close = false;
            if (jwave_count > 0) {
                int prev_idx = (jwave_head - 1 + BCG_JWAVE_BUF_SIZE) % BCG_JWAVE_BUF_SIZE;
                uint32_t dt = bcg_ts_buf[i] - jwave_ts[prev_idx];
                if (dt < (uint32_t)(1000.0f * BCG_MIN_PEAK_DIST / BCG_FS_HZ)) {
                    // Keep taller peak
                    int prev_buf_idx = i - (int)(dt / (1000.0f / BCG_FS_HZ));
                    if (prev_buf_idx >= 0 && bcg_buf[i] > bcg_buf[prev_buf_idx]) {
                        jwave_ts[prev_idx] = bcg_ts_buf[i];
                    }
                    too_close = true;
                }
            }

            if (!too_close) {
                jwave_ts[jwave_head] = bcg_ts_buf[i];
                jwave_head = (jwave_head + 1) % BCG_JWAVE_BUF_SIZE;
                if (jwave_count < BCG_JWAVE_BUF_SIZE) jwave_count++;
            }
        }
    }
}

// Called from ppg.ino after a PPG foot is detected
// ppg_foot_ts: wall-clock time (ms) of the PPG foot
// hr_est: current HR estimate in bpm (from PPG window)
// Returns PAT in ms, or NAN if no recent J-wave to pair with

float bcg_compute_pat(uint32_t ppg_foot_ts, float hr_est) {
    if (jwave_count == 0) return NAN;

    // Find the most recent J-wave that precedes this PPG foot
    // PAT physiologically expected to be 100–400ms
    uint32_t best_ts = 0;
    bool found = false;

    for (int i = 0; i < jwave_count; i++) {
        int idx = (jwave_head - 1 - i + BCG_JWAVE_BUF_SIZE) % BCG_JWAVE_BUF_SIZE;
        uint32_t jts = jwave_ts[idx];
        if (jts >= ppg_foot_ts) continue;  // J-wave must precede PPG foot

        uint32_t pat_candidate = ppg_foot_ts - jts;
        if (pat_candidate >= 100 && pat_candidate <= 400) {
            best_ts = jts;
            found = true;
            break;
        }
    }

    if (!found) return NAN;

    float pat_ms = (float)(ppg_foot_ts - best_ts);
    bcg_last_pat = pat_ms;

    // Compute BP if HR is valid
    if (!isnan(hr_est) && hr_est > 30.0f && hr_est < 200.0f) {
        float ln_pat = logf(pat_ms);
        bcg_last_sbp = bp_alpha_sbp * ln_pat + bp_beta_sbp * hr_est + bp_gamma_sbp;
        bcg_last_dbp = bp_alpha_dbp * ln_pat + bp_beta_dbp * hr_est + bp_gamma_dbp;
        send_bp_packet();
    }

    return pat_ms;
}

// BLE packet: 'P' ts(uint32) sbp(int16 x10) dbp(int16 x10)
static void send_bp_packet() {
    static uint32_t last_bp_send_ms = 0;
    uint32_t now = millis();
    if (now - last_bp_send_ms < 5000) return;
    last_bp_send_ms = now;

#if BP_SERIAL
    Serial.print("BP pat_ms: "); Serial.print(bcg_last_pat);
    Serial.print(", sbp: "); Serial.print(bcg_last_sbp);
    Serial.print(", dbp: "); Serial.println(bcg_last_dbp);
#endif

    if (!Bluefruit.connected()) return;

    int16_t sbp_i = isnan(bcg_last_sbp) ? -1 : (int16_t)lroundf(bcg_last_sbp * 10.0f);
    int16_t dbp_i = isnan(bcg_last_dbp) ? -1 : (int16_t)lroundf(bcg_last_dbp * 10.0f);

    uint32_t ts = millis();
    uint8_t pkt[9];
    pkt[0] = 'P';
    memcpy(&pkt[1], &ts, 4);
    memcpy(&pkt[5], &sbp_i, 2);
    memcpy(&pkt[7], &dbp_i, 2);

    bleuart.write(pkt, sizeof(pkt));
}

// Public interface

void bcg_setup() {
    bcg_idx = 0;
    jwave_head = 0;
    jwave_count = 0;
    bcg_last_pat = NAN;
    bcg_last_sbp = NAN;
    bcg_last_dbp = NAN;
    bcg_z1_s1 = bcg_z2_s1 = 0.0f;
    bcg_z1_s2 = bcg_z2_s2 = 0.0f;
}

// Called from handle_imu() each tick, pass in the chest-perpendicular axis
void bcg_update(float ay) {
    float filtered = bcg_filter(ay);
    bcg_buf[bcg_idx] = filtered;
    bcg_ts_buf[bcg_idx] = millis();

// #if BP_SERIAL
//     Serial.print("BCG_RAW:"); Serial.print(ay, 4);
//     Serial.print(",BCG_FILT:"); Serial.println(filtered, 4);
// #endif

    bcg_idx++;

    if (bcg_idx >= BCG_N_SAMPLES) {
        bcg_detect_jwaves();
        // Overlap by 50% — same pattern as rr.ino
        int half = BCG_N_SAMPLES / 2;
        memmove(bcg_buf, bcg_buf + half, half * sizeof(float));
        memmove(bcg_ts_buf, bcg_ts_buf + half, half * sizeof(uint32_t));
        bcg_idx = half;
    }
}