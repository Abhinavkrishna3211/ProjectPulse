#!/usr/bin/env python3
"""Project Pulse: probe Linux entry point. Skeleton only (Step 1).

Check mode and Guard mode logic land in rules.py / model.py / report.py
once sensor features are flowing from the MCU over the Bridge (Step 2+).
"""

import threading
import time

from arduino.app_utils import *

logger = Logger("project-pulse")
logger.info("Project Pulse probe starting (skeleton)")


@call()
def get_mic_stats() -> str: ...


@call()
def get_kx134_stats() -> str: ...


def poll_mic_stats():
    while True:
        try:
            logger.info("mic stats: %s", get_mic_stats())
        except Exception as exc:
            logger.error("get_mic_stats failed: %s", exc)
        time.sleep(1)


def poll_kx134_stats():
    while True:
        try:
            logger.info("kx134 stats: %s", get_kx134_stats())
        except Exception as exc:
            logger.error("get_kx134_stats failed: %s", exc)
        time.sleep(1)


threading.Thread(target=poll_mic_stats, daemon=True).start()
threading.Thread(target=poll_kx134_stats, daemon=True).start()

App.run()
