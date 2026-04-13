// ppg_serial_stream.ino

#include <Wire.h>
#include <MAX30105.h>

MAX30105 sensor;

// Change this to set the sampling rate (samples per second)
// Valid options for MAX30102: 50, 100, 200, 400, 800, 1000
#define SAMPLE_RATE 100

void setup() {
  Serial.begin(115200);
  delay(2000);

  if (!sensor.begin(Wire, 400000)) {
    Serial.println("MAX30102 not found");
    while (1) {}
  }

  sensor.setup(
    60,           // LED power
    4,            // sample average
    2,            // red + IR
    SAMPLE_RATE,  // sample rate
    411,          // pulse width
    4096          // ADC range
  );

  Serial.println("PPG ready.");
}

void loop() {
  int n = sensor.check();

  while (n--) {
    uint32_t ir_raw  = sensor.getFIFOIR();
    uint32_t red_raw = sensor.getFIFORed();

    Serial.print(ir_raw);
    Serial.print(",");
    Serial.println(red_raw);
  }
}