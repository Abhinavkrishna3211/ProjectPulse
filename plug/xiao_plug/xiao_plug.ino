// Stop plug: XIAO ESP32-S3 + relay, paired on demand with the probe.
//
// NOT YET TESTED ON HARDWARE. Before ever wiring this to mains: verify the
// relay contact rating covers the machine, test the logic end to end with a
// lamp instead of the machine, and only then connect anything live.
//
// Unpaired = normal socket (relay stays closed/ON, passthrough). Paired =
// relay ON only while valid HMAC permits keep arriving; any gap over
// PERMIT_TIMEOUT_MS opens the relay. Fail-safe: starts every pairing with no
// permit seen yet, so the motor only runs once the link is confirmed live.
//
// Permit packet (8 bytes payload + 32 bytes HMAC-SHA256, over UDP):
//   seq (uint32 big-endian) | unix_time (uint32 big-endian) | hmac(seq+time)
// seq must strictly increase (replay guard); freshness is judged by the
// plug's own clock at receipt, not by the timestamp inside the packet.

#include <WiFi.h>
#include <WiFiUdp.h>
#include <mbedtls/md.h>

#include "config.h"

#define RELAY_PIN 2   // ponytail: placeholder, confirm against actual wiring before use
#define BUTTON_PIN 3  // ponytail: placeholder, confirm against actual wiring before use

const unsigned long PERMIT_TIMEOUT_MS = 2500;
const unsigned long DEBOUNCE_MS = 200;

WiFiUDP udp;
bool paired = false;
uint32_t lastSeq = 0;
unsigned long lastValidPermitMs = 0;
int lastButtonState = HIGH;
unsigned long lastButtonChangeMs = 0;

bool verifyPermit(const uint8_t* packet, size_t len) {
  if (len != 40) return false;
  uint8_t expected[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const uint8_t*)SHARED_SECRET, strlen(SHARED_SECRET));
  mbedtls_md_hmac_update(&ctx, packet, 8);
  mbedtls_md_hmac_finish(&ctx, expected);
  mbedtls_md_free(&ctx);
  if (memcmp(expected, packet + 8, 32) != 0) return false;

  uint32_t seq = ((uint32_t)packet[0] << 24) | ((uint32_t)packet[1] << 16) |
                 ((uint32_t)packet[2] << 8) | packet[3];
  if (seq <= lastSeq) return false;  // replay / out of order
  lastSeq = seq;
  return true;
}

void pollPermits() {
  uint8_t packet[64];
  int len = udp.parsePacket();
  if (len <= 0) return;
  int read = udp.read(packet, sizeof(packet));
  if (verifyPermit(packet, read)) {
    lastValidPermitMs = millis();
  }
}

void pollButton() {
  int state = digitalRead(BUTTON_PIN);
  if (state != lastButtonState && millis() - lastButtonChangeMs > DEBOUNCE_MS) {
    lastButtonChangeMs = millis();
    lastButtonState = state;
    if (state == LOW) {  // pressed, active-low with pull-up
      paired = !paired;
      lastSeq = 0;
      lastValidPermitMs = 0;  // fail-safe: relay stays open until a fresh permit arrives
    }
  }
}

void applyRelay() {
  bool relayOn;
  if (!paired) {
    relayOn = true;  // normal socket
  } else {
    relayOn = lastValidPermitMs != 0 && millis() - lastValidPermitMs < PERMIT_TIMEOUT_MS;
  }
  digitalWrite(RELAY_PIN, relayOn ? HIGH : LOW);
}

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  digitalWrite(RELAY_PIN, HIGH);  // unpaired default: normal socket

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
  }
  udp.begin(PLUG_PORT);
}

void loop() {
  pollButton();
  pollPermits();
  applyRelay();
}
