#include "led.h"

#include <Arduino.h>
#include <Arduino_RouterBridge.h>

// Common anode: a pin driven LOW sinks current through that color's
// resistor and turns it on; HIGH turns it off. See planning/wiring.md.
static const int PIN_R = 3;
static const int PIN_G = 5;
static const int PIN_B = 6;

static void led_off() {
  digitalWrite(PIN_R, HIGH);
  digitalWrite(PIN_G, HIGH);
  digitalWrite(PIN_B, HIGH);
}

static void led_set_state(String state) {
  led_off();
  if (state == "blue") {
    digitalWrite(PIN_B, LOW);
  } else if (state == "green") {
    digitalWrite(PIN_G, LOW);
  } else if (state == "amber") {
    digitalWrite(PIN_R, LOW);
    digitalWrite(PIN_G, LOW);
  } else if (state == "red") {
    digitalWrite(PIN_R, LOW);
  }
  // any other value (including "off"): stays off.
}

void led_start() {
  pinMode(PIN_R, OUTPUT);
  pinMode(PIN_G, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  led_off();
  Bridge.provide_safe("set_led_state", led_set_state);
}
