#include "LSM6DS3.h"
<<<<<<<< HEAD:app/ble_stream_init/ble_stream.ino

BLEUart bleuart;
MAX30105 sensor;
LSM6DS3 myIMU(I2C_MODE, 0x6A);

#define ENABLE_SERIAL_TEST 1
#define DEBUG_IMU 0

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

// IMU constants
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

#define LIMP_SKEWNESS_THRESHOLD 1.5

// Range-based thresholds for event scoring
#define MIN_SCORE 3 // min number of range matches to classify an event

// FALL
#define FALL_ASVM_STD_LO    -0.0174f
#define FALL_ASVM_STD_HI     0.1122f
#define FALL_GSVM_STD_LO    -5.4818f
#define FALL_GSVM_STD_HI    25.9585f
#define FALL_MAX_ASVM_LO     2.2048f
#define FALL_MAX_ASVM_HI     9.0501f
#define FALL_MIN_ASVM_LO     0.3046f
#define FALL_MIN_ASVM_HI     0.7059f
#define FALL_TILT_DIFF_LO   13.8784f
#define FALL_TILT_DIFF_HI   88.4487f
#define FALL_SKEWNESS_LO     1.4838f
#define FALL_SKEWNESS_HI     4.6622f

// LIMP
#define LIMP_ASVM_STD_LO     0.0662f
#define LIMP_ASVM_STD_HI     0.4648f
#define LIMP_GSVM_STD_LO     5.8598f
#define LIMP_GSVM_STD_HI    22.4971f
#define LIMP_MAX_ASVM_LO     1.8062f
#define LIMP_MAX_ASVM_HI     3.0036f
#define LIMP_MIN_ASVM_LO     0.2952f
#define LIMP_MIN_ASVM_HI     0.6898f
#define LIMP_TILT_DIFF_LO   -0.2081f
#define LIMP_TILT_DIFF_HI   15.7581f
#define LIMP_SKEWNESS_LO     1.1049f
#define LIMP_SKEWNESS_HI     2.4283f

// RUN
#define RUN_ASVM_STD_LO      0.3217f
#define RUN_ASVM_STD_HI      1.6061f
#define RUN_GSVM_STD_LO      7.0514f
#define RUN_GSVM_STD_HI    100.2226f
#define RUN_MAX_ASVM_LO      3.2098f
#define RUN_MAX_ASVM_HI      7.8539f
#define RUN_MIN_ASVM_LO     -0.0099f
#define RUN_MIN_ASVM_HI      0.2158f
#define RUN_TILT_DIFF_LO     2.6980f
#define RUN_TILT_DIFF_HI    52.1412f
#define RUN_SKEWNESS_LO      0.9297f
#define RUN_SKEWNESS_HI      4.7800f

// WALK
#define WALK_ASVM_STD_LO     0.0939f
#define WALK_ASVM_STD_HI     0.3622f
#define WALK_GSVM_STD_LO     9.3677f
#define WALK_GSVM_STD_HI    32.5926f
#define WALK_MAX_ASVM_LO     1.4242f
#define WALK_MAX_ASVM_HI     2.0116f
#define WALK_MIN_ASVM_LO     0.3105f
#define WALK_MIN_ASVM_HI     0.7612f
#define WALK_TILT_DIFF_LO   -2.7011f
#define WALK_TILT_DIFF_HI   11.5852f
#define WALK_SKEWNESS_LO     0.7277f
#define WALK_SKEWNESS_HI     1.9725f

// JUMP
#define JUMP_ASVM_STD_LO    -0.5109f
#define JUMP_ASVM_STD_HI     1.1051f
#define JUMP_GSVM_STD_LO    -6.7328f
#define JUMP_GSVM_STD_HI    37.1204f
#define JUMP_MAX_ASVM_LO     3.5655f
#define JUMP_MAX_ASVM_HI     7.7131f
#define JUMP_MIN_ASVM_LO     0.0358f
#define JUMP_MIN_ASVM_HI     0.1124f
#define JUMP_TILT_DIFF_LO   -6.3122f
#define JUMP_TILT_DIFF_HI   79.3750f
#define JUMP_SKEWNESS_LO     0.5459f
#define JUMP_SKEWNESS_HI     3.8936f

// SIT
#define SIT_ASVM_STD_LO     -0.0011f
#define SIT_ASVM_STD_HI      0.0334f
#define SIT_GSVM_STD_LO      0.7608f
#define SIT_GSVM_STD_HI      3.3579f
#define SIT_MAX_ASVM_LO      1.0226f
#define SIT_MAX_ASVM_HI      4.1145f
#define SIT_MIN_ASVM_LO      0.1256f
#define SIT_MIN_ASVM_HI      0.5739f
#define SIT_TILT_DIFF_LO     1.7556f
#define SIT_TILT_DIFF_HI    20.4851f
#define SIT_SKEWNESS_LO      1.1826f
#define SIT_SKEWNESS_HI      1.6645f

// SQUAT
#define SQUAT_ASVM_STD_LO   -0.1059f
#define SQUAT_ASVM_STD_HI    0.4536f
#define SQUAT_GSVM_STD_LO   -7.4134f
#define SQUAT_GSVM_STD_HI   38.1835f
#define SQUAT_MAX_ASVM_LO    1.1479f
#define SQUAT_MAX_ASVM_HI    2.8265f
#define SQUAT_MIN_ASVM_LO    0.0823f
#define SQUAT_MIN_ASVM_HI    0.5547f
#define SQUAT_TILT_DIFF_LO  -1.8043f
#define SQUAT_TILT_DIFF_HI  16.1746f
#define SQUAT_SKEWNESS_LO    0.8107f
#define SQUAT_SKEWNESS_HI    1.5118f
========
#include "defines.h"
>>>>>>>> 41286d5c9c6775bd72c7b2a1681aa7837a1fd755:app/ble_stream/imu.ino

// IMU calibration offsets — measured at rest, subtracted from raw readings
double cal_gx = 1.101100;
double cal_gy = -2.472750;
double cal_gz = 0.921550;

double cal_ax = -0.058177;
double cal_ay = -0.020211;
double cal_az = -0.001846;

// Note: the AY value is actually the "Z" direction due to the
// horizontal orientation of the device
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

curr_vals_struct cv = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

FALL_STATES fall_state;

String fall_state_strings[11] = {"IDLE_FALL", "CHECK_FALL", "ANALYZE_IMPACT", "DETECTED_FALL", "STATIONARY_POST_FALL", "WALKING", "RUNNING", "JUMPING", "LIMPING", "SITTING", "SQUATTING"};

uint32_t last_imu_ms = 0;

// Non-blocking state tracking for CHECK_FALL — avoids stalling loop()
int check_fall_count = 0;
bool check_fall_large_accel = false;
float check_fall_max_accel = 0.0f;

int stationary_count = 0;

LSM6DS3 myIMU(I2C_MODE, 0x6A);

void initialize_values() {
  fall_state = IDLE_FALL;
  cv.A_SVM = 0.0f;
  cv.G_SVM = 0.0f;
  cv.fall_impact = 0.0f;
  cv.fall_event_val = 0.0f;
  cv.min_asvm = 9999.9f;
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

#if DEBUG_SERIAL
  // ax,ay,az,gx,gy,gz,asvm,gsvm,delta_time,fall_event_val,state
  char buf[160];
  snprintf(buf, sizeof(buf),
    "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%lu,%.3f,%s",
    cv.ax, cv.ay, cv.az,
    cv.gx, cv.gy, cv.gz,
    cv.A_SVM, cv.G_SVM,
    cv.delta_time, cv.fall_event_val,
    fall_state_strings[fall_state].c_str());
  Serial.println(buf);
#endif
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
float posture_check() {
  float tilt_init_sum = 0.0f;
  float tilt_final_sum = 0.0f;
  float hor_dist = 0.0f;

  // just calculate across first 25 samples if check_pos is 0 to avoid div by 0
  int end_idx_init = (check_pos == 0) ? 25 : check_pos;

  for (int i = 0; i < end_idx_init; i++) {
    hor_dist = sqrtf(ax_buf[i] * ax_buf[i] + az_buf[i] * az_buf[i]);
    tilt_init_sum += atan2f(ay_buf[i], hor_dist);
  }

  int end_idx = min(BUF_SIZE, max_pos + BUF_SMALL);

  for (int i = max_pos; i < end_idx; i++) {
    hor_dist = sqrtf(ax_buf[i] * ax_buf[i] + az_buf[i] * az_buf[i]);
    tilt_final_sum += atan2f(ay_buf[i], hor_dist);
  }

  float avg_init = (RAD_TO_DEG_CONV * tilt_init_sum) / end_idx_init;
  float avg_final = (RAD_TO_DEG_CONV * tilt_final_sum) / (end_idx - max_pos);

  float tilt_diff = fabsf(avg_final - avg_init);
  cv.fall_event_val = tilt_diff;
  // return (tilt_diff >= TILT_TRIGGER);
  return tilt_diff;
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

float calculate_median(float* arr, int n) {
    // copy so we don't mutate the original buffer
    float temp[n];
    memcpy(temp, arr, n * sizeof(float));

    // insertion sort - efficient for small n (your BUF_SIZE ~50-200)
    for (int i = 1; i < n; i++) {
        float key = temp[i];
        int j = i - 1;
        while (j >= 0 && temp[j] > key) {
            temp[j + 1] = temp[j];
            j--;
        }
        temp[j + 1] = key;
    }

    if (n % 2 == 0)
        return (temp[n/2 - 1] + temp[n/2]) / 2.0f;
    else
        return temp[n/2];
}

// skewness value for use in detecting limps
float calculate_skewness() {
    float above_dev = 0;
    float below_dev = 0;

    int num_above = 0;
    int num_below = 0;

    // calculate median
    float midpoint = calculate_median(asvm_buf, BUF_SIZE);

    // calculate means above/below midpoint value
    for(int i = 0; i < BUF_SIZE; i++) {
        if(asvm_buf[i] > midpoint) {
            above_dev += (asvm_buf[i] - midpoint);
            num_above ++;
        }

        else if(asvm_buf[i] < midpoint) {
            below_dev += (midpoint - asvm_buf[i]);
            num_below ++;
        }
    }

    if(num_above == 0 || num_below == 0) {
        return 1.0;
    }

    else {
        above_dev = above_dev / num_above;
        below_dev = below_dev / num_below;

        return (above_dev / below_dev);
    }
}

// range check for use in scorer functions
bool in_range(float val, float lo, float hi) {
    return val >= lo && val <= hi;
}

// SCORER FUNCTIONS
int score_fall(float asvm_std, float gsvm_std, float max_asvm,
               float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  FALL_ASVM_STD_LO,  FALL_ASVM_STD_HI) +
           in_range(gsvm_std,  FALL_GSVM_STD_LO,  FALL_GSVM_STD_HI) +
           in_range(max_asvm,  FALL_MAX_ASVM_LO,  FALL_MAX_ASVM_HI) +
           in_range(min_asvm,  FALL_MIN_ASVM_LO,  FALL_MIN_ASVM_HI) +
           in_range(tilt_diff, FALL_TILT_DIFF_LO, FALL_TILT_DIFF_HI) +
           in_range(skewness,  FALL_SKEWNESS_LO,  FALL_SKEWNESS_HI);
}

int score_run(float asvm_std, float gsvm_std, float max_asvm,
              float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  RUN_ASVM_STD_LO,  RUN_ASVM_STD_HI) +
           in_range(gsvm_std,  RUN_GSVM_STD_LO,  RUN_GSVM_STD_HI) +
           in_range(max_asvm,  RUN_MAX_ASVM_LO,  RUN_MAX_ASVM_HI) +
           in_range(min_asvm,  RUN_MIN_ASVM_LO,  RUN_MIN_ASVM_HI) +
           in_range(tilt_diff, RUN_TILT_DIFF_LO, RUN_TILT_DIFF_HI) +
           in_range(skewness,  RUN_SKEWNESS_LO,  RUN_SKEWNESS_HI);
}

int score_limp(float asvm_std, float gsvm_std, float max_asvm,
               float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  LIMP_ASVM_STD_LO,  LIMP_ASVM_STD_HI) +
           in_range(gsvm_std,  LIMP_GSVM_STD_LO,  LIMP_GSVM_STD_HI) +
           in_range(max_asvm,  LIMP_MAX_ASVM_LO,  LIMP_MAX_ASVM_HI) +
           in_range(min_asvm,  LIMP_MIN_ASVM_LO,  LIMP_MIN_ASVM_HI) +
           in_range(tilt_diff, LIMP_TILT_DIFF_LO, LIMP_TILT_DIFF_HI) +
           in_range(skewness,  LIMP_SKEWNESS_LO,  LIMP_SKEWNESS_HI);
}

int score_walk(float asvm_std, float gsvm_std, float max_asvm,
               float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  WALK_ASVM_STD_LO,  WALK_ASVM_STD_HI) +
           in_range(gsvm_std,  WALK_GSVM_STD_LO,  WALK_GSVM_STD_HI) +
           in_range(max_asvm,  WALK_MAX_ASVM_LO,  WALK_MAX_ASVM_HI) +
           in_range(min_asvm,  WALK_MIN_ASVM_LO,  WALK_MIN_ASVM_HI) +
           in_range(tilt_diff, WALK_TILT_DIFF_LO, WALK_TILT_DIFF_HI) +
           in_range(skewness,  WALK_SKEWNESS_LO,  WALK_SKEWNESS_HI);
}

int score_jump(float asvm_std, float gsvm_std, float max_asvm,
               float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  JUMP_ASVM_STD_LO,  JUMP_ASVM_STD_HI) +
           in_range(gsvm_std,  JUMP_GSVM_STD_LO,  JUMP_GSVM_STD_HI) +
           in_range(max_asvm,  JUMP_MAX_ASVM_LO,  JUMP_MAX_ASVM_HI) +
           in_range(min_asvm,  JUMP_MIN_ASVM_LO,  JUMP_MIN_ASVM_HI) +
           in_range(tilt_diff, JUMP_TILT_DIFF_LO, JUMP_TILT_DIFF_HI) +
           in_range(skewness,  JUMP_SKEWNESS_LO,  JUMP_SKEWNESS_HI);
}

int score_sit(float asvm_std, float gsvm_std, float max_asvm,
              float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  SIT_ASVM_STD_LO,  SIT_ASVM_STD_HI) +
           in_range(gsvm_std,  SIT_GSVM_STD_LO,  SIT_GSVM_STD_HI) +
           in_range(max_asvm,  SIT_MAX_ASVM_LO,  SIT_MAX_ASVM_HI) +
           in_range(min_asvm,  SIT_MIN_ASVM_LO,  SIT_MIN_ASVM_HI) +
           in_range(tilt_diff, SIT_TILT_DIFF_LO, SIT_TILT_DIFF_HI) +
           in_range(skewness,  SIT_SKEWNESS_LO,  SIT_SKEWNESS_HI);
}

int score_squat(float asvm_std, float gsvm_std, float max_asvm,
                float min_asvm, float tilt_diff, float skewness) {
    return in_range(asvm_std,  SQUAT_ASVM_STD_LO,  SQUAT_ASVM_STD_HI) +
           in_range(gsvm_std,  SQUAT_GSVM_STD_LO,  SQUAT_GSVM_STD_HI) +
           in_range(max_asvm,  SQUAT_MAX_ASVM_LO,  SQUAT_MAX_ASVM_HI) +
           in_range(min_asvm,  SQUAT_MIN_ASVM_LO,  SQUAT_MIN_ASVM_HI) +
           in_range(tilt_diff, SQUAT_TILT_DIFF_LO, SQUAT_TILT_DIFF_HI) +
           in_range(skewness,  SQUAT_SKEWNESS_LO,  SQUAT_SKEWNESS_HI);
}

// score based next_state generation instead of all-or-nothing logic
// if all scores are too low then go to IDLE
FALL_STATES analyze_event_score() {

    float std_accel = std_dev_check(ACCEL, BUF_SIZE);
    float std_gyro = std_dev_check(GYRO, BUF_SIZE);
    float angle_diff = posture_check();
    float skewness = calculate_skewness();
    float max_asvm = cv.fall_impact;
    float min_asvm = cv.min_asvm;

    int scores[7] = {0, 0, 0, 0, 0, 0, 0};
    // generate scores for each event
    scores[0] = score_fall(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[1] = score_limp(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[2] = score_run(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[3] = score_walk(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[4] = score_jump(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[5] = score_sit(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);
    scores[6] = score_squat(std_accel, std_gyro, max_asvm, min_asvm, angle_diff, skewness);

    if(DEBUG_IMU) {
      Serial.print("fall  score: "); Serial.print(scores[0]);
      Serial.print("; limp  score: "); Serial.print(scores[1]); 
      Serial.print("; run   score: "); Serial.print(scores[2]); 
      Serial.print("; walk  score: "); Serial.print(scores[3]); 
      Serial.print("; jump  score: "); Serial.print(scores[4]); 
      Serial.print("; sit   score: "); Serial.print(scores[5]); 
      Serial.print("; squat score: "); Serial.println(scores[6]);
    }

    int high_score_idx = -1;
    int high_score = 0;

    // find event with the highest match score
    for(int i = 0; i < 7; i++) {
        // strictly greater to maintain priority ranking
        if(scores[i] > high_score) {
            high_score = scores[i];
            high_score_idx = i;
        }
    }
    if(DEBUG_IMU) {
      Serial.print("High score index: "); Serial.println(high_score_idx);
    }

    // require fall detection to include angle change to avoid hella false positives from priority ranking
    if(high_score_idx == 0) {
      // discriminate based on angle only
      if(angle_diff >= TILT_TRIGGER) {
        return DETECTED_FALL;
      }
      else if((scores[4] >= scores[5]) && (scores[4] >= scores[6])) {
        return JUMPING;
      }
      else if((scores[5] >= scores[4]) && (scores[5] >= scores[6])) {
        return SITTING;
      }
      else if((scores[6] >= scores[4]) && (scores[6] >= scores[5])) {
        return SQUATTING;
      }
    }

    // no event matched closely enough, return IDLE
    if(high_score < MIN_SCORE) {
        return IDLE_FALL;
    }

    else {
        switch(high_score_idx) {
        case 0: return DETECTED_FALL;
        case 1: return LIMPING;
        case 2: return RUNNING;
        case 3: return WALKING;
        case 4: return JUMPING;
        case 5: return SITTING;
        case 6: return SQUATTING;
        default: return IDLE_FALL;
        }
    }
}
<<<<<<<< HEAD:app/ble_stream_init/ble_stream.ino
// M packet: ts(uint32), state(uint8), event_val(int16 x100), impact(int16 x100)
void send_motion_packet() {
  if (!Bluefruit.connected() && !ENABLE_SERIAL_TEST) return;
========

// M packet: ts(uint32), state(uint8), event_val(int16 x100), impact(int16 x100)
void send_motion_packet() {
#if DEBUG_SERIAL
  Serial.print("IMU state: "); Serial.println(fall_state_strings[fall_state]);
#else
  if (!Bluefruit.connected()) return;
>>>>>>>> 41286d5c9c6775bd72c7b2a1681aa7837a1fd755:app/ble_stream/imu.ino

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
#endif
}

// send all data points for external analysis
void send_motion_packet_serial() {
  if(ENABLE_SERIAL_TEST) {
    // also don't print every line if debugging
    if(DEBUG_IMU && ((fall_state != IDLE_FALL) || (fall_state != CHECK_FALL) || (fall_state != STATIONARY_POST_FALL))) {
      return;
    }
    char buffer[160];

    // send accel values
    snprintf(buffer, sizeof(buffer),
            "%.3f,%.3f,%.3f",
            cv.ax, cv.ay, cv.az);
    Serial.print(buffer);

    // send gyro values
    snprintf(buffer, sizeof(buffer),
            ",%.3f,%.3f,%.3f",
            cv.gx, cv.gy, cv.gz);
    Serial.print(buffer);

    // send svm values
    snprintf(buffer, sizeof(buffer),
            ",%.3f,%.3f",
            cv.A_SVM, cv.G_SVM);
    Serial.print(buffer);
      // send time and fall_event values
    snprintf(buffer, sizeof(buffer),
            ",%.lu,%.3f,",
            cv.delta_time, cv.fall_event_val);
    Serial.print(buffer);
    Serial.println(fall_state_strings[fall_state]);
  }
}

// Fills the event buffer one tick at a time after a low-accel trigger
// Spread across loop() calls to avoid blocking PPG collection
void handle_check_fall_tick() {
  update_values(true); // save values to the buffer now
  send_motion_packet_serial();
  if (cv.A_SVM >= CHECK_TRIGGER) {
    if (!check_fall_large_accel) check_pos = check_fall_count;  // Mark where impact started
    check_fall_large_accel = true;
  }

  if (cv.A_SVM >= check_fall_max_accel) {
    check_fall_max_accel = cv.A_SVM;
    max_pos = check_fall_count;  // Track index of peak impact
  }

  // also store the minimum impact value, but no index tracking needed
  cv.min_asvm = min(cv.min_asvm, cv.A_SVM);

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
  send_motion_packet_serial();
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

void imu_setup() {
  if (myIMU.begin() != 0) {
    while (1) {}  // Halt if IMU not found
  }

  initialize_values();
  cv.curr_time = millis();
  last_imu_ms = millis();
}

// Run strictly once per tick
void handle_imu() {
  switch (fall_state) {
    case IDLE_FALL:
      update_values(false);  // No buffering needed — just watching for trigger
      send_motion_packet_serial();
      cv.fall_event_val = 0.0f;
      cv.fall_impact = 0.0f;

      // Low acceleration suggests onset of free-fall, initialize values for
      // CHECK_FALL state
      if (cv.A_SVM <= IDLE_TRIGGER) {
        update_pos = 0;
        check_pos = 0;
        max_pos = 0;
        check_fall_count = 0;
        check_fall_large_accel = false;
        check_fall_max_accel = 0.0f;
        fall_state = CHECK_FALL; // start loading sample buffer on next clock
      }
      break;

    case CHECK_FALL:
      handle_check_fall_tick();
      break;

    case ANALYZE_IMPACT: {
      // float std_accel = std_dev_check(ACCEL, BUF_SIZE);
      // float std_gyro = std_dev_check(GYRO, BUF_SIZE);
      // bool fall_tilt_check = posture_check();

      // // Classify the event based on post-impact motion signature
      // bool stabilized_dev = (std_accel <= ACCEL_DEV_THRESHOLD) &&
      //                       (std_gyro <= GYRO_DEV_THRESHOLD);
      // bool walking_dev = (std_accel >= ACCEL_DEV_WALKING) &&
      //                    (std_accel <= ACCEL_DEV_RUNNING);
      // bool running_dev = (std_accel >= ACCEL_DEV_RUNNING);
      // bool running_accel = (cv.fall_impact >= ASVM_RUN_WALK_THRESHOLD);

      // if (stabilized_dev && fall_tilt_check) {
      //   fall_state = DETECTED_FALL;
      // } else if (running_dev && !fall_tilt_check && running_accel) {
      //   fall_state = RUNNING;
      // } else if (walking_dev && !fall_tilt_check && !running_accel) {
      //   fall_state = WALKING;
      // } else if (stabilized_dev && !fall_tilt_check) {
      //   fall_state = JUMPING_OR_QUICK_SIT;
      // } else {
      //   initialize_values();  // Unclassifiable — reset and wait
      // }
      send_motion_packet_serial();
      fall_state = analyze_event_score();
      // reset values for next clock if going back to IDLE
      if(fall_state == IDLE_FALL) {
        initialize_values();
      }
      break;
    }

    case DETECTED_FALL:
      cv.fall_event_val = 1.0f;   // Flag value to distinguish fall packet from post-fall
      send_motion_packet();
      send_motion_packet_serial();
      cv.fall_event_val = 0.0f;
      update_pos = 0; // reset buffer idx for stationary buffer analysis
      stationary_count = 0;
      fall_state = STATIONARY_POST_FALL;
      break;

    case STATIONARY_POST_FALL:
      handle_stationary_tick();
      if (fall_state == STATIONARY_POST_FALL && stationary_count == 0) {
        send_motion_packet();  // Periodic update while person remains down
      }
      break;
    // for demo, just sending all motion classification results instead of injury-only
    case LIMPING:
    case WALKING:
    case RUNNING:
    case JUMPING:
    case SITTING:
    case SQUATTING:
      send_motion_packet();
      send_motion_packet_serial();
      initialize_values(); // reset state for new detection window
      break;
  }
}
<<<<<<<< HEAD:app/ble_stream_init/ble_stream.ino

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
  
  if(ENABLE_SERIAL_TEST) {
    Serial.begin(115200);
    while(!Serial);
  }
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
========
>>>>>>>> 41286d5c9c6775bd72c7b2a1681aa7837a1fd755:app/ble_stream/imu.ino
