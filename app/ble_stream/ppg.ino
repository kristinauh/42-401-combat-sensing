// ppg.ino

#include <MAX30105.h>
#include "defines.h"

// PPG settings
#define FS_HZ 100.0f          // Sampling rate (Hz) — must match sampleRate below
#define WINDOW_SEC 5.0f       // PPG processing window length
#define N_SAMPLES 500         // Samples per window: FS_HZ * WINDOW_SEC
#define TRIM_SEC 0.13f        // Ignore initial unstable portion of each window

// SpO2 fit: SpO2 = A - B*R
#define SPO2_A 99.6061f
#define SPO2_B 4.7242f

// Minimum signal quality thresholds — windows below these are rejected
#define MIN_IR_DC 5000.0f
#define MIN_IR_AC 20.0f

MAX30105 sensor;

uint32_t ir_raw_buf[N_SAMPLES];
uint32_t red_raw_buf[N_SAMPLES];

float ir0[N_SAMPLES];
float red0[N_SAMPLES];
float ir_filt[N_SAMPLES];
float red_filt[N_SAMPLES];
float ir_norm[N_SAMPLES];
float scratch1[N_SAMPLES];   // Reusable scratch buffers for filtfilt passes
float scratch2[N_SAMPLES];
int peak_locs[N_SAMPLES];

int sample_idx = 0;
uint32_t window_counter = 0;
uint32_t ppg_ts = 0;         // Wall-clock time captured when each window completes

void reverse_in_place(float *x, int n) {
  for (int i = 0; i < n / 2; i++) {
    float t = x[i];
    x[i] = x[n - 1 - i];
    x[n - 1 - i] = t;
  }
}

void filter_biquad(const float *x, float *y, int n,
                   float b0, float b1, float b2,
                   float a1, float a2) {
  float z1 = 0.0f;
  float z2 = 0.0f;

  for (int i = 0; i < n; i++) {
    float out = b0 * x[i] + z1;
    z1 = b1 * x[i] - a1 * out + z2;
    z2 = b2 * x[i] - a2 * out;
    y[i] = out;
  }
}

// Forward-backward bandpass for zero-phase distortion (equivalent to filtfilt in MATLAB/scipy)
void bandpass_filtfilt(const float *x, float *y, int n) {
  // Forward pass
  filter_biquad(x, scratch1, n, 0.00686787f, 0.01373573f, 0.00686787f, -1.78602350f, 0.82036394f);
  filter_biquad(scratch1, scratch2, n, 1.00000000f, -2.00000000f, 1.00000000f, -1.94806585f, 0.95047992f);

  // Reverse and run again to cancel phase shift
  memcpy(scratch1, scratch2, n * sizeof(float));
  reverse_in_place(scratch1, n);

  filter_biquad(scratch1, scratch2, n, 0.00686787f, 0.01373573f, 0.00686787f, -1.78602350f, 0.82036394f);
  filter_biquad(scratch2, scratch1, n, 1.00000000f, -2.00000000f, 1.00000000f, -1.94806585f, 0.95047992f);

  reverse_in_place(scratch1, n);
  memcpy(y, scratch1, n * sizeof(float));
}

// Finds local maxima separated by at least min_peak_dist samples
// If two peaks are too close, keeps the taller one
int find_peaks(const float *x, int n, int min_peak_dist, int *locs) {
  int count = 0;

  for (int i = 1; i < n - 1; i++) {
    if (x[i] > x[i - 1] && x[i] >= x[i + 1]) {
      if (count == 0) {
        locs[count++] = i;
      } else {
        int prev = locs[count - 1];
        if ((i - prev) >= min_peak_dist) {
          locs[count++] = i;
        } else if (x[i] > x[prev]) {
          locs[count - 1] = i;
        }
      }
    }
  }

  return count;
}

// R packet: ts(uint32), hr(int16 x100), spo2(int16 x100)
// Values are scaled by 100 to avoid floats over BLE; -1 signals invalid/no reading
void send_result(float hr, float spo2) {
#if PPG_SERIAL
  // hr and spo2 are computed per-window, not per-sample, so print once per window
  Serial.print("PPG hr: "); Serial.print(hr); Serial.print(", spo2: "); Serial.println(spo2);
#endif

  if (!Bluefruit.connected()) return;

  int16_t hr_i = isnan(hr) ? -1 : (int16_t)lroundf(hr * 100.0f);
  int16_t spo2_i = isnan(spo2) ? -1 : (int16_t)lroundf(spo2 * 100.0f);

  uint8_t pkt[9];
  pkt[0] = 'R';
  memcpy(&pkt[1], &ppg_ts, 4);
  memcpy(&pkt[5], &hr_i, 2);
  memcpy(&pkt[7], &spo2_i, 2);

  bleuart.write(pkt, sizeof(pkt));
}

void process_window() {
  // Mask to 18-bit ADC range
  for (int i = 0; i < N_SAMPLES; i++) {
    ir_raw_buf[i] &= 0x3FFFF;
    red_raw_buf[i] &= 0x3FFFF;
    ir0[i] = (float)ir_raw_buf[i];
    red0[i] = (float)red_raw_buf[i];
  }

  float ir_dc_full = mean_float(ir0, N_SAMPLES);

  float ir_mean = ir_dc_full;
  float red_mean = mean_float(red0, N_SAMPLES);

  // Remove DC component before filtering so the bandpass sees a zero-mean signal
  for (int i = 0; i < N_SAMPLES; i++) {
    ir0[i] -= ir_mean;
    red0[i] -= red_mean;
  }

  bandpass_filtfilt(ir0, ir_filt, N_SAMPLES);
  bandpass_filtfilt(red0, red_filt, N_SAMPLES);

  float ir_std = std_float(ir_filt, N_SAMPLES);
  float red_std = std_float(red_filt, N_SAMPLES);

  if (ir_std == 0.0f || red_std == 0.0f) {
    send_result(NAN, NAN);
    return;
  }

  // Skip the first TRIM_SEC worth of samples — filter startup transient
  int start_idx_trim = 0;
  while (start_idx_trim < N_SAMPLES && ((float)start_idx_trim / FS_HZ) < TRIM_SEC) {
    start_idx_trim++;
  }

  int Nt = N_SAMPLES - start_idx_trim;
  if (Nt < 3) {
    send_result(NAN, NAN);
    return;
  }

  float ir_dc = mean_u32(&ir_raw_buf[start_idx_trim], Nt);
  float ir_ac = 0.5f * (max_float(&ir_filt[start_idx_trim], Nt) - min_float(&ir_filt[start_idx_trim], Nt));

#if PPG_SERIAL
  Serial.print("ir_dc: "); Serial.print(ir_dc);
  Serial.print(" ir_ac: "); Serial.print(ir_ac);
  Serial.print(" ir_dc_full: "); Serial.println(ir_dc_full);
#endif

  // Reject windows with weak or absent PPG signal
  if (ir_dc < MIN_IR_DC || ir_ac < MIN_IR_AC || ir_dc_full < MIN_IR_DC) {
    send_result(NAN, NAN);
    return;
  }

  // Normalise by std-dev so peak detection isn't sensitive to signal amplitude
  for (int i = 0; i < N_SAMPLES; i++) {
    ir_norm[i] = ir_filt[i] / ir_std;
  }

  // Minimum 0.3s between peaks — rejects anything faster than 200 bpm
  int min_peak_dist = (int)roundf(FS_HZ * 0.3f);
  if (min_peak_dist > Nt - 2) min_peak_dist = Nt - 2;
  if (min_peak_dist < 1) {
    send_result(NAN, NAN);
    return;
  }

  int n_peaks = find_peaks(&ir_norm[start_idx_trim], Nt, min_peak_dist, peak_locs);

  // HR = 60 / mean inter-beat interval
  float hr_est = NAN;
  if (n_peaks >= 2) {
    float ibi_sum = 0.0f;
    for (int i = 1; i < n_peaks; i++) {
      ibi_sum += (float)(peak_locs[i] - peak_locs[i - 1]) / FS_HZ;
    }

    float mean_ibi = ibi_sum / (float)(n_peaks - 1);
    if (mean_ibi > 0.0f) hr_est = 60.0f / mean_ibi;
  }

  // SpO2 from modified Beer-Lambert: R = (ACred/DCred) / (ACir/DCir)
  float red_dc = mean_u32(&red_raw_buf[start_idx_trim], Nt);
  float red_ac = 0.5f * (max_float(&red_filt[start_idx_trim], Nt) - min_float(&red_filt[start_idx_trim], Nt));

  float spo2_est = NAN;
  if (ir_dc > 0.0f && red_dc > 0.0f && ir_ac > 0.0f && red_ac > 0.0f) {
    float R = (red_ac / red_dc) / (ir_ac / ir_dc);
    spo2_est = SPO2_A - SPO2_B * R;
    if (spo2_est > 100.0f) spo2_est = 100.0f;
  }

  send_result(hr_est, spo2_est);

  for (int i = 0; i < n_peaks; i++) {
    uint32_t foot_ts = ppg_ts - (uint32_t)((float)(N_SAMPLES - start_idx_trim - peak_locs[i]) * (1000.0f / FS_HZ));
    bcg_compute_pat(foot_ts, hr_est);
  }
}

void ppg_setup() {
  if (!sensor.begin(Wire, 400000)) {
    while (1) {}  // Halt if sensor not found
  }

  sensor.setup(
    60,             // LED brightness (0–255)
    1,               // sampleAverage — 1 means no averaging, true FS_HZ into FIFO
    2,               // ledMode — 2 = red + IR (required for SpO2)
    (int)FS_HZ,      // sampleRate (Hz) — driven by FS_HZ defined above
    411,             // pulseWidth (µs) — longer = more ADC bits, higher SNR
    4096             // adcRange — maximum range for high-perfusion signals
  );
}

void handle_ppg() {
  int n = sensor.check();
  if (n == 0) return;

  while (n--) {
    uint32_t ir_raw  = sensor.getFIFOIR();
    uint32_t red_raw = sensor.getFIFORed();

// #if PPG_SERIAL
//     // Print raw samples: ir,red
//     Serial.print(ir_raw);
//     Serial.print(",");
//     Serial.println(red_raw);
// #endif

    ir_raw_buf[sample_idx]  = ir_raw;
    red_raw_buf[sample_idx] = red_raw;
    sample_idx++;

    if (sample_idx >= N_SAMPLES) {
      ppg_ts = millis();  // Capture wall-clock time at window completion
      process_window();
      sample_idx = 0;
      window_counter++;
    }
  }
}
