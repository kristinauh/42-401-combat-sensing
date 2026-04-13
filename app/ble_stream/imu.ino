//imu.ino

#include "LSM6DS3.h"
#include "defines.h"

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

#if IMU_DEBUG
    Serial.print("fall  score: "); Serial.print(scores[0]);
    Serial.print("; limp  score: "); Serial.print(scores[1]);
    Serial.print("; run   score: "); Serial.print(scores[2]);
    Serial.print("; walk  score: "); Serial.print(scores[3]);
    Serial.print("; jump  score: "); Serial.print(scores[4]);
    Serial.print("; sit   score: "); Serial.print(scores[5]);
    Serial.print("; squat score: "); Serial.println(scores[6]);
#endif

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

#if IMU_DEBUG
    Serial.print("high score index: "); Serial.println(high_score_idx);
#endif

    // require fall detection to include angle change to avoid false positives from priority ranking
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

// Send all data points over serial for external analysis
void send_motion_packet_serial() {
#if !IMU_SERIAL
  return;
#endif

  char buffer[160];

  // send accel values
  snprintf(buffer, sizeof(buffer), "%.3f,%.3f,%.3f", cv.ax, cv.ay, cv.az);
  Serial.print(buffer);

  // send gyro values
  snprintf(buffer, sizeof(buffer), ",%.3f,%.3f,%.3f", cv.gx, cv.gy, cv.gz);
  Serial.print(buffer);

  // send svm values
  snprintf(buffer, sizeof(buffer), ",%.3f,%.3f", cv.A_SVM, cv.G_SVM);
  Serial.print(buffer);

  // send time and fall_event values
  snprintf(buffer, sizeof(buffer), ",%lu,%.3f,", cv.delta_time, cv.fall_event_val);
  Serial.print(buffer);

  Serial.println(fall_state_strings[fall_state]);
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
  rr_update(cv.ax);
  bcg_update(cv.ax);

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
