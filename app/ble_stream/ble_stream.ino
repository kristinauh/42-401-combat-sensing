// ble_stream.ino

#include <Wire.h>
#include <Arduino.h>
#include <bluefruit.h>
#include <math.h>
#include <string.h>
#include "defines.h"

// Set to 1 to stream IMU and PPG data over serial
#define PPG_SERIAL 0
#define IMU_SERIAL 1 // for data collection
#define RR_SERIAL 0
#define BP_SERIAL 0
#define BAT_SERIAL 0  // battery

#define IMU_DEBUG 0 // so debug prints don't clobber data collection

BLEUart bleuart;

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

void setup() {
  Serial.begin(115200);

  Wire.begin();

  Bluefruit.begin();
  Bluefruit.setName("XIAO-SENSE");
  bleuart.begin();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.start(0);  // 0 = advertise indefinitely

  battery_setup();
  ppg_setup();
  imu_setup();
  rr_setup();
  bcg_setup();
}

void loop() {
  handle_ppg();
  handle_battery();

  // Run IMU at fixed LOOP_DELAY interval without blocking PPG collection
  uint32_t now = millis();
  if ((uint32_t)(now - last_imu_ms) >= LOOP_DELAY) {
    last_imu_ms += LOOP_DELAY;
    handle_imu();
  }
}
