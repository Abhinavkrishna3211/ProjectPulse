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

#define KX134_THREAD_STACK_SIZE 4096  // FFT buffers (2 x 1024 floats) live on this stack
#define KX134_THREAD_PRIORITY 10  // below Bridge, same as mic_sampler

#define KX134_SENSITIVITY_COUNTS_PER_G 4096.0f  // +-8g range, Table 1 of the datasheet
#define KX134_G_TO_MS2 9.80665f

// FFT window: 1024 samples at ~1600 Hz = 0.64 s, 512 usable bins up to 800 Hz
// (the spec's velocity band) at ~1.5625 Hz/bin. Single Z-axis only for this
// first cut - see the comment on kx134_features_compute for why.
#define FFT_N 1024
#define FFT_LOG2N 10
#define FFT_PI 3.14159265358979323846f

static SPISettings kx134_spi_settings(1000000, MSBFIRST, SPI_MODE0);

K_MUTEX_DEFINE(kx134_stats_mtx);

struct kx134_stats {
  uint32_t rate_hz;
  int16_t min_sample;
  int16_t max_sample;
  uint32_t rms;
  uint32_t clip_count;
};

struct kx134_features {
  float rotation_hz;
  float velocity_rms_mm_s;
  float amp_1x_g;
  float amp_2x_g;
  float amp_3x_g;
  float band_high_ratio;  // 400-800 Hz energy share of the 10-800 Hz band
  float kurtosis;
  float crest;
};

static struct kx134_stats kx134_stats_latest = {0, 0, 0, 0, 0};
static struct kx134_features kx134_features_latest = {0, 0, 0, 0, 0, 0, 0, 0};
static bool kx134_present = false;

// In-place iterative radix-2 decimation-in-time FFT (no CMSIS-DSP on this
// core). im[] must be zeroed by the caller for a real-input transform.
static void fft_transform(float *re, float *im) {
  for (uint32_t i = 1, j = 0; i < FFT_N; i++) {
    uint32_t bit = FFT_N >> 1;
    for (; j & bit; bit >>= 1) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      float t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }

  for (uint32_t len = 2; len <= FFT_N; len <<= 1) {
    float ang = -2.0f * FFT_PI / (float)len;
    float wr = cosf(ang), wi = sinf(ang);
    for (uint32_t i = 0; i < FFT_N; i += len) {
      float cur_wr = 1.0f, cur_wi = 0.0f;
      for (uint32_t j = 0; j < len / 2; j++) {
        float ure = re[i + j], uim = im[i + j];
        float vre = re[i + j + len / 2] * cur_wr - im[i + j + len / 2] * cur_wi;
        float vim = re[i + j + len / 2] * cur_wi + im[i + j + len / 2] * cur_wr;
        re[i + j] = ure + vre;
        im[i + j] = uim + vim;
        re[i + j + len / 2] = ure - vre;
        im[i + j + len / 2] = uim - vim;
        float next_wr = cur_wr * wr - cur_wi * wi;
        float next_wi = cur_wr * wi + cur_wi * wr;
        cur_wr = next_wr;
        cur_wi = next_wi;
      }
    }
  }
}

// Z-axis only (perpendicular to the magnet mount face) for this first Check
// mode cut: the imbalance rule in planning/spec.md wants radial > axial,
// which needs two independent axes compared against the housing's actual
// radial/axial directions - not knowable from mounting orientation alone.
// Z is the right single channel to start tuning thresholds with on T2-T5;
// X/Y comparison is a follow-up once real fault data exists.
// ponytail: no windowing applied (rectangular) - add a Hann window if
// spectral leakage turns out to blur 1x/2x/3x peaks during tuning.
static void kx134_features_compute(const float *accel_g, float sample_rate_hz,
                                    struct kx134_features *out) {
  static float re[FFT_N];
  static float im[FFT_N];

  float mean = 0;
  for (uint32_t i = 0; i < FFT_N; i++) mean += accel_g[i];
  mean /= FFT_N;

  float sum4 = 0, sumsq = 0, peak = 0;
  for (uint32_t i = 0; i < FFT_N; i++) {
    float ac = accel_g[i] - mean;  // remove gravity/mount-angle DC offset
    re[i] = ac;
    im[i] = 0;
    sumsq += ac * ac;
    sum4 += ac * ac * ac * ac;
    if (fabsf(ac) > peak) peak = fabsf(ac);
  }
  float variance = sumsq / FFT_N;
  float stddev = sqrtf(variance);
  out->kurtosis = variance > 0 ? (sum4 / FFT_N) / (variance * variance) : 0;
  out->crest = stddev > 0 ? peak / stddev : 0;

  fft_transform(re, im);

  float bin_hz = sample_rate_hz / (float)FFT_N;
  uint32_t nyquist_bin = FFT_N / 2;

  float mag[FFT_N / 2 + 1];
  for (uint32_t k = 1; k <= nyquist_bin; k++) {
    mag[k] = 2.0f * sqrtf(re[k] * re[k] + im[k] * im[k]) / (float)FFT_N;
  }

  // Rotation (1x): strongest peak in a plausible small-motor speed range
  // (300-12000 RPM -> 5-200 Hz). Starting assumption; narrow per
  // planning/spec.md once real motor speeds are measured.
  uint32_t k_min = (uint32_t)(5.0f / bin_hz);
  uint32_t k_max = (uint32_t)(200.0f / bin_hz);
  if (k_min < 1) k_min = 1;
  if (k_max > nyquist_bin) k_max = nyquist_bin;

  uint32_t rot_bin = k_min;
  for (uint32_t k = k_min; k <= k_max; k++) {
    if (mag[k] > mag[rot_bin]) rot_bin = k;
  }
  out->rotation_hz = rot_bin * bin_hz;
  out->amp_1x_g = mag[rot_bin];

  uint32_t bin_2x = (uint32_t)((2.0f * out->rotation_hz) / bin_hz + 0.5f);
  uint32_t bin_3x = (uint32_t)((3.0f * out->rotation_hz) / bin_hz + 0.5f);
  out->amp_2x_g = (bin_2x >= 1 && bin_2x <= nyquist_bin) ? mag[bin_2x] : 0;
  out->amp_3x_g = (bin_3x >= 1 && bin_3x <= nyquist_bin) ? mag[bin_3x] : 0;

  // Velocity RMS over 10-800 Hz: single-integrate each bin's acceleration
  // amplitude (g -> m/s^2 -> /omega -> m/s -> mm/s), then combine as
  // independent sinusoids (amplitude/sqrt(2) each) to get an overall RMS.
  uint32_t v_k_min = (uint32_t)(10.0f / bin_hz);
  if (v_k_min < 1) v_k_min = 1;
  float vel_sumsq = 0;
  float band_total_sumsq = 0, band_high_sumsq = 0;
  uint32_t high_k_min = (uint32_t)(400.0f / bin_hz);
  for (uint32_t k = v_k_min; k <= nyquist_bin; k++) {
    float f = k * bin_hz;
    float omega = 2.0f * FFT_PI * f;
    float vel_amp_mm_s = (mag[k] * KX134_G_TO_MS2 / omega) * 1000.0f;
    vel_sumsq += vel_amp_mm_s * vel_amp_mm_s;

    float e = mag[k] * mag[k];
    band_total_sumsq += e;
    if (k >= high_k_min) band_high_sumsq += e;
  }
  out->velocity_rms_mm_s = sqrtf(vel_sumsq / 2.0f);
  out->band_high_ratio = band_total_sumsq > 0 ? band_high_sumsq / band_total_sumsq : 0;
}

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
  float measured_rate_hz = 1600.0f;  // refined from the 1s rate stat below

  static float fft_buf[FFT_N];
  uint32_t fft_idx = 0;

  while (1) {
    if (kx134_read_reg(KX134_REG_INS2) & KX134_INS2_DRDY_MASK) {
      uint8_t raw[KX134_OUT_BYTES];
      kx134_read_burst(KX134_REG_XOUT_L, raw, KX134_OUT_BYTES);
      int16_t x = (int16_t)(raw[0] | (raw[1] << 8));
      int16_t y = (int16_t)(raw[2] | (raw[3] << 8));
      int16_t z = (int16_t)(raw[4] | (raw[5] << 8));
      // Magnitude for the 1s bring-up stats (orientation-independent sanity
      // check); Z alone feeds the feature window - see kx134_features_compute.
      int16_t mag = (int16_t)sqrtf((float)x * x + (float)y * y + (float)z * z);

      if (mag < acc.min_sample) acc.min_sample = mag;
      if (mag > acc.max_sample) acc.max_sample = mag;
      if (mag >= 32000) acc.clip_count++;
      sumsq += (int32_t)mag * (int32_t)mag;
      sample_count++;

      fft_buf[fft_idx++] = (float)z / KX134_SENSITIVITY_COUNTS_PER_G;
      if (fft_idx >= FFT_N) {
        struct kx134_features f;
        kx134_features_compute(fft_buf, measured_rate_hz, &f);
        k_mutex_lock(&kx134_stats_mtx, K_FOREVER);
        kx134_features_latest = f;
        k_mutex_unlock(&kx134_stats_mtx);
        fft_idx = 0;
      }
    }

    int64_t elapsed_ms = k_uptime_get() - window_start;
    if (elapsed_ms >= 1000) {
      acc.rate_hz = (uint32_t)((uint64_t)sample_count * 1000 / (uint64_t)elapsed_ms);
      acc.rms = sample_count ? (uint32_t)sqrtf((float)sumsq / (float)sample_count) : 0;
      if (acc.rate_hz > 0) measured_rate_hz = (float)acc.rate_hz;

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

static String kx134_get_features(void) {
  struct kx134_features f;
  k_mutex_lock(&kx134_stats_mtx, K_FOREVER);
  f = kx134_features_latest;
  k_mutex_unlock(&kx134_stats_mtx);

  String out;
  out += String(f.rotation_hz, 2);
  out += ",";
  out += String(f.velocity_rms_mm_s, 3);
  out += ",";
  out += String(f.amp_1x_g, 4);
  out += ",";
  out += String(f.amp_2x_g, 4);
  out += ",";
  out += String(f.amp_3x_g, 4);
  out += ",";
  out += String(f.band_high_ratio, 3);
  out += ",";
  out += String(f.kurtosis, 2);
  out += ",";
  out += String(f.crest, 2);
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
  Bridge.provide("get_kx134_features", kx134_get_features);

  k_thread_create(&kx134_sampler_thread_data, kx134_sampler_thread_stack,
                  K_THREAD_STACK_SIZEOF(kx134_sampler_thread_stack),
                  kx134_sampler_thread_entry, NULL, NULL, NULL,
                  KX134_THREAD_PRIORITY, 0, K_NO_WAIT);
  k_thread_name_set(&kx134_sampler_thread_data, "kx134_sampler");
}
