// ble_stream.ino
#include <Wire.h>
#include <MAX30105.h>
#include <Arduino.h>
#include <bluefruit.h>
#include <math.h>
#include <string.h>
#include "LSM6DS3.h"

BLEUart bleuart;
MAX30105 sensor;
LSM6DS3 myIMU(I2C_MODE, 0x6A);

// PPG settings
#define FS_HZ 100.0f          // Sampling rate (Hz) — must match sampleRate below
#define WINDOW_SEC 5.0f       // PPG processing window length
#define N_SAMPLES 500         // Samples per window: FS_HZ * WINDOW_SEC
#define TRIM_SEC 0.13f        // Ignore initial unstable portion of each window

// SpO2 fit: SpO2 = A - B*R
#define SPO2_A 99.6061f
#define SPO2_B 4.7242f

// Minimum signal quality thresholds — windows below these are rejected
#define MIN_IR_DC 20000.0f    // Weak DC means finger is not on sensor
#define MIN_IR_AC 100.0f      // Weak AC means no detectable pulse

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

// IMU settings
const float G = 9.81f;
const float RAD_TO_DEG_CONV = 57.295779f;

#define LOOP_DELAY 10         // IMU update period in ms (100 Hz)

#define BUF_SIZE 200          // Circular buffer depth — covers ~2s of IMU data at 100 Hz
#define IDLE_TRIGGER 0.8      // A_SVM below this suggests free-fall onset
#define CHECK_TRIGGER 1.4     // A_SVM above this during CHECK_FALL suggests impact

// Std-dev thresholds used to classify post-impact motion
#define ACCEL_DEV_THRESHOLD 0.08
#define GYRO_DEV_THRESHOLD 17.1
#define DEV_BUFFER_SIZE 50    // Number of samples evaluated for std-dev check

#define ACCEL_DEV_WALKING 0.13
#define ACCEL_DEV_RUNNING 0.702
#define ASVM_RUN_WALK_THRESHOLD 2.6
#define BUF_SMALL 50          // Short window used for stationary and posture checks

#define TILT_TRIGGER 30       // Degrees of tilt change required to confirm a fall
#define STATIONARY_THRESHOLD 0.15  // Max deviation from 1g to be considered stationary

// IMU calibration offsets — measured at rest, subtracted from raw readings
double cal_gx = 1.101100;
double cal_gy = -2.472750;
double cal_gz = 0.921550;

double cal_ax = -0.058177;
double cal_ay = -0.020211;
double cal_az = -0.001846;

float gx_buf[BUF_SIZE];
float gy_buf[BUF_SIZE];
float gz_buf[BUF_SIZE];

float ax_buf[BUF_SIZE];
float ay_buf[BUF_SIZE];
float az_buf[BUF_SIZE];

float asvm_buf[BUF_SIZE];    // Scalar vector magnitude history for accel
float gsvm_buf[BUF_SIZE];    // Scalar vector magnitude history for gyro

int update_pos = 0;
int check_pos = 0;           // Buffer index where high-accel impact was first seen
int max_pos = 0;             // Buffer index of peak impact acceleration
bool avg_valid = false;

float A_SVM_mean = 0.0f;
float G_SVM_mean = 0.0f;

struct curr_vals_struct {
  float ax;
  float ay;
  float az;
  float gx;
  float gy;
  float gz;
  float A_SVM;               // Acceleration scalar vector magnitude
  float G_SVM;               // Gyro scalar vector magnitude
  uint32_t curr_time;
  uint32_t delta_time;
  float fall_impact;         // Peak A_SVM seen during CHECK_FALL window
  float fall_event_val;      // Diagnostic value sent with motion packet (tilt or avg_asvm)
};

curr_vals_struct cv = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

enum FALL_STATES {
  IDLE_FALL = 0,             // Normal monitoring — waiting for free-fall trigger
  CHECK_FALL = 1,            // Collecting post-trigger buffer to look for impact
  ANALYZE_IMPACT = 2,        // Classifying what the event was
  DETECTED_FALL = 3,         // Confirmed fall — emit packet then move to post-fall
  STATIONARY_POST_FALL = 4,  // Waiting to confirm person is still down
  WALKING = 5,
  RUNNING = 6,
  JUMPING_OR_QUICK_SIT = 7
} fall_state;

enum IMU_COMP {
  ACCEL = 0,
  GYRO = 1
} imu_comp;

uint32_t last_imu_ms = 0;

// Non-blocking state tracking for CHECK_FALL — avoids stalling loop()
int check_fall_count = 0;
bool check_fall_large_accel = false;
float check_fall_max_accel = 0.0f;

int stationary_count = 0;

// Shared helpers

float mean_float(const float *x, int n) {
  float s = 0.0f;
  for (int i = 0; i < n; i++) s += x[i];
  return s / (float)n;
}

float mean_u32(const uint32_t *x, int n) {
  float s = 0.0f;
  for (int i = 0; i < n; i++) s += (float)x[i];
  return s / (float)n;
}

float std_float(const float *x, int n) {
  float m = mean_float(x, n);
  float s = 0.0f;
  for (int i = 0; i < n; i++) {
    float d = x[i] - m;
    s += d * d;
  }
  return sqrtf(s / (float)(n - 1));
}

float max_float(const float *x, int n) {
  float m = x[0];
  for (int i = 1; i < n; i++) {
    if (x[i] > m) m = x[i];
  }
  return m;
}

float min_float(const float *x, int n) {
  float m = x[0];
  for (int i = 1; i < n; i++) {
    if (x[i] < m) m = x[i];
  }
  return m;
}

// PPG processing

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

  // Reject windows with weak or absent PPG signal
  if (ir_dc < MIN_IR_DC || ir_ac < MIN_IR_AC || ir_dc_full < MIN_IR_DC) {
    send_result(NAN, NAN);
    return;
  }

  // Normalise by std-dev so peak detection isn't sensitive to signal amplitude
  for (int i = 0; i < N_SAMPLES; i++) {
    ir_norm[i] = ir_filt[i] / ir_std;
  }

  // Minimum 0.4s between peaks — rejects anything faster than 200 bpm
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
}

void handle_ppg() {
  int n = sensor.check();
  if (n == 0) return;

  while (n--) {
    ir_raw_buf[sample_idx] = sensor.getFIFOIR();
    red_raw_buf[sample_idx] = sensor.getFIFORed();
    sample_idx++;

    if (sample_idx >= N_SAMPLES) {
      ppg_ts = millis();  // Capture wall-clock time at window completion
      process_window();
      sample_idx = 0;
      window_counter++;
    }
  }
}

// IMU processing

void initialize_values() {
  fall_state = IDLE_FALL;
  cv.A_SVM = 0.0f;
  cv.G_SVM = 0.0f;
  cv.fall_impact = 0.0f;
  cv.fall_event_val = 0.0f;
  update_pos = 0;
  check_pos = 0;
  max_pos = 0;
  avg_valid = false;
  A_SVM_mean = 0.0f;
  G_SVM_mean = 0.0f;
  check_fall_count = 0;
  check_fall_large_accel = false;
  check_fall_max_accel = 0.0f;
  stationary_count = 0;
}

// Read IMU, apply calibration offsets, and optionally push into circular buffers
void update_values(bool update_buffers) {
  cv.ax = myIMU.readFloatAccelX() - cal_ax;
  cv.ay = myIMU.readFloatAccelY() - cal_ay;
  cv.az = myIMU.readFloatAccelZ() - cal_az;

  cv.gx = myIMU.readFloatGyroX() - cal_gx;
  cv.gy = myIMU.readFloatGyroY() - cal_gy;
  cv.gz = myIMU.readFloatGyroZ() - cal_gz;

  cv.A_SVM = sqrtf(cv.ax * cv.ax + cv.ay * cv.ay + cv.az * cv.az);
  cv.G_SVM = sqrtf(cv.gx * cv.gx + cv.gy * cv.gy + cv.gz * cv.gz);

  cv.delta_time = millis() - cv.curr_time;
  cv.curr_time += cv.delta_time;

  if (update_buffers) {
    ax_buf[update_pos] = cv.ax;
    ay_buf[update_pos] = cv.ay;
    az_buf[update_pos] = cv.az;

    gx_buf[update_pos] = cv.gx;
    gy_buf[update_pos] = cv.gy;
    gz_buf[update_pos] = cv.gz;

    asvm_buf[update_pos] = cv.A_SVM;
    gsvm_buf[update_pos] = cv.G_SVM;

    update_pos = (update_pos + 1) % BUF_SIZE;

    if (update_pos > 0) {
      A_SVM_mean = (A_SVM_mean * (update_pos - 1)) / update_pos + cv.A_SVM / update_pos;
      G_SVM_mean = (G_SVM_mean * (update_pos - 1)) / update_pos + cv.G_SVM / update_pos;
    }

    if (!avg_valid && update_pos >= BUF_SIZE) {
      avg_valid = true;
    }
  }
}

// Returns std-dev of the most recent DEV_BUFFER_SIZE samples from the circular buffer
float std_dev_check(IMU_COMP dev_type, int buffer_size) {
  float mean = 0.0f;
  int start_idx = 0;
  int end_idx = 0;

  if (buffer_size == BUF_SIZE) {
    // Only evaluate the tail of the full buffer — most recent activity
    start_idx = BUF_SIZE - DEV_BUFFER_SIZE;
    end_idx = BUF_SIZE;
    buffer_size = DEV_BUFFER_SIZE;
  } else {
    start_idx = 0;
    end_idx = buffer_size;
  }

  for (int i = start_idx; i < end_idx; i++) {
    float val = (dev_type == ACCEL) ? asvm_buf[i] : gsvm_buf[i];
    mean += val;
  }

  mean /= buffer_size;

  float variance = 0.0f;
  for (int i = start_idx; i < end_idx; i++) {
    float val = (dev_type == ACCEL) ? asvm_buf[i] : gsvm_buf[i];
    variance += (val - mean) * (val - mean);
  }

  variance /= buffer_size;
  return sqrtf(variance);
}

// Compares body tilt before and after the event to help confirm a fall
// A genuine fall should show a significant change in vertical orientation
bool posture_check() {
  float tilt_init_sum = 0.0f;
  float tilt_final_sum = 0.0f;
  float hor_dist = 0.0f;

  for (int i = 0; i < check_pos; i++) {
    hor_dist = sqrtf(ax_buf[i] * ax_buf[i] + az_buf[i] * az_buf[i]);
    tilt_init_sum += atan2f(ay_buf[i], hor_dist);
  }

  int end_idx = min(BUF_SIZE, max_pos + BUF_SMALL);

  for (int i = max_pos; i < end_idx; i++) {
    hor_dist = sqrtf(ax_buf[i] * ax_buf[i] + az_buf[i] * az_buf[i]);
    tilt_final_sum += atan2f(ay_buf[i], hor_dist);
  }

  float avg_init = (RAD_TO_DEG_CONV * tilt_init_sum) / check_pos;
  float avg_final = (RAD_TO_DEG_CONV * tilt_final_sum) / (end_idx - max_pos);

  float tilt_diff = fabsf(avg_final - avg_init);
  cv.fall_event_val = tilt_diff;
  return (tilt_diff >= TILT_TRIGGER);
}

// Returns true if average A_SVM is close to 1g — person is lying still
bool check_stationary() {
  float sum = 0.0f;
  for (int i = 0; i < BUF_SMALL; i++) {
    sum += asvm_buf[i];
  }

  float avg_asvm = sum / BUF_SMALL;
  cv.fall_event_val = avg_asvm;
  return (fabsf(avg_asvm - 1.0f) <= STATIONARY_THRESHOLD);
}

// M packet: ts(uint32), state(uint8), event_val(int16 x100), impact(int16 x100)
void send_motion_packet() {
  if (!Bluefruit.connected()) return;

  uint8_t pkt[10];
  pkt[0] = 'M';

  uint32_t ts = cv.curr_time;
  int16_t event_i = (int16_t)lroundf(cv.fall_event_val * 100.0f);
  int16_t impact_i = (int16_t)lroundf(cv.fall_impact * 100.0f);
  uint8_t state_i = (uint8_t)fall_state;

  memcpy(&pkt[1], &ts, 4);
  pkt[5] = state_i;
  memcpy(&pkt[6], &event_i, 2);
  memcpy(&pkt[8], &impact_i, 2);

  bleuart.write(pkt, sizeof(pkt));
}

// Fills the event buffer one tick at a time after a low-accel trigger
// Spread across loop() calls to avoid blocking PPG collection
void handle_check_fall_tick() {
  update_values(true);

  if (cv.A_SVM >= CHECK_TRIGGER) {
    if (!check_fall_large_accel) check_pos = check_fall_count;  // Mark where impact started
    check_fall_large_accel = true;
  }

  if (cv.A_SVM >= check_fall_max_accel) {
    check_fall_max_accel = cv.A_SVM;
    max_pos = check_fall_count;  // Track index of peak impact
  }

  check_fall_count++;

  if (check_fall_count >= BUF_SIZE) {
    cv.fall_impact = check_fall_max_accel;

    if (check_fall_large_accel) {
      fall_state = ANALYZE_IMPACT;  // Got free-fall + impact — analyse it
    } else {
      initialize_values();          // No impact seen — likely a false trigger
    }
  }
}

void handle_stationary_tick() {
  update_values(true);
  stationary_count++;

  if (stationary_count >= BUF_SMALL) {
    if (check_stationary()) {
      fall_state = STATIONARY_POST_FALL;  // Still down — maintain fall alert
    } else {
      initialize_values();                // Person is moving again — reset
    }
    stationary_count = 0;
    update_pos = 0;
  }
}

void handle_imu() {
  switch (fall_state) {
    case IDLE_FALL:
      update_values(false);  // No buffering needed — just watching for trigger
      cv.fall_event_val = 0.0f;
      cv.fall_impact = 0.0f;

      // Low acceleration suggests onset of free-fall
      if (cv.A_SVM <= IDLE_TRIGGER) {
        update_pos = 0;
        check_pos = 0;
        max_pos = 0;
        check_fall_count = 0;
        check_fall_large_accel = false;
        check_fall_max_accel = 0.0f;
        fall_state = CHECK_FALL;
      }
      break;

    case CHECK_FALL:
      handle_check_fall_tick();
      break;

    case ANALYZE_IMPACT: {
      float std_accel = std_dev_check(ACCEL, BUF_SIZE);
      float std_gyro = std_dev_check(GYRO, BUF_SIZE);
      bool fall_tilt_check = posture_check();

      // Classify the event based on post-impact motion signature
      bool stabilized_dev = (std_accel <= ACCEL_DEV_THRESHOLD) &&
                            (std_gyro <= GYRO_DEV_THRESHOLD);
      bool walking_dev = (std_accel >= ACCEL_DEV_WALKING) &&
                         (std_accel <= ACCEL_DEV_RUNNING);
      bool running_dev = (std_accel >= ACCEL_DEV_RUNNING);
      bool running_accel = (cv.fall_impact >= ASVM_RUN_WALK_THRESHOLD);

      if (stabilized_dev && fall_tilt_check) {
        fall_state = DETECTED_FALL;
      } else if (running_dev && !fall_tilt_check && running_accel) {
        fall_state = RUNNING;
      } else if (walking_dev && !fall_tilt_check && !running_accel) {
        fall_state = WALKING;
      } else if (stabilized_dev && !fall_tilt_check) {
        fall_state = JUMPING_OR_QUICK_SIT;
      } else {
        initialize_values();  // Unclassifiable — reset and wait
      }
      break;
    }

    case DETECTED_FALL:
      cv.fall_event_val = 1.0f;   // Flag value to distinguish fall packet from post-fall
      send_motion_packet();
      cv.fall_event_val = 0.0f;
      update_pos = 0;
      stationary_count = 0;
      fall_state = STATIONARY_POST_FALL;
      break;

    case STATIONARY_POST_FALL:
      handle_stationary_tick();
      if (fall_state == STATIONARY_POST_FALL && stationary_count == 0) {
        send_motion_packet();  // Periodic update while person remains down
      }
      break;

    case WALKING:
    case RUNNING:
    case JUMPING_OR_QUICK_SIT:
      send_motion_packet();
      initialize_values();
      break;
  }
}

void setup() {
  Wire.begin();

  Bluefruit.begin();
  Bluefruit.setName("XIAO-SENSE");
  bleuart.begin();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.start(0);  // 0 = advertise indefinitely

  if (!sensor.begin(Wire, 400000)) {
    while (1) {}  // Halt if sensor not found
  }

  sensor.setup(
    60,    // LED brightness (0–255)
    1,     // sampleAverage — 1 means no averaging, true 100 Hz into FIFO
    2,     // ledMode — 2 = red + IR (required for SpO2)
    100,   // sampleRate (Hz) — must match FS_HZ
    411,   // pulseWidth (µs) — longer = more ADC bits, higher SNR
    4096   // adcRange — maximum range for high-perfusion signals
  );

  if (myIMU.begin() != 0) {
    while (1) {}  // Halt if IMU not found
  }

  initialize_values();
  cv.curr_time = millis();
  last_imu_ms = millis();
}

void loop() {
  handle_ppg();

  // Run IMU at fixed LOOP_DELAY interval without blocking PPG collection
  uint32_t now = millis();
  if ((uint32_t)(now - last_imu_ms) >= LOOP_DELAY) {
    last_imu_ms += LOOP_DELAY;
    handle_imu();
  }
}