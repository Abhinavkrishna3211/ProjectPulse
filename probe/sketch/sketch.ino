// Project Pulse: probe MCU sketch (STM32, via Arduino Zephyr core).
// Skeleton only. Sensor bring-up (INMP441 I2S, KX134 I2C) comes next, once hardware is wired.
// Keep loop() non-blocking: long work here stalls Bridge calls.

#include <Arduino_RouterBridge.h>

void setup() {
  Serial.begin(115200);
  Bridge.begin();
}

void loop() {
  Bridge.update();
  delay(10);
}
