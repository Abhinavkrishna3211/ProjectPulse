// INMP441 bring-up (T0): SAI1_A as I2S RX master, mono (slot 0), driven by
// hand-written STM32 LL register setup instead of a Zephyr i2s driver -
// this core's shipped firmware has no sai1_a devicetree node and the sketch
// build gives no overlay hook to add one.
//
// Pins: SCK=PB10 (header SCL), WS=PB9 (D10), SD=PC1 (A4), all AF13 - this
// chip's only header-accessible SAI1_A candidates. No MCLK pin; the INMP441
// derives its own timing from SCK/WS.
//
// Clocking: PLL2 (HSE 16MHz, M=1, N=24 -> VCO 384MHz, P=30 -> PLL2_P
// 12.8MHz) feeds SAI1's kernel clock. NODIV=1, MCKDIV=25 gives
// Fs = SAI_CK / (MCKDIV * 32) = 12.8e6 / 800 = 16000 Hz exactly.
//
// This version polls the FIFO directly (SR.FREQ) rather than using DMA: the
// goal of T0 is just to prove the mic produces real audio and to measure the
// achieved rate, OVR count, noise floor and clipping on hardware. A dedicated
// low-priority thread does the polling so it can't block Bridge's RPC
// thread; MIC_THREAD_PRIORITY is a starting guess and should be checked
// against Bridge responsiveness during the T0 hardware test (raise the
// number/lower the priority further if Bridge calls stall while the mic
// runs).
#include "mic_sampler.h"

#include <Arduino_RouterBridge.h>
#define STM32U585xx
#include <stm32u5xx.h>
#include <stm32u5xx_ll_bus.h>
#include <stm32u5xx_ll_gpio.h>
#include <stm32u5xx_ll_rcc.h>
#include <zephyr/kernel.h>
#include <cmath>

#define MIC_MCKDIV 25

#define MIC_THREAD_STACK_SIZE 1024
#define MIC_THREAD_PRIORITY 10  // below Bridge; verify on hardware (see header comment)

#define MIC_CLOCK_WAIT_ITERATIONS 10000  // bounded: don't hang setup() if a clock never locks

K_MUTEX_DEFINE(mic_stats_mtx);

struct mic_stats {
  uint32_t rate_hz;
  uint32_t ovr_count;
  int16_t min_sample;
  int16_t max_sample;
  uint32_t rms;
  uint32_t clip_count;
};

static struct mic_stats mic_stats_latest = {0, 0, 0, 0, 0, 0};

static void mic_configure_af_pin(GPIO_TypeDef *port, uint32_t pin, int pin_num) {
  LL_GPIO_SetPinMode(port, pin, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinSpeed(port, pin, LL_GPIO_SPEED_FREQ_VERY_HIGH);
  LL_GPIO_SetPinPull(port, pin, LL_GPIO_PULL_NO);
  if (pin_num < 8) {
    LL_GPIO_SetAFPin_0_7(port, pin, LL_GPIO_AF_13);
  } else {
    LL_GPIO_SetAFPin_8_15(port, pin, LL_GPIO_AF_13);
  }
}

static bool mic_sampler_init_clocks(void) {
  int i;

  if (!LL_RCC_HSE_IsReady()) {
    LL_RCC_HSE_Enable();
    for (i = 0; i < MIC_CLOCK_WAIT_ITERATIONS && !LL_RCC_HSE_IsReady(); i++) {
    }
    if (!LL_RCC_HSE_IsReady()) {
      return false;
    }
  }

  LL_RCC_PLL2_SetVCOInputRange(LL_RCC_PLLINPUTRANGE_8_16);
  LL_RCC_PLL2_ConfigDomain_SAI(LL_RCC_PLL2SOURCE_HSE, 1, 24, 30);
  LL_RCC_PLL2_EnableDomain_SAI();
  LL_RCC_PLL2_Enable();
  for (i = 0; i < MIC_CLOCK_WAIT_ITERATIONS && !LL_RCC_PLL2_IsReady(); i++) {
  }
  if (!LL_RCC_PLL2_IsReady()) {
    return false;
  }
  LL_RCC_SetSAIClockSource(LL_RCC_SAI1_CLKSOURCE_PLL2);

  LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOB | LL_AHB2_GRP1_PERIPH_GPIOC);
  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SAI1);
  return true;
}

static void mic_sampler_init_sai(void) {
  mic_configure_af_pin(GPIOB, LL_GPIO_PIN_9, 9);    // WS
  mic_configure_af_pin(GPIOB, LL_GPIO_PIN_10, 10);  // SCK
  mic_configure_af_pin(GPIOC, LL_GPIO_PIN_1, 1);    // SD

  SAI1_Block_A->CR1 = 0;
  SAI1_Block_A->CR2 = 0;  // FTH=EMPTY: FREQ asserts as soon as the FIFO has anything

  SAI1_Block_A->FRCR = (31UL << 0)   // FRL: 32-bit frame
                      | (15UL << 8)  // FSALL: 16-bit half-frame
                      | SAI_xFRCR_FSDEF
                      | SAI_xFRCR_FSOFF;

  SAI1_Block_A->SLOTR = (1UL << SAI_xSLOTR_NBSLOT_Pos)    // NBSLOT=2
                       | (1UL << SAI_xSLOTR_SLOTEN_Pos);  // slot 0 only

  SAI1_Block_A->CR1 = SAI_xCR1_MODE_0  // master RX
                     | SAI_xCR1_DS_2   // 16-bit data
                     | SAI_xCR1_NODIV
                     | SAI_xCR1_CKSTR  // experiment: try the other sampling edge (see T0 notes)
                     | (MIC_MCKDIV << SAI_xCR1_MCKDIV_Pos);

  SAI1_Block_A->CR1 |= SAI_xCR1_SAIEN;
}

static void mic_stats_reset(struct mic_stats *s) {
  s->rate_hz = 0;
  s->ovr_count = 0;
  s->min_sample = 0x7FFF;
  s->max_sample = -0x8000;
  s->rms = 0;
  s->clip_count = 0;
}

static void mic_sampler_thread_entry(void *p1, void *p2, void *p3) {
  ARG_UNUSED(p1);
  ARG_UNUSED(p2);
  ARG_UNUSED(p3);

  struct mic_stats acc;
  mic_stats_reset(&acc);
  uint64_t sumsq = 0;
  uint32_t ovr_this_window = 0;
  uint32_t sample_count = 0;
  int64_t window_start = k_uptime_get();

  while (1) {
    while (!(SAI1_Block_A->SR & SAI_xSR_FREQ)) {
    }
    int16_t sample = (int16_t)(SAI1_Block_A->DR & 0xFFFF);

    if (SAI1_Block_A->SR & SAI_xSR_OVRUDR) {
      SAI1_Block_A->CLRFR = SAI_xCLRFR_COVRUDR;
      ovr_this_window++;
    }

    if (sample < acc.min_sample) acc.min_sample = sample;
    if (sample > acc.max_sample) acc.max_sample = sample;
    if (sample >= 32000 || sample <= -32000) acc.clip_count++;
    sumsq += (int32_t)sample * (int32_t)sample;
    sample_count++;

    int64_t elapsed_ms = k_uptime_get() - window_start;
    if (elapsed_ms >= 1000) {
      // Count over the real elapsed window, not a fixed sample target -
      // this is what actually reveals a rate shortfall (missed FIFO
      // reads, preemption) instead of hiding it behind a fixed count.
      acc.rate_hz = (uint32_t)((uint64_t)sample_count * 1000 / (uint64_t)elapsed_ms);
      acc.ovr_count = ovr_this_window;
      acc.rms = (uint32_t)sqrtf((float)sumsq / (float)sample_count);

      k_mutex_lock(&mic_stats_mtx, K_FOREVER);
      mic_stats_latest = acc;
      k_mutex_unlock(&mic_stats_mtx);

      // T0 bring-up readout: Serial is a separate channel from Bridge, so
      // this is safe to print from here. Drop this once Check mode (T1+)
      // consumes get_mic_stats over Bridge instead.
      Serial.print("mic rate=");
      Serial.print(acc.rate_hz);
      Serial.print(" ovr=");
      Serial.print(acc.ovr_count);
      Serial.print(" min=");
      Serial.print(acc.min_sample);
      Serial.print(" max=");
      Serial.print(acc.max_sample);
      Serial.print(" rms=");
      Serial.print(acc.rms);
      Serial.print(" clip=");
      Serial.println(acc.clip_count);

      mic_stats_reset(&acc);
      sumsq = 0;
      ovr_this_window = 0;
      sample_count = 0;
      window_start = k_uptime_get();
    }
  }
}

static String mic_get_stats(void) {
  struct mic_stats s;
  k_mutex_lock(&mic_stats_mtx, K_FOREVER);
  s = mic_stats_latest;
  k_mutex_unlock(&mic_stats_mtx);

  String out;
  out += String(s.rate_hz);
  out += ",";
  out += String(s.ovr_count);
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

K_THREAD_STACK_DEFINE(mic_sampler_thread_stack, MIC_THREAD_STACK_SIZE);
static struct k_thread mic_sampler_thread_data;

void mic_sampler_start(void) {
  if (!mic_sampler_init_clocks()) {
    return;  // Bridge/rest of the app still comes up; "get_mic_stats" just won't exist
  }
  mic_sampler_init_sai();

  Bridge.provide("get_mic_stats", mic_get_stats);

  k_thread_create(&mic_sampler_thread_data, mic_sampler_thread_stack,
                  K_THREAD_STACK_SIZEOF(mic_sampler_thread_stack),
                  mic_sampler_thread_entry, NULL, NULL, NULL,
                  MIC_THREAD_PRIORITY, 0, K_NO_WAIT);
  k_thread_name_set(&mic_sampler_thread_data, "mic_sampler");
}
