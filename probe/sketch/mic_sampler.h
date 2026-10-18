#ifndef MIC_SAMPLER_H_
#define MIC_SAMPLER_H_

// INMP441 bring-up (T0). SAI1_A has no devicetree node on this core and no
// sketch-level overlay hook, so it's driven directly via STM32 LL registers.
// This first version FIFO-polls (no DMA): proves audio actually flows and
// measures rate/OVR/noise floor/clipping, per planning/test-plan.md T0.
// Call once from setup(), after Bridge.begin().
void mic_sampler_start(void);

#endif  // MIC_SAMPLER_H_
