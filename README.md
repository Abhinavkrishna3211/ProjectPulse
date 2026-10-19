# Project Pulse

A magnetic stethoscope for small motors, with an optional plug that can stop them.

Snap the probe onto a running machine and in about 30 seconds it tells you how hard the motor is shaking,
what the likely fault is (imbalance, looseness, overload, bearing wear) and what to check, in plain words.
Leave it mounted and pair it with the stop plug, and it guards that motor: it learns what normal looks like,
warns when something drifts, and cuts power when it has to. Everything runs on an Arduino UNO Q; nothing goes to the cloud.

## Two units
- **Probe:** Arduino UNO Q, KX134 accelerometer, INMP441 microphone, RGB LED, magnet base.
- **Stop plug:** XIAO ESP32-S3 and a relay. An ordinary socket until paired; once paired, it keeps power on only while the probe keeps saying so.

## Two modes
- **Check:** for repair technicians. Severity zone, likely fault and a short report for the customer, with before/after comparison.
- **Guard:** for owners. Learns this motor's normal, tracks run time and load, stops the motor through the paired plug, writes a daily note.

## How it works
- **STM32 (real time):** samples vibration at 1.6 kHz and sound over I2S, computes features every second, enforces hard safety limits, issues signed run permits.
- **Linux (QRB2210):** fault rules, an on-board anomaly model (scikit-learn) for Guard mode, and reports written by Gemma 3 1B (llama.cpp) with every number checked against the measurements.
- **Stop plug:** fail-safe. A stop, a lost link or a bad signature turns the motor off.

## Status
- **Probe, Check mode:** done and tested on real hardware - sensor bring-up, fault rules, zone/LED display, Gemma report generation.
- **Probe, Guard mode:** done and tested on real hardware - calibrate/learn/guard cycle, anomaly + fault debounce, heat-budget stop/cooldown, motor-on/off LED state.
- **Stop plug:** code written, **not yet tested on real hardware**. Logic only; verify with a lamp before ever wiring it to mains.
- Measured results go in `docs/measurements.md`.

## Safety
The stop plug switches mains voltage. Use a relay rated for the load, keep mains wiring inside a closed box, never work on it while plugged in, and test with a lamp first.
This is a diagnostic aid with a fail-safe cut-off, not a certified protection device. Severity zones are field indications, not certified measurements.

## Credits
- llama.cpp, scikit-learn, Gemma 3 (Google), SparkFun KX13X library.
- Some setup steps and the check-and-retry idea for model output are adapted from the author's earlier Daybreak project.

## License
MIT
