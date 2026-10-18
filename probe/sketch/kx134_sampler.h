#ifndef KX134_SAMPLER_H_
#define KX134_SAMPLER_H_

// KX134-1211 bring-up (T1): 4-wire SPI, polled (no interrupt yet).
// Pins per planning/wiring.md: SCK D13, MISO D12, MOSI D11 (core's bundled
// SPI object), CS D8 (software GPIO), INT1 D9 (wired, not used by this
// first version). Verifies WHO_AM_I == 0x46 at boot; if that fails,
// get_kx134_stats is never registered so the fault is visible from Python.
// Call once from setup(), after Bridge.begin().
void kx134_sampler_start(void);

#endif  // KX134_SAMPLER_H_
