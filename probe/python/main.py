#!/usr/bin/env python3
"""Project Pulse: probe Linux entry point.

Check mode logic (rules.py) runs on each KX134 feature row from the MCU.
Guard mode / report.py / the web page land in later build steps.
"""

import threading
import time

from flask import Flask, Response, redirect, render_template, request, url_for

from arduino.app_utils import *

from features import parse_kx134_features
from guard import IDLE as GUARD_IDLE
from guard import GuardController
from rules import evaluate
from report import generate_guard_note, generate_report
from pdf_export import build_pdf

logger = Logger("project-pulse")
logger.info("Project Pulse probe starting (Check mode)")

flask_app = Flask(__name__)
latest_lock = threading.Lock()
latest = {"features": None, "result": None, "report": None, "rated_hz": None, "guard_note": None}
guard = GuardController()


@call()
def get_mic_stats() -> str: ...


@call()
def get_kx134_stats() -> str: ...


@call()
def get_kx134_features() -> str: ...


@call()
def get_button_event() -> str: ...


@call()
def set_led_state(state: str) -> None: ...


def led_state_for(result: dict) -> str:
    if result["zone"] == "D":
        return "red"
    if result["zone"] in ("B", "C") or result["faults"]:
        return "amber"
    return "green"


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


def poll_button():
    try:
        event = get_button_event()
    except Exception as exc:
        logger.error("get_button_event failed: %s", exc)
        return
    if event == "press":
        guard.button_press()
    elif event == "hold":
        guard.button_hold()


def poll_kx134_features():
    while True:
        try:
            row = parse_kx134_features(get_kx134_features())
            with latest_lock:
                rated_hz = latest["rated_hz"]
            result = evaluate(row, rated_hz)
            logger.info("kx134 features: %s -> %s", row, result)
            with latest_lock:
                latest["features"] = row
                latest["result"] = result
            poll_button()
            led_state = led_state_for(result) if guard.state == GUARD_IDLE else guard.feed(row, result)
            try:
                set_led_state(led_state)
            except Exception as exc:
                logger.error("set_led_state failed: %s", exc)
        except Exception as exc:
            logger.error("get_kx134_features failed: %s", exc)
        time.sleep(1)


@flask_app.route("/", methods=["GET"])
def index():
    with latest_lock:
        return render_template("index.html", guard_state=guard.state, **latest)


@flask_app.route("/rated_hz", methods=["POST"])
def set_rated_hz():
    value = request.form.get("rated_hz", "").strip()
    with latest_lock:
        latest["rated_hz"] = float(value) if value else None
    return redirect(url_for("index"))


@flask_app.route("/guard/press", methods=["POST"])
def guard_press():
    guard.button_press()
    return redirect(url_for("index"))


@flask_app.route("/guard/hold", methods=["POST"])
def guard_hold():
    guard.button_hold()
    return redirect(url_for("index"))


@flask_app.route("/check", methods=["POST"])
def check():
    with latest_lock:
        features, result = latest["features"], latest["result"]
    if features is not None:
        report = generate_report(features, result)
        with latest_lock:
            latest["report"] = report
    return redirect(url_for("index"))


@flask_app.route("/guard/note", methods=["POST"])
def guard_note():
    with latest_lock:
        features, result = latest["features"], latest["result"]
    if features is not None:
        note = generate_guard_note(features, result, guard.heat.h)
        with latest_lock:
            latest["guard_note"] = note
    return redirect(url_for("index"))


def _feature_rows(features) -> list:
    return [
        ("Rotation", f"{features.rotation_hz:.1f} Hz"),
        ("Velocity RMS", f"{features.velocity_rms_mm_s:.2f} mm/s"),
        ("1x/2x/3x", f"{features.amp_1x_g:.3f}/{features.amp_2x_g:.3f}/{features.amp_3x_g:.3f} g"),
        ("High-band ratio", f"{features.band_high_ratio:.2f}"),
        ("Kurtosis", f"{features.kurtosis:.2f}"),
        ("Crest factor", f"{features.crest:.2f}"),
    ]


def _pdf_response(title: str, body: str, rows: list, filename: str) -> Response:
    pdf_bytes = build_pdf(title, body, rows)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@flask_app.route("/check/pdf", methods=["GET"])
def check_pdf():
    with latest_lock:
        features, result, report = latest["features"], latest["result"], latest["report"]
    if features is None or report is None:
        return redirect(url_for("index"))
    rows = [("Zone", result["zone"]), ("Faults", ", ".join(result["faults"]) or "none")] + _feature_rows(features)
    return _pdf_response("Project Pulse - Check report", report, rows, "check-report.pdf")


@flask_app.route("/guard/note/pdf", methods=["GET"])
def guard_note_pdf():
    with latest_lock:
        features, result, note = latest["features"], latest["result"], latest["guard_note"]
    if features is None or note is None:
        return redirect(url_for("index"))
    rows = [
        ("Zone", result["zone"]),
        ("Faults", ", ".join(result["faults"]) or "none"),
        ("Heat budget", f"{guard.heat.h:.2f}"),
    ] + _feature_rows(features)
    return _pdf_response("Project Pulse - Guard note", note, rows, "guard-note.pdf")


threading.Thread(target=poll_mic_stats, daemon=True).start()
threading.Thread(target=poll_kx134_stats, daemon=True).start()
threading.Thread(target=poll_kx134_features, daemon=True).start()
threading.Thread(
    target=lambda: flask_app.run(host="0.0.0.0", port=5001, use_reloader=False),
    daemon=True,
).start()

App.run()
