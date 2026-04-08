//defines.h

#pragma once

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

// motion classifier states
enum FALL_STATES {
    IDLE_FALL = 0,             // Normal monitoring — waiting for free-fall trigger
    CHECK_FALL = 1,            // Collecting post-trigger buffer to look for impact
    ANALYZE_IMPACT = 2,        // Classifying what the event was
    DETECTED_FALL = 3,         // Confirmed fall — emit packet then move to post-fall
    STATIONARY_POST_FALL = 4,  // Waiting to confirm person is still down
    WALKING = 5,
    RUNNING = 6,
    JUMPING = 7,
    LIMPING = 8,
    SITTING = 9,
    SQUATTING = 10
};

enum IMU_COMP {
  ACCEL = 0,
  GYRO = 1
};

// Forward declarations
void battery_setup();
void handle_battery();
void ppg_setup();
void handle_ppg();
void imu_setup();
void rr_setup();
void rr_update(float ax);
void bcg_setup();
void bcg_update(float ax);
extern float bcg_compute_pat(uint32_t ppg_foot_ts, float hr_est);
void handle_imu();
extern uint32_t last_imu_ms;

struct curr_vals_struct {
    float ax;
    float ay;
    float az;
    float gx;
    float gy;
    float gz;
    float A_SVM; // Acceleration signal vector magnitude
    float G_SVM;
    uint32_t curr_time;
    uint32_t delta_time;
    float fall_impact; // Peak A_SVM seen during CHECK_FALL window
    float min_asvm;
    float fall_event_val; // Debug value
};