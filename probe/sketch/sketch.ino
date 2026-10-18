// Project Pulse: probe MCU sketch (STM32, via Arduino Zephyr core).
// Keep loop() non-blocking: long work here stalls Bridge calls.

#include <Arduino_RouterBridge.h>

#include "kx134_sampler.h"
#include "led.h"
#include "mic_sampler.h"

void setup() {
  Serial.begin(115200);
  Bridge.begin();
  mic_sampler_start();
  kx134_sampler_start();
  led_start();
}

void loop() {
  Bridge.update();
  delay(10);
}
