#include <MAX30105.h>
#include "defines.h"
#include <math.h>

// Settings
#define FS_HZ 100.0f
#define WINDOW_SEC 10.0f
#define N_SAMPLES 1000
#define TRIM_SEC 0.13f

#define SPO2_A 98.9724f
#define SPO2_B 1.6658f

#define MIN_IR_DC 5000.0f
#define MIN_IR_AC 20.0f

#define LOW_CUT  0.7f
#define HIGH_CUT 3.5f

MAX30105 sensor;

uint32_t ir_raw_buf[N_SAMPLES];
uint32_t red_raw_buf[N_SAMPLES];

float ir0[N_SAMPLES];
float red0[N_SAMPLES];
float ir_filt[N_SAMPLES];
float red_filt[N_SAMPLES];
float ir_norm[N_SAMPLES];
float scratch1[N_SAMPLES];
float scratch2[N_SAMPLES];
int   peak_locs[N_SAMPLES];

int      sample_idx    = 0;
uint32_t window_counter = 0;
uint32_t ppg_ts        = 0;

static inline void biquad_reset(biquad_t* s) {
  s->z1 = 0.0f;
  s->z2 = 0.0f;
}

static inline float biquad_process(biquad_t* s, float x) {
  float y = s->b0 * x + s->z1;
  s->z1 = s->b1 * x - s->a1 * y + s->z2;
  s->z2 = s->b2 * x - s->a2 * y;
  return y;
}

// Proper bandpass (Butterworth-like via bilinear transform)
void design_bandpass(biquad_t* s, float fs, float f1, float f2) {
  float w0 = 2.0f * M_PI * sqrtf(f1 * f2) / fs;
  float bw = (f2 - f1);
  float Q  = sqrtf(f1 * f2) / bw;

  float alpha = sinf(w0) / (2.0f * Q);
  float cos_w0 = cosf(w0);

  float b0 =  alpha;
  float b1 =  0.0f;
  float b2 = -alpha;
  float a0 =  1.0f + alpha;
  float a1 = -2.0f * cos_w0;
  float a2 =  1.0f - alpha;

  s->b0 = b0 / a0;
  s->b1 = b1 / a0;
  s->b2 = b2 / a0;
  s->a1 = a1 / a0;
  s->a2 = a2 / a0;

  biquad_reset(s);
}

void send_result(float hr, float spo2) {
#if PPG_SERIAL
  Serial.print("PPG hr: "); Serial.print(hr);
  Serial.print(", spo2: "); Serial.println(spo2);
#endif

  if (!Bluefruit.connected()) return;

  int16_t hr_i   = isnan(hr)   ? -1 : (int16_t)lroundf(hr   * 100.0f);
  int16_t spo2_i = isnan(spo2) ? -1 : (int16_t)lroundf(spo2 * 100.0f);

  uint8_t pkt[9];
  pkt[0] = 'R';
  memcpy(&pkt[1], &ppg_ts,   4);
  memcpy(&pkt[5], &hr_i,     2);
  memcpy(&pkt[7], &spo2_i,   2);
  bleuart.write(pkt, sizeof(pkt));
}

void reverse_in_place(float *x, int n) {
  for (int i = 0; i < n / 2; i++) {
    float t = x[i];
    x[i] = x[n - 1 - i];
    x[n - 1 - i] = t;
  }
}

// filtfilt-style bandpass
void bandpass_filtfilt(const float *x, float *y, int n) {
  biquad_t s1, s2;

  design_bandpass(&s1, FS_HZ, LOW_CUT, HIGH_CUT);
  design_bandpass(&s2, FS_HZ, LOW_CUT, HIGH_CUT);

  // forward
  for (int i = 0; i < n; i++) {
    float v = x[i];
    v = biquad_process(&s1, v);
    v = biquad_process(&s2, v);
    scratch1[i] = v;
  }

  reverse_in_place(scratch1, n);

  biquad_reset(&s1);
  biquad_reset(&s2);

  // backward
  for (int i = 0; i < n; i++) {
    float v = scratch1[i];
    v = biquad_process(&s1, v);
    v = biquad_process(&s2, v);
    scratch2[i] = v;
  }

  reverse_in_place(scratch2, n);
  memcpy(y, scratch2, n * sizeof(float));
}

// Signal
int find_peaks(const float *x, int n, int min_peak_dist, int *locs) {
  int count = 0;
  for (int i = 1; i < n - 1; i++) {
    if (x[i] > x[i-1] && x[i] >= x[i+1]) {
      if (count == 0) {
        locs[count++] = i;
      } else {
        int prev = locs[count-1];
        if ((i - prev) >= min_peak_dist) {
          locs[count++] = i;
        } else if (x[i] > x[prev]) {
          locs[count-1] = i;
        }
      }
    }
  }
  return count;
}

float estimate_hr_peaks(const float *x, int n, float fs) {
  float std_val = 0.0f;
  for (int i = 0; i < n; i++) std_val += x[i] * x[i];
  std_val = sqrtf(std_val / n);
  if (std_val == 0.0f) return NAN;

  for (int i = 0; i < n; i++) ir_norm[i] = x[i] / std_val;

  int min_dist = (int)(fs * 0.4f);
  int n_peaks = find_peaks(ir_norm, n, min_dist, peak_locs);
  if (n_peaks < 2) return NAN;

  float ibi_sum = 0.0f;
  for (int i = 1; i < n_peaks; i++)
    ibi_sum += (float)(peak_locs[i] - peak_locs[i-1]) / fs;

  float mean_ibi = ibi_sum / (n_peaks - 1);
  if (mean_ibi <= 0.0f) return NAN;

  return 60.0f / mean_ibi;
}

// Process
void process_window() {
  for (int i = 0; i < N_SAMPLES; i++) {
    ir0[i]  = (float)ir_raw_buf[i];
    red0[i] = (float)red_raw_buf[i];
  }

  float ir_mean  = mean_float(ir0, N_SAMPLES);
  float red_mean = mean_float(red0, N_SAMPLES);

  for (int i = 0; i < N_SAMPLES; i++) {
    ir0[i]  -= ir_mean;
    red0[i] -= red_mean;
  }

  bandpass_filtfilt(ir0, ir_filt, N_SAMPLES);

  #if PPG_SERIAL
  for (int i = 0; i < N_SAMPLES; i++) {
    Serial.println(ir_filt[i]);
  }
  #endif

  bandpass_filtfilt(red0, red_filt, N_SAMPLES);

  float ir_std  = std_float(ir_filt,  N_SAMPLES);
  float red_std = std_float(red_filt, N_SAMPLES);

  if (ir_std == 0.0f || red_std == 0.0f) {
    send_result(NAN, NAN);
    return;
  }

  int start_idx = (int)(TRIM_SEC * FS_HZ);
  int Nt = N_SAMPLES - start_idx;

  float ir_dc = mean_u32(&ir_raw_buf[start_idx], Nt);
  float ir_ac = 0.5f * (max_float(&ir_filt[start_idx], Nt) - min_float(&ir_filt[start_idx], Nt));

  if (ir_dc < MIN_IR_DC || ir_ac < MIN_IR_AC) {
    send_result(NAN, NAN);
    return;
  }

  float hr_est = estimate_hr_peaks(&ir_filt[start_idx], Nt, FS_HZ);

  float red_dc = mean_u32(&red_raw_buf[start_idx], Nt);
  float red_ac = 0.5f * (max_float(&red_filt[start_idx], Nt) - min_float(&red_filt[start_idx], Nt));

  float spo2_est = NAN;
  if (ir_dc > 0 && red_dc > 0 && ir_ac > 0 && red_ac > 0) {
    float R = (red_ac / red_dc) / (ir_ac / ir_dc);
    spo2_est = SPO2_A - SPO2_B * R;
    if (spo2_est > 100.0f) spo2_est = 100.0f;
  }

  send_result(hr_est, spo2_est);
  bcg_compute_pat(ppg_ts, hr_est);
}

// Sensor
void ppg_setup() {
  if (!sensor.begin(Wire, 400000)) {
    while (1) {}
  }

  sensor.setup(150, 1, 2, (int)FS_HZ, 411, 16384);
}

void handle_ppg() {
  int n = sensor.check();
  if (n == 0) return;

  while (n--) {
    ir_raw_buf[sample_idx]  = sensor.getFIFOIR();
    red_raw_buf[sample_idx] = sensor.getFIFORed();
    sample_idx++;

    if (sample_idx >= N_SAMPLES) {
      ppg_ts = millis();
      process_window();
      sample_idx = 0;
      window_counter++;
    }
  }
}