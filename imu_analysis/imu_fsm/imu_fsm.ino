#include "LSM6DS3.h"
#include "Wire.h"
#include <bluefruit.h>
#include <math.h>

// DEBUGGING MACROS
#define DEBUG_ANGLE 1
#define DEBUG_IMU 1

// constants
const float G = 9.81;
const float RAD_TO_DEG_CONV = 57.295779;
const bool USE_BLE = false;
// macros

// should run at 100Hz
#define LOOP_DELAY 10

// These values are inspired by the paper
#define BUF_SIZE 200
#define IDLE_TRIGGER 0.8
#define CHECK_TRIGGER 1.4

// These values are inspired by the data
#define ACCEL_DEV_THRESHOLD 0.08 // 0.1 in the paper, 0.0845 max from data
#define GYRO_DEV_THRESHOLD 17.1 // 10 in the paper, 17ish from data
#define DEV_BUFFER_SIZE 50 // same as paper

// Thresholds for detecting walking or running, from the data
#define ACCEL_DEV_WALKING 0.13
#define ACCEL_DEV_RUNNING 0.702
#define ASVM_RUN_WALK_THRESHOLD 2.6
#define BUF_SMALL 50 // calculate these things over a smaller buffer to improve responsiveness
#define PEAK_BUF_SIZE 10

// relative comparison, check if final - init angle is greater than the threshold
#define TILT_TRIGGER 30

#define STATIONARY_THRESHOLD 0.15

#define LIMP_SKEWNESS_THRESHOLD 1.5

// Range-based thresholds for event scoring
#define MIN_SCORE 4

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

// Note: the AY value is actually the "AZ" due to the orientation of the device lol

// BLE UART service
BLEUart bleuart;

//Create a instance of class LSM6DS3
LSM6DS3 myIMU(I2C_MODE, 0x6A);    //I2C device address 0x6A


double cal_gx = 1.101100;
double cal_gy = -2.472750;
double cal_gz = 0.921550;

double cal_ax = -0.058177;
double cal_ay = -0.020211;
double cal_az = -0.001846;

// buffers for holding window of data
float gx_buf[BUF_SIZE];
float gy_buf[BUF_SIZE];
float gz_buf[BUF_SIZE];

float ax_buf[BUF_SIZE];
float ay_buf[BUF_SIZE];
float az_buf[BUF_SIZE];

float asvm_buf[BUF_SIZE];
float gsvm_buf[BUF_SIZE];

int update_pos;
int check_pos;
int max_pos;
bool avg_valid;

float A_SVM_mean;
float G_SVM_mean;

struct curr_vals_struct {
    float ax;
    float ay;
    float az;
    float gx;
    float gy;
    float gz;
    float A_SVM; // signal vector magnitude
    float G_SVM;
    uint32_t curr_time;
    uint32_t delta_time;
    float fall_impact;
    float min_asvm;
    float fall_event_val;
};

curr_vals_struct cv = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

// motion classifer states
enum FALL_STATES {
    IDLE_FALL = 0,
    CHECK_FALL = 1,
    ANALYZE_IMPACT = 2,
    DETECTED_FALL = 3,
    STATIONARY_POST_FALL = 4,
    WALKING = 5,
    RUNNING = 6,
    JUMPING = 7,
    LIMPING = 8,
    SITTING = 9,
    SQUATTING = 10
} fall_state;

String fall_state_strings[11] = {"IDLE_FALL", "CHECK_FALL", "ANALYZE_IMPACT", "DETECTED_FALL", "STATIONARY_POST_FALL", "WALKING", "RUNNING", "JUMPING", "LIMPING", "SITTING", "SQUATTING"};

enum IMU_COMP {
    ACCEL = 0,
    GYRO = 1
} imu_comp;

// reset stuff to 0s
void initialize_values() {
    fall_state = IDLE_FALL;
    cv.A_SVM = 0.0;
    cv.G_SVM = 0.0;
    cv.min_asvm = 9999.9f;
    cv.fall_impact = 0.0;
    cv.fall_event_val = 0.0;
    A_SVM_mean = 0.0f;
    G_SVM_mean = 0.0f;
    update_pos = 0;
    check_pos = 0;
    max_pos = 0;
    avg_valid = false;
}

// update values in the buffers
void update_values(bool update_buffers) {
    // read from the IMU
    cv.ax = myIMU.readFloatAccelX() - cal_ax;
    cv.ay = myIMU.readFloatAccelY() - cal_ay;
    cv.az = myIMU.readFloatAccelZ() - cal_az;

    cv.gx = myIMU.readFloatGyroX() - cal_gx;
    cv.gy = myIMU.readFloatGyroY() - cal_gy;
    cv.gz = myIMU.readFloatGyroZ() - cal_gz;

    // update SVMs
    cv.A_SVM = sqrt(sq(cv.ax) + sq(cv.ay) + sq(cv.az));
    cv.G_SVM = sqrt(sq(cv.gx) + sq(cv.gy) + sq(cv.gz));

    // update buffers with new value
    if(update_buffers) {
        ax_buf[update_pos] = cv.ax;
        ay_buf[update_pos] = cv.ay;
        az_buf[update_pos] = cv.az;

        gx_buf[update_pos] = cv.gx;
        gy_buf[update_pos] = cv.gy;
        gz_buf[update_pos] = cv.gz;

        asvm_buf[update_pos] = cv.A_SVM;
        gsvm_buf[update_pos] = cv.G_SVM;

        // increment position pointer
        update_pos = (update_pos + 1) % BUF_SIZE;

        // update means
        if (update_pos > 0) {
        A_SVM_mean = (A_SVM_mean * (update_pos - 1)) / update_pos + cv.A_SVM / update_pos;
        G_SVM_mean = (G_SVM_mean * (update_pos - 1)) / update_pos + cv.G_SVM / update_pos;
        }

        // update if the data is valid or not
        if(!avg_valid & (update_pos >= BUF_SIZE)) {
            avg_valid = true;
        }
    }
    
}

// for debugging
void print_values() {
    Serial.print("AX: "); Serial.print(cv.ax); Serial.print(", ");
    Serial.print("AY: "); Serial.print(cv.ay); Serial.print(", ");
    Serial.print("AZ: "); Serial.print(cv.az); Serial.print(", ");

    Serial.print("GX: "); Serial.print(cv.gx); Serial.print(", ");
    Serial.print("GY: "); Serial.print(cv.gy); Serial.print(", ");
    Serial.print("GZ: "); Serial.print(cv.gz); Serial.print(", ");

    Serial.print("ASVM: "); Serial.print(cv.A_SVM); Serial.print(", ");
    Serial.print("GSVM: "); Serial.print(cv.G_SVM); Serial.print(", ");

    Serial.print("FALL_EVENT: "); Serial.print(cv.fall_event_val); Serial.print(", ");
    Serial.print("STATE: "); Serial.println(fall_state);
}

// Send only critical values over BLE:
// MCU_time, fall_state if in {DETECTED_FALL, STATIONARY_POST_FALL, 
// WALKING, RUNNING, JUMPING_OR_QUICK_SIT}, fall impact in Gs
void send_values_BLE() {
    update_values(1);

    char buffer[160];

    cv.delta_time = millis() - cv.curr_time; // very naive, optimize later
    cv.curr_time = cv.curr_time + cv.delta_time;

    // send time and motion information
    snprintf(buffer, sizeof(buffer),
            ",%.lu,%.3f,%.3f",
            cv.delta_time, cv.fall_event_val, cv.fall_impact);
    Serial.println(buffer);
    bleuart.print(buffer);
}

// send values over serial - use for testing to send all data points to analyze
void send_values_serial() {

    update_values(1);
    char buffer[160];

    cv.delta_time = millis() - cv.curr_time; // very naive, optimize later
    cv.curr_time = cv.curr_time + cv.delta_time;

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

// send values over BLE or serial
void send_values() {
    if(USE_BLE) {
        send_values_BLE();
    }
    else {
        send_values_serial();
    }
}
// returns if there was a high acceleration event, also collect the BUF_SIZE
// samples for later processing
bool check_fall() {
    bool large_accel = false;
    // reset update position
    update_pos = 0;
    check_pos = 0;
    max_pos = 0;
    float max_accel = 0;
    float min_accel = 999.0f;
    for(int i = 0; i < BUF_SIZE; i++) {
        // update_values(1);
        send_values();
        if(cv.A_SVM >= CHECK_TRIGGER) {
            if(!large_accel) {
                check_pos = i; // save index of first suprathreshold ASVM only
            }
            large_accel = true; // found at least one suprathreshold ASVM
        }
        // also update a maximum acceleration for later use
        if(cv.A_SVM >= max_accel) {
            max_accel = cv.A_SVM;
            max_pos = i; // also save index of max accel value
        }

        if(cv.A_SVM <= min_accel) {
            min_accel = cv.A_SVM;
        }
        delay(LOOP_DELAY); // delay since collecting samples
    }

    cv.fall_impact = max_accel;
    cv.min_asvm = min_accel;
    return large_accel;
}

// Calculate stdev over the last DEV_BUFFER_SIZE samples of the buffer
// If doesn't work, consider doing a comparison between earlier samples
// and later samples to show stabilization
float std_dev_check(IMU_COMP dev_type, int buffer_size) {
    float mean = 0.0;
    int start_idx = 0;
    int end_idx = 0;
    if(buffer_size == BUF_SIZE) {
        start_idx = BUF_SIZE - DEV_BUFFER_SIZE;
        end_idx = BUF_SIZE;
        buffer_size = DEV_BUFFER_SIZE;
    }
    else {
        start_idx = 0;
        end_idx = buffer_size;
    }
    // naive implementation, optimize if lag is too bad
    for(int i = start_idx; i < end_idx; i++) {
        float val = (dev_type == ACCEL) ? asvm_buf[i] : gsvm_buf[i];
        mean = mean + val;
    }
    
    mean = mean/buffer_size;

    float variance = 0.0;

    for(int i = start_idx; i < end_idx; i++) {
        float val = (dev_type == ACCEL) ? asvm_buf[i] : gsvm_buf[i];
        variance = variance + (val - mean)*(val-mean);

    }

    variance = variance/buffer_size;
    
    return sqrt(variance);
    
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

    if(DEBUG_ANGLE) {
        Serial.print("******* init: "); Serial.println(avg_init);
        Serial.print("******* final: "); Serial.println(avg_final);
        Serial.print("******* check_pos: "); Serial.println(check_pos);
        Serial.print("******* max_pos: "); Serial.println(max_pos);
        Serial.print("******* max accel: "); Serial.println(cv.fall_impact);
        Serial.print("******* end_idx: "); Serial.println(end_idx);
        Serial.print("******* end_idx - max_pos: "); Serial.println(end_idx - max_pos);
    }

    float tilt_diff = (fabs(avg_final - avg_init));
    cv.fall_event_val = tilt_diff;
    Serial.print("Calculated angle: "); Serial.print(tilt_diff); Serial.print(", TILT_TRIGGER: "); Serial.println(TILT_TRIGGER);
    // return (tilt_diff >= TILT_TRIGGER);
    return tilt_diff;
}

// basically the same as update_values(1) but only updates the buffers
// until a certain buffer_size
void update_buffer(int buffer_size) {
    // reset update position
    update_pos = 0;
    for(int i = 0; i < buffer_size; i++) {
        update_values(1);
    }
    return;
}

// check if person is stationary (low ASVM)
bool check_stationary() {
    bool stationary = false;
    float sum = 0.0;
    for(int i = 0; i < BUF_SMALL; i++) {
        sum = sum + asvm_buf[i];
    }

    float avg_asvm = sum / BUF_SMALL;
    cv.fall_event_val = avg_asvm;
    // ASVM = 1 when stationary
    stationary = (abs(avg_asvm - 1) <= STATIONARY_THRESHOLD);
    return stationary;
}

// ========== SCORER FUNCTIONS ==========

bool in_range(float val, float lo, float hi) {
    return val >= lo && val <= hi;
}

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

float calculate_median(float* arr, int n) {
    // copy so we don't mutate the original buffer
    float temp[n];
    memcpy(temp, arr, n * sizeof(float));

    // insertion sort
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

// Naive algorithm, optimize later
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


void setup() {
    Serial.begin(115200);
    while (!Serial);
    if (myIMU.begin() != 0) {
        Serial.println("Device error");
    } else {
        Serial.println("Device OK!");
    }

    // BLE init
    Bluefruit.begin();
    Bluefruit.setName("XIAO-IMU");

    bleuart.begin();

    Bluefruit.Advertising.addService(bleuart);
    Bluefruit.Advertising.addName();
    Bluefruit.Advertising.start(0); // continuous

    initialize_values();
}

// FSM style motion detection
void loop() {
    if(fall_state == IDLE_FALL) {
        // Serial.println("IN IDLE_FALL");
        send_values();
        cv.fall_event_val = 0.0;
        // right now this is just a instantaneous check but really should 
        // be some small running average
        if(cv.A_SVM <= IDLE_TRIGGER) {
            fall_state = CHECK_FALL;
        }
        else {
            fall_state = IDLE_FALL;
        }
    }

    if(fall_state == CHECK_FALL) {
        send_values();
        Serial.println("IN CHECK_FALL");
        // collect buffer of samples and send
        if(check_fall()) {
            fall_state = ANALYZE_IMPACT;
        }
        else {
            fall_state = IDLE_FALL;
        }
    }

    // analyze values from the buffer to classify the motion
    if(fall_state == ANALYZE_IMPACT) {
        send_values();
        Serial.println("IN ANALYZE_IMPACT");
        // float std_accel = std_dev_check(ACCEL, BUF_SIZE);
        // float std_gyro = std_dev_check(GYRO, BUF_SIZE);
        // float fall_tilt_check = posture_check();
        // bool stabilized_dev =   (std_accel <= ACCEL_DEV_THRESHOLD) &&
        //                         (std_gyro <= GYRO_DEV_THRESHOLD);
        // bool walking_dev =  (std_accel >= ACCEL_DEV_WALKING) &&
        //                     (std_accel <= ACCEL_DEV_RUNNING);
        // bool running_dev =  (std_accel >= ACCEL_DEV_RUNNING);
        // bool running_accel = (cv.fall_impact >= ASVM_RUN_WALK_THRESHOLD);
        // bool limp = calculate_skewness() >= LIMP_SKEWNESS_THRESHOLD;

        fall_state = analyze_event_score();

        // // Fall
        // if(stabilized_dev && fall_tilt_check) {
        //     fall_state = DETECTED_FALL;
        // }
        // // Run
        // else if(running_dev && !fall_tilt_check && running_accel) {
        //     fall_state = RUNNING;
        // }
        // // Walk
        // else if(walking_dev && !fall_tilt_check && !running_accel) {
        //     // Walk and limp
        //     if(limp) {
        //         fall_state = LIMPING;
        //     }
        //     // Normal walk
        //     else {
        //         fall_state = WALKING;
        //     }
        // }
        // // Jump or sit
        // else if(stabilized_dev && !fall_tilt_check) {
        //     fall_state = JUMPING_OR_QUICK_SIT;
        // }
        // // Something else??
        // else {
        //     fall_state = IDLE_FALL;
        // }
    }

    if(fall_state == DETECTED_FALL) {
        Serial.println("IN DETECTED_FALL");
        cv.fall_event_val = 1.0; // toggle fall signal and send
        send_values();
        cv.fall_event_val = 0.0;

        // check if stationary post fall
        update_buffer(BUF_SMALL);
        if(check_stationary()) {
            fall_state = STATIONARY_POST_FALL;
        }
        else {
            // go back to IDLE if moving again
            initialize_values();
            fall_state = IDLE_FALL;
        }
    }

    if(fall_state == STATIONARY_POST_FALL) {
        Serial.println("IN STATIONARY_POST_FALL");
        send_values();
        update_buffer(BUF_SMALL);
        // stay in this state if still unmoving
        if(check_stationary()) {
            fall_state = STATIONARY_POST_FALL;
        }
        // return to idle when moving again
        else {
            initialize_values();
            fall_state = IDLE_FALL;
        }
    }

    // walking and running is ok so just go back to IDLE
    // Add limp detection here
    if(fall_state == WALKING || fall_state == RUNNING) {
        Serial.println("WALKING OR RUNNING");
        send_values();
        fall_state = IDLE_FALL;
    }

    if(fall_state == LIMPING) {
        Serial.println("LIMPING");
        send_values();
        fall_state = IDLE_FALL;
    }

    // jumping and sitting is also ok
    if(fall_state == JUMPING || fall_state == SITTING || fall_state == SQUATTING) {
        Serial.println("IN JUMPING/SITTING/SQUATTING");
        send_values();
        fall_state = IDLE_FALL;
    }

    delay(LOOP_DELAY);
}
