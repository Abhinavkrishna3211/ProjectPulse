# Measurements

Every number here comes from a test actually run. Format: date, setup, n, result.

## Gemma 3 1B (llama-server, CPU build) one-shot latency
- Date: 2026-10-18.
- Setup: UNO Q (`pulse`, 192.168.1.8), `~/llama.cpp/llama-server -m ~/models/gemma-3-1b-it-qat-Q4_0.gguf -t 3 -c 2048 --no-webui`, prompt "Say OK.", `n_predict=16`, measured with `curl -w %{time_total}` on the board itself (loopback).
- n = 1.
- Result: prompt eval 4 tokens / 618.8 ms (6.46 tok/s); generation 16 tokens / 3371.1 ms (4.45 tok/s); end-to-end request time 3.997 s.
