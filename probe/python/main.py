#!/usr/bin/env python3
"""Project Pulse: probe Linux entry point.

Check mode logic (rules.py) runs on each KX134 feature row from the MCU.
Guard mode / report.py / the web page land in later build steps.
"""

import threading
import time

from arduino.app_utils import *

from features import parse_kx134_features
from rules import evaluate

logger = Logger("project-pulse")
logger.info("Project Pulse probe starting (Check mode)")


@call()
def get_mic_stats() -> str: ...


@call()
def get_kx134_stats() -> str: ...


@call()
def get_kx134_features() -> str: ...


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


def poll_kx134_features():
    while True:
        try:
            row = parse_kx134_features(get_kx134_features())
            result = evaluate(row)
            logger.info("kx134 features: %s -> %s", row, result)
        except Exception as exc:
            logger.error("get_kx134_features failed: %s", exc)
        time.sleep(1)


threading.Thread(target=poll_mic_stats, daemon=True).start()
threading.Thread(target=poll_kx134_stats, daemon=True).start()
threading.Thread(target=poll_kx134_features, daemon=True).start()

App.run()
