#!/usr/bin/env python3
"""Project Pulse: probe Linux entry point.

Check mode logic (rules.py) runs on each KX134 feature row from the MCU.
Guard mode / report.py / the web page land in later build steps.
"""

import threading
import time

from flask import Flask, render_template, request

from arduino.app_utils import *

from features import parse_kx134_features
from rules import evaluate
from report import generate_report

logger = Logger("project-pulse")
logger.info("Project Pulse probe starting (Check mode)")

flask_app = Flask(__name__)
latest_lock = threading.Lock()
latest = {"features": None, "result": None, "report": None}


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
            with latest_lock:
                latest["features"] = row
                latest["result"] = result
        except Exception as exc:
            logger.error("get_kx134_features failed: %s", exc)
        time.sleep(1)


@flask_app.route("/", methods=["GET"])
def index():
    with latest_lock:
        return render_template("index.html", **latest)


@flask_app.route("/check", methods=["POST"])
def check():
    with latest_lock:
        features, result = latest["features"], latest["result"]
    if features is not None:
        report = generate_report(features, result)
        with latest_lock:
            latest["report"] = report
    with latest_lock:
        return render_template("index.html", **latest)


threading.Thread(target=poll_mic_stats, daemon=True).start()
threading.Thread(target=poll_kx134_stats, daemon=True).start()
threading.Thread(target=poll_kx134_features, daemon=True).start()
threading.Thread(
    target=lambda: flask_app.run(host="0.0.0.0", port=5001, use_reloader=False),
    daemon=True,
).start()

App.run()
