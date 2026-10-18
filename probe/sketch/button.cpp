#include "button.h"

#include <Arduino.h>
#include <Arduino_RouterBridge.h>

// Short press starts Guard-mode calibration; a 2 s hold acks a latched
// STOP. See planning/wiring.md (pin) and planning/spec.md (hold time).
static const int PIN_BUTTON = 2;
static const unsigned long HOLD_MS = 2000;
static const unsigned long DEBOUNCE_MS = 30;

static bool pressed = false;
static unsigned long pressed_at = 0;
static unsigned long last_change = 0;
static bool hold_sent = false;
static String pending = "none";

// Polled by Python once a second; must not miss a quick press, so the edge
// detection in button_update() runs every loop() iteration instead.
static String get_button_event() {
  String event = pending;
  pending = "none";
  return event;
}

void button_start() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  Bridge.provide_safe("get_button_event", get_button_event);
}

void button_update() {
  bool down = digitalRead(PIN_BUTTON) == LOW;
  unsigned long now = millis();
  if (down != pressed && now - last_change > DEBOUNCE_MS) {
    last_change = now;
    pressed = down;
    if (pressed) {
      pressed_at = now;
      hold_sent = false;
    } else if (!hold_sent) {
      pending = "press";
    }
  }
  if (pressed && !hold_sent && now - pressed_at >= HOLD_MS) {
    hold_sent = true;
    pending = "hold";
  }
}
