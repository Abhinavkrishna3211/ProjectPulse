# Measurements

Every number here comes from a test actually run. Format: date, setup, n, result.

## Gemma 3 1B (llama-server, CPU build) one-shot latency
- Date: 2026-10-18.
- Setup: UNO Q (`pulse`, 192.168.1.8), `~/llama.cpp/llama-server -m ~/models/gemma-3-1b-it-qat-Q4_0.gguf -t 3 -c 2048 --no-webui`, prompt "Say OK.", `n_predict=16`, measured with `curl -w %{time_total}` on the board itself (loopback).
- n = 1.
- Result: prompt eval 4 tokens / 618.8 ms (6.46 tok/s); generation 16 tokens / 3371.1 ms (4.45 tok/s); end-to-end request time 3.997 s.

## T0: INMP441 bring-up (SAI1_A, FIFO polling)
- Date: 2026-10-18.
- Setup: UNO Q (192.168.1.8), INMP441 wired SCK->D21/PB10 (header SCL), WS->D10/PB9, SD->A4/PC1, L/R->GND, VDD->3.3V. SAI1_A master RX, 16kHz target (PLL2 HSE/1/24/30, NODIV, MCKDIV=25), FIFO-polled in a dedicated thread, 1s windows, stats read over Bridge (`get_mic_stats`) from `main.py`, quiet indoor room.
- n = 1 continuous run, read over ~15 s per condition.
- Result (rate_hz, ovr_count, min, max, rms, clip_count per 1s window):
  - Quiet room baseline: rate 16012-16028 Hz (target 16000, <0.2% error); ovr ~2/s; min/max ~-30..+30; rms ~7-8; clip 0.
  - 1 kHz tone (phone speaker, few cm): rate unchanged; min/max ~-125..+127; rms ~20-56; clip 0.
  - 150 Hz tone (phone speaker, few cm): rate unchanged; min/max ~-57..+74; rms ~10-19; clip 0. Weaker response than 1kHz, consistent with small-speaker low-frequency rolloff, not a mic issue.
  - 180 Hz tone: rms ~11-19 (baseline ~7-10); min/max ~-51..+51; clip 0.
  - 200 Hz tone: rms ~16-24; min/max ~-59..+58; clip 0.
  - 250 Hz tone: rms ~14-32; min/max ~-85..+92; clip 0.
  - 300 Hz tone: rms ~15-19; min/max ~-52..+54; clip 0.
  - Fan-off baseline: rate unchanged; rms ~5-8, slightly below fan-on baseline, as expected.
- Note: an earlier build had min/max pinned at exactly 0/32767 every window (SAI `CR1.CKSTR` left at reset default) -  fixed by setting `CKSTR` for the correct RX sampling edge, after which min/max/rms started tracking real audio.
- Conclusion: proportional, non-clipping response confirmed across 150-300 Hz (the motor-vibration-relevant band) and at 1 kHz. T0 passed.

## T1: KX134-1211 bring-up (4-wire SPI, polled DRDY), mic running concurrently
- Date: 2026-10-18.
- Setup: UNO Q (192.168.1.8), KX134 wired SCK/MISO/MOSI->D13/D12/D11 (core SPI object), CS->D8 (software GPIO), 1 MHz SPI clock, SPI_MODE0. CNTL1/ODCNTL configured for +-8g, OSA=1600 Hz, PC1=1, DRDYE=1. Stats (rate_hz, min, max, rms, clip_count of 3-axis magnitude) read over Bridge (`get_kx134_stats`) from `main.py`, 1s windows, INMP441 mic sampling concurrently (`get_mic_stats`), board sitting still on a desk.
- n = 1 continuous run, 50 s logged after the fix below.
- Result: rate 1623-1627 Hz (target 1600, <1.7% error) across the full window; min 2904-3799, max 4781-5085, rms 4305-4340 (magnitude counts, ~1 g resting baseline at 4096 counts/g for +-8g range - consistent with gravity on a still sensor); clip_count 0 throughout. Mic unaffected: 16004-16031 Hz concurrently, same as T0 baseline.
- Bug found and fixed: CNTL1.DRDYE (bit 5) was left at 0 in the first version, only PC1 (bit 7) was set. INS2's DRDY status bit never asserted, so the polling thread never read a sample - rate/min/max/rms stayed pinned at their reset values (0, 32767, -32768, 0) indefinitely even though WHO_AM_I and the SPI link were fine. Fixed by setting CNTL1 = 0xA0 (DRDYE | PC1).
- Conclusion: T1 passed. Achieved rate within tolerance of the 1600 Hz target, no clipping, no interference with the concurrently-running mic.

## Step 3 bring-up: KX134 feature pipeline on STM32 (FFT, velocity RMS, 1x/2x/3x, bands, kurtosis, crest)
- Date: 2026-10-18.
- Setup: UNO Q (192.168.1.8), same KX134 wiring as T1. Added a 1024-sample (Z-axis only, ~0.64 s at the achieved ODR) hand-written radix-2 FFT and feature extraction in `kx134_sampler.cpp`, exposed over Bridge as `get_kx134_features`, polled every 1 s from `main.py` and fed into `rules.py` (ISO 10816 zone + fault-signature rules). Board sitting still on a desk, no motor running - this is a pipeline sanity check, not a fault-detection measurement.
- n = 1 continuous run, ~15 s logged.
- Result: feature rows arrived every ~0.6-1 s with no Bridge errors and no crash; row length ~60-70 chars, well under RPClite's 256-byte limit. `rules.py` consumed every row without error. rotation_hz jumped around between windows (30-120 Hz) and velocity_rms_mm_s sat at 2.4-3.7 mm/s (ISO zone C) with `looseness_or_misalignment` flagged on most windows.
- Important caveat, not a bug: with no motor spinning there is no real periodic signal, so "1x peak" is just picking the loudest noise bin each window (hence it jumping around), and the zone-C/looseness readings are an artifact of the velocity integration (`accel / omega`) amplifying low-frequency acceleration noise near the 10 Hz cutoff, not a real fault signature. These numbers say nothing about real motor behavior.
- Conclusion: the pipeline itself (FFT, feature math, Bridge payload size, rules.py wiring) runs correctly end to end. It is *not yet validated against a real rotating motor* - that's T2-T5, and will also be the first real test of whether the 10 Hz low-cut on velocity RMS is tight enough to avoid noise amplification, or needs raising.

## Check-mode report generation (`report.py`): LLM-vs-fallback pass rate

- Date: 2026-10-18.
- Setup: UNO Q (192.168.1.8), Flask Check-mode app (`main.py` + `templates/index.html`) calling `POST /check`, which calls `report.generate_report()` against the same llama-server/Gemma setup as above, board sitting still on a desk (no motor running, same idle-noise feature rows as the Step 3 entry above).
- Two real bugs were found and fixed before taking this measurement, not model-quality issues:
  1. llama-server was bound to `127.0.0.1` on the host, unreachable from the app's Docker container; restarted with `--host 0.0.0.0`, and `report.py` now resolves the server via the container's default-route gateway (read from `/proc/net/route`, no `ip` binary in the container) instead of hardcoding `127.0.0.1`.
  2. The number validator's regex misread range dashes as minus signs (e.g. "10-800 Hz" parsed as `-800`), rejecting every correct LLM response that mentioned a frequency band. Fixed with a `(?<!\d)` lookbehind so a "-" glued to a preceding digit is treated as a range separator, not a sign; `tests/test_report.py` has a regression test for this.
- n = 11 `POST /check` calls total across this debugging session, 8 after both fixes were deployed and the app restarted (restarting matters: the running Flask process only picks up a new `report.py` on restart, not on file copy alone).
- Result: 8/8 after both fixes and a restart returned genuine Gemma-generated text that passed the number validator (zero invented numbers); before the restart, with the old `report.py` still loaded, 4/4 fell back, confirming the regex was the actual cause, not model unreliability.
- Conclusion: Check-mode report generation works end to end. The small model still occasionally paraphrases loosely or truncates mid-sentence at the current `n_predict=130`/60s-timeout budget; the fallback template remains the safety net for those cases, by design.

## Guard mode: calibrate/learn/guard cycle on a real motor, anomaly + fault debounce

- Date: 2026-10-19.
- Setup: UNO Q (192.168.1.8), Guard mode (`guard.py`) driven from the web UI (`/guard/press`, `/guard/hold`), an old desk fan (visibly wobbling at times) as the test motor, 30 s off-floor calibration with the fan fully stopped, 180 s learn window with the fan running continuously, `ANOMALY_DEBOUNCE = 5` rows for both the IsolationForest anomaly signal and rule-based faults.
- n = 1 clean calibrate->learn->guard cycle (zero `learn() needs at least 2 healthy feature rows` errors in the app logs for this run, confirming the learn window collected enough running rows throughout).
- Result: in `guarding`, velocity RMS sat 7.4-10.1 mm/s (zone D throughout, consistent with this fan's general vibration level), rotation_hz 19-20.6 Hz. `rules.py` flagged `imbalance` (and occasionally `looseness_or_misalignment`) intermittently - one observed run of 8 consecutive rows flagged `imbalance` (amp_1x_g ranging ~0.08-0.13 g, straddling the rule's threshold), which correctly crossed the 5-row debounce and produced a stable amber with no flicker. Shorter (<5 row) fault/anomaly blips did not trigger amber.
- Conclusion: the debounced amber signal reflects a real, sustained condition (this fan's known intermittent wobble/imbalance), not sensor or logic noise. With `ANOMALY_DEBOUNCE = 3` (an earlier value), isolated 3-row fault runs on this same fan still triggered visible amber flicker during normal variation; 5 rows removed that false-flicker while still catching the genuine 8-row fault run above.

## T6: Guard mode false-alarm rate (soak)

- Date: 2026-10-19.
- Setup: UNO Q (192.168.1.8), same old/wobbly desk fan as the entry above, `OFF_FLOOR_K` lowered from 3.0 to 1.5 (see the build-order note below), floor calibrated at 1.9413225806451613 mm/s, `guarding` reached with 166 learn rows at 2026-10-19 05:06:59 UTC.
- n = 1 run, ~10 minutes (shortened from the originally planned 30+ minutes under time pressure, not a full-length soak).
- Result: `docker logs` for the full window (05:06:59-05:16:59 UTC) and the ~2 minutes beyond it contain exactly one `guard` log line - the initial `learning -> guarding` transition. Zero amber, zero red, zero anomaly flags from Guard's own debounced logic. Check-mode's separate `rules.py` zone/fault classifier (which runs every row regardless of Guard state, and is not what Guard acts on) did show a transient zone-D/`imbalance`+`looseness_or_misalignment` read, apparently from a momentary rotation-rate glitch (consecutive 1 s rows alternating ~19 Hz / ~80 Hz) - this did not reach Guard's 5-row debounce and produced no false alarm.
- Conclusion: zero false alarms over the shortened ~10-minute window on this fan. This is a short soak, not a long-duration guarantee - a longer run is the natural follow-up if there's time.
