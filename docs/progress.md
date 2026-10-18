# Progress

## Done
- Step 0: board cleaned (`daybreak` -> `pulse`, 192.168.1.8). Old app/units/models removed, llama-server + Gemma 1B GGUF kept at neutral paths, docker image pruned, 1.1G disk freed. See `docs/board-baseline.md`, `docs/measurements.md`.
- Step 1: repo skeleton. Folders (`probe/sketch`, `probe/python`, `plug/xiao_plug`, `docs`, `tests`, `data/raw`), README, `.gitignore`, `probe/app.yaml`, pinned `sketch.yaml` (Bridge libs at the versions installed on the board), placeholder `sketch.ino` / `main.py`. Private planning notes kept out via `.git/info/exclude`, never gitignored.

## In progress
- Step 2: sensor bring-up. T0 (INMP441, I2S/SAI) and T1 (KX134, I2C) — waiting on hardware to be wired up.

## Blocked
- (none)
