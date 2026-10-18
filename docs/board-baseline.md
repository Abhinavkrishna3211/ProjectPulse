# Board baseline (UNO Q 4 GB)

Board: hostname renamed `daybreak` -> `pulse`, reachable at 192.168.1.8 (`ssh arduino@pulse.local` or `ssh arduino@192.168.1.8`).
Date: 2026-10-18.

## Before cleanup
- Disk `/`: 9.8G total, 6.0G used, 3.3G free (65%).
- RAM: 3667M total, 514M used, 2168M free, 3152M available. Swap 1833M (0 used).
- Apps: `user:daybreak` (stopped), default auto-start app = Daybreak.
- systemd --user units enabled: `daybreak-llm.service` (llama-server on :8080), `daybreak-bt-speaker.service`, `daybreak-watchdog.timer`.
- Docker images: `python-apps-base:0.10.1` (830M), `ei-models-runner:0.10.0` (969M).
- Largest home dirs: `daybreak-models` 4.6G, `ArduinoApps` 845M, `.arduino15` 660M, `local` 406M, `daybreak-speech` 222M, `daybreak-preserve` 219M, `model-stage` 256M, `daybreak-voices` 181M, `.local` 216M, `.npm` 166M, `.cache` 137M, `sessions-old` 21M, `hey-jarvis.eim` 14M, `llamacpp` 110M.

## Cleanup done
- Stopped/disabled/removed the 3 daybreak systemd user units.
- Cleared the default auto-start app; destroyed `user:daybreak` (`arduino-app-cli app destroy`).
- Moved what's reused to neutral paths: `~/llamacpp/cpu/llama-b11449/` -> `~/llama.cpp/`, `~/daybreak-models/google_gemma-3-1b-it-qat-Q4_0.gguf` -> `~/models/gemma-3-1b-it-qat-Q4_0.gguf`.
- Deleted: rest of `~/daybreak-models` (other Gemma variants), `daybreak-speech/-tts/-voices/-preserve`, `model-stage`, `sessions-old`, `~/llamacpp` (cpu+snapdragon builds, now moved/unused), `~/.local/share/pywhispercpp`, both `hey-jarvis.eim` copies, `edge-impulse-config.json`, `alarm.json`, `~/local/ei-cli`, `~/local/node.tar.xz`, old `t2_smoke*`/`mem_recheck` dirs, and ~50 old `*.sh/*.py/*.log/*.csv` files in `~`, plus 3 stray junk files (`--help` socket, `ssh`, a mis-saved command as a filename).
- Removed unused docker image `ei-models-runner:0.10.0` (freed ~969M as part of the 1.1G disk gain below; `docker image prune` found nothing dangling).
- Renamed the board `daybreak` -> `pulse` (`arduino-app-cli system set-name pulse`).

## After cleanup
- Disk `/`: 9.8G total, 5.0G used, 4.4G free (54%). **+1.1G freed.**
- RAM: 3667M total, 432-437M used, ~2.0-2.1G free, ~3.2G available. Swap unchanged (0 used).
- `arduino-app-cli system cleanup`: nothing further to clean.

## Fresh checks (all passed)
- SSH: `ssh arduino@192.168.1.8` works (hostname now `pulse`).
- `llama-server` from the new path (`~/llama.cpp/llama-server`) with the model at its new path (`~/models/gemma-3-1b-it-qat-Q4_0.gguf`) answers a test prompt. Timing logged in `docs/measurements.md`.
- Empty app skeleton `project-pulse` (`arduino-app-cli app new project-pulse --no-sketch`): created, started, stopped cleanly, then destroyed (Step 1 creates the real one from the repo).
