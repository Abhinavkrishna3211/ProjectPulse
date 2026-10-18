// KX134-1211 bring-up (T1): 4-wire SPI, master RX, polled DRDY (no DMA, no
// INT1 yet - the goal here is just to prove real acceleration data flows at
// the target ODR and measure the achieved rate, per planning/test-plan.md
// T1). Runs in its own low-priority Zephyr thread, same pattern as
// mic_sampler, so SPI polling can't block Bridge's RPC thread.
//
// Register addresses/bit layout below are hardware facts (not copyrightable
// code), cross-referenced from the Kionix KX134-1211 datasheet (WHO_AM_I
// value, SPI protocol/timing) and the open-source SparkFun KX13X Arduino
// Library's register header (MIT license; credited in README) for the
// register map the datasheet itself doesn't tabulate (CNTL1, ODCNTL,
// output registers). The driver code itself is written fresh for this
// project.
#include "kx134_sampler.h"

#include <Arduino_RouterBridge.h>
#include <SPI.h>
#include <zephyr/kernel.h>
#include <cmath>

#define KX134_CS_PIN 8

#define KX134_REG_WHO_AM_I 0x13
#define KX134_WHO_AM_I_VAL 0x46
#define KX134_REG_INS2 0x17
#define KX134_INS2_DRDY_MASK 0x10
#define KX134_REG_CNTL1 0x1B
// GSEL=00 (+-8g) | DRDYE=1 (bit5, required for INS2.drdy to ever assert -
// without it DRDY never goes high and no samples are ever read) | PC1=1
#define KX134_CNTL1_PC1 0xA0
#define KX134_REG_ODCNTL 0x21
#define KX134_ODCNTL_OSA_1600HZ 0x0B
#define KX134_REG_XOUT_L 0x08
#define KX134_OUT_BYTES 6  // XOUT_L/H, YOUT_L/H, ZOUT_L/H, burst-read

#define KX134_THREAD_STACK_SIZE 1024
#define KX134_THREAD_PRIORITY 10  // below Bridge, same as mic_sampler

static SPISettings kx134_spi_settings(1000000, MSBFIRST, SPI_MODE0);

K_MUTEX_DEFINE(kx134_stats_mtx);

struct kx134_stats {
  uint32_t rate_hz;
  int16_t min_sample;
  int16_t max_sample;
  uint32_t rms;
  uint32_t clip_count;
};

static struct kx134_stats kx134_stats_latest = {0, 0, 0, 0, 0};
static bool kx134_present = false;

static uint8_t kx134_read_reg(uint8_t addr) {
  SPI.beginTransaction(kx134_spi_settings);
  digitalWrite(KX134_CS_PIN, LOW);
  SPI.transfer(addr | 0x80);
  uint8_t val = SPI.transfer(0x00);
  digitalWrite(KX134_CS_PIN, HIGH);
  SPI.endTransaction();
  return val;
}

static void kx134_read_burst(uint8_t addr, uint8_t *buf, uint8_t len) {
  SPI.beginTransaction(kx134_spi_settings);
  digitalWrite(KX134_CS_PIN, LOW);
  SPI.transfer(addr | 0x80);
  for (uint8_t i = 0; i < len; i++) {
    buf[i] = SPI.transfer(0x00);
  }
  digitalWrite(KX134_CS_PIN, HIGH);
  SPI.endTransaction();
}

static void kx134_write_reg(uint8_t addr, uint8_t val) {
  SPI.beginTransaction(kx134_spi_settings);
  digitalWrite(KX134_CS_PIN, LOW);
  SPI.transfer(addr & 0x7F);
  SPI.transfer(val);
  digitalWrite(KX134_CS_PIN, HIGH);
  SPI.endTransaction();
}

static bool kx134_sampler_init_spi(void) {
  pinMode(KX134_CS_PIN, OUTPUT);
  digitalWrite(KX134_CS_PIN, HIGH);
  SPI.begin();

  uint8_t who = kx134_read_reg(KX134_REG_WHO_AM_I);
  if (who != KX134_WHO_AM_I_VAL) {
    Serial.print("KX134 WHO_AM_I mismatch, got 0x");
    Serial.println(who, HEX);
    return false;
  }

  kx134_write_reg(KX134_REG_CNTL1, 0x00);  // standby - required to change ODCNTL
  kx134_write_reg(KX134_REG_ODCNTL, KX134_ODCNTL_OSA_1600HZ);
  kx134_write_reg(KX134_REG_CNTL1, KX134_CNTL1_PC1);  // operating mode, +-8g
  return true;
}

static void kx134_stats_reset(struct kx134_stats *s) {
  s->rate_hz = 0;
  s->min_sample = 0x7FFF;
  s->max_sample = -0x8000;
  s->rms = 0;
  s->clip_count = 0;
}

static void kx134_sampler_thread_entry(void *p1, void *p2, void *p3) {
  ARG_UNUSED(p1);
  ARG_UNUSED(p2);
  ARG_UNUSED(p3);

  struct kx134_stats acc;
  kx134_stats_reset(&acc);
  uint64_t sumsq = 0;
  uint32_t sample_count = 0;
  int64_t window_start = k_uptime_get();

  while (1) {
    if (kx134_read_reg(KX134_REG_INS2) & KX134_INS2_DRDY_MASK) {
      uint8_t raw[KX134_OUT_BYTES];
      kx134_read_burst(KX134_REG_XOUT_L, raw, KX134_OUT_BYTES);
      int16_t x = (int16_t)(raw[0] | (raw[1] << 8));
      int16_t y = (int16_t)(raw[2] | (raw[3] << 8));
      int16_t z = (int16_t)(raw[4] | (raw[5] << 8));
      // Magnitude, orientation-independent for this bring-up check -
      // per-axis features come later in features.py (Step 3).
      int16_t mag = (int16_t)sqrtf((float)x * x + (float)y * y + (float)z * z);

      if (mag < acc.min_sample) acc.min_sample = mag;
      if (mag > acc.max_sample) acc.max_sample = mag;
      if (mag >= 32000) acc.clip_count++;
      sumsq += (int32_t)mag * (int32_t)mag;
      sample_count++;
    }

    int64_t elapsed_ms = k_uptime_get() - window_start;
    if (elapsed_ms >= 1000) {
      acc.rate_hz = (uint32_t)((uint64_t)sample_count * 1000 / (uint64_t)elapsed_ms);
      acc.rms = sample_count ? (uint32_t)sqrtf((float)sumsq / (float)sample_count) : 0;

      k_mutex_lock(&kx134_stats_mtx, K_FOREVER);
      kx134_stats_latest = acc;
      k_mutex_unlock(&kx134_stats_mtx);

      Serial.print("kx134 rate=");
      Serial.print(acc.rate_hz);
      Serial.print(" min=");
      Serial.print(acc.min_sample);
      Serial.print(" max=");
      Serial.print(acc.max_sample);
      Serial.print(" rms=");
      Serial.print(acc.rms);
      Serial.print(" clip=");
      Serial.println(acc.clip_count);

      kx134_stats_reset(&acc);
      sumsq = 0;
      sample_count = 0;
      window_start = k_uptime_get();
    }
  }
}

static String kx134_get_stats(void) {
  struct kx134_stats s;
  k_mutex_lock(&kx134_stats_mtx, K_FOREVER);
  s = kx134_stats_latest;
  k_mutex_unlock(&kx134_stats_mtx);

  String out;
  out += String(s.rate_hz);
  out += ",";
  out += String(s.min_sample);
  out += ",";
  out += String(s.max_sample);
  out += ",";
  out += String(s.rms);
  out += ",";
  out += String(s.clip_count);
  return out;
}

K_THREAD_STACK_DEFINE(kx134_sampler_thread_stack, KX134_THREAD_STACK_SIZE);
static struct k_thread kx134_sampler_thread_data;

void kx134_sampler_start(void) {
  kx134_present = kx134_sampler_init_spi();
  if (!kx134_present) {
    return;  // Bridge/rest of the app still comes up; "get_kx134_stats" just won't exist
  }

  Bridge.provide("get_kx134_stats", kx134_get_stats);

  k_thread_create(&kx134_sampler_thread_data, kx134_sampler_thread_stack,
                  K_THREAD_STACK_SIZEOF(kx134_sampler_thread_stack),
                  kx134_sampler_thread_entry, NULL, NULL, NULL,
                  KX134_THREAD_PRIORITY, 0, K_NO_WAIT);
  k_thread_name_set(&kx134_sampler_thread_data, "kx134_sampler");
}
