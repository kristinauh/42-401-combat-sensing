// battery.ino

#define BAT_SEND_INTERVAL 30000  // Send battery level every 30 seconds

uint32_t last_bat_ms = 0;

// B packet: ts(uint32), vbat(int16 x100)
// voltage scaled by 100 to avoid floats over BLE
void send_battery_packet(float vbat) {
#if BAT_SERIAL
  Serial.print("BAT vbat: "); Serial.println(vbat);
#endif

  if (!Bluefruit.connected()) return;

  int16_t vbat_i = (int16_t)lroundf(vbat * 100.0f);

  uint8_t pkt[7];
  pkt[0] = 'B';
  uint32_t ts = millis();
  memcpy(&pkt[1], &ts, 4);
  memcpy(&pkt[5], &vbat_i, 2);

  bleuart.write(pkt, sizeof(pkt));
}

void battery_setup() {
  // VBAT_ENABLE must be pulled low to turn on the voltage divider before reading
  pinMode(VBAT_ENABLE, OUTPUT);
  digitalWrite(VBAT_ENABLE, LOW);
}

void handle_battery() {
  uint32_t now = millis();

  if ((uint32_t)(now - last_bat_ms) < BAT_SEND_INTERVAL) return;
  last_bat_ms = now;

  // analogRead blocks briefly but at 30s intervals it won't disrupt BLE
  int raw = analogRead(PIN_VBAT);
  float vbat = (float)raw * (4.08f / 377.0f);
  send_battery_packet(vbat);
}
