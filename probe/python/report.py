"""Check-mode report generation: Gemma 3 1B via llama-server, with a number
validator (every number in the generated text must trace back to a measured
value) and a fixed-template fallback - never show an invented number.

The llama-server setup and this check-and-retry idea are reused from the
author's own prior (Daybreak) project; see README Credits.
"""

import json
import logging
import re
import socket
import struct
import urllib.request

logger = logging.getLogger("project-pulse.report")


def _llama_host() -> str:
    """llama-server runs on the board's host, not inside this app's container,
    so 127.0.0.1 here means the container itself. Route through the
    container's default gateway (the host), falling back to localhost for
    local/non-container test runs. No `ip`/`iproute2` binary in this
    container, so read the kernel routing table directly."""
    try:
        with open("/proc/net/route") as f:
            next(f)
            for line in f:
                fields = line.split()
                if fields[1] == "00000000":  # destination 0.0.0.0 = default route
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except Exception:
        pass
    return "127.0.0.1"


LLAMA_SERVER_URL = f"http://{_llama_host()}:8080/completion"
NUMBER_TOLERANCE_REL = 0.05  # 5% relative tolerance for rounding in the report text
NUMBER_TOLERANCE_ABS = 0.05  # absolute floor so near-zero measured values aren't impossibly strict


def _numbers_in(text):
    # (?<!\d) keeps a "-" in a range like "10-800" from being read as a minus sign.
    # (?!\w) excludes digits glued to a following letter, e.g. the "1" in "1x amplitude".
    return [float(m) for m in re.findall(r"(?<!\d)-?\d+\.?\d*(?!\w)", text)]


def _matches_a_measurement(n, measured_values):
    return any(
        abs(n - m) <= max(abs(m) * NUMBER_TOLERANCE_REL, NUMBER_TOLERANCE_ABS)
        for m in measured_values
    )


def validate_numbers(text: str, measured: dict) -> bool:
    """Every number in text must be within tolerance of some measured value."""
    measured_values = list(measured.values())
    return all(_matches_a_measurement(n, measured_values) for n in _numbers_in(text))


def _measured_values(features, result) -> dict:
    return {
        "iso_standard": 10816,  # the prompt names "ISO 10816"; let the model echo it
        "band_edge_lo_hz": 10,  # the prompt names the "10-800 Hz" and "400-800 Hz" bands; let the model echo them
        "band_edge_mid_hz": 400,
        "band_edge_hi_hz": 800,
        "rotation_hz": round(features.rotation_hz, 1),
        "velocity_rms_mm_s": round(features.velocity_rms_mm_s, 2),
        "amp_1x_g": round(features.amp_1x_g, 3),
        "amp_2x_g": round(features.amp_2x_g, 3),
        "amp_3x_g": round(features.amp_3x_g, 3),
        "band_high_ratio": round(features.band_high_ratio, 2),
        "kurtosis": round(features.kurtosis, 2),
        "crest": round(features.crest, 2),
    }


def build_prompt(features, result: dict) -> str:
    return (
        "You are writing a short plain-language report for a technician who just "
        "tested a motor with a vibration probe. Use ONLY the measurements given below - "
        "never invent a number, a band, or a measurement that isn't listed below. "
        "Write 3-4 plain sentences, no bullet list, no restating the raw numbers.\n\n"
        f"ISO 10816 zone: {result['zone']}\n"
        f"Faults detected: {', '.join(result['faults']) or 'none'}\n"
        f"Rotation speed: {features.rotation_hz:.1f} Hz\n"
        f"Velocity RMS: {features.velocity_rms_mm_s:.2f} mm/s\n"
        f"1x amplitude: {features.amp_1x_g:.3f} g\n"
        f"2x amplitude: {features.amp_2x_g:.3f} g\n"
        f"3x amplitude: {features.amp_3x_g:.3f} g\n"
        f"400-800 Hz energy share of the 10-800 Hz vibration band: {features.band_high_ratio:.2f}\n"
        f"Kurtosis: {features.kurtosis:.2f}\n"
        f"Crest factor: {features.crest:.2f}\n"
    )


def _call_llama(prompt: str, n_predict: int = 130) -> str:
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "temperature": 0.2}).encode()
    req = urllib.request.Request(
        LLAMA_SERVER_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["content"].strip()


def _fallback_report(features, result: dict) -> str:
    fault_text = ", ".join(result["faults"]) if result["faults"] else "no fault signature matched"
    return (
        f"ISO 10816 zone {result['zone']}. {fault_text}. "
        f"Rotation {features.rotation_hz:.1f} Hz, velocity RMS {features.velocity_rms_mm_s:.2f} mm/s, "
        f"1x/2x/3x {features.amp_1x_g:.3f}/{features.amp_2x_g:.3f}/{features.amp_3x_g:.3f} g, "
        f"kurtosis {features.kurtosis:.2f}, crest {features.crest:.2f}."
    )


def _generate(prompt: str, measured: dict, fallback: str, call_llama) -> str:
    """One try + one retry against llama-server; a response with any number
    that doesn't trace back to a measured value is rejected. Falls back to a
    fixed template on repeated validation failure or if llama-server is
    unreachable."""
    for _ in range(2):
        try:
            text = call_llama(prompt)
        except Exception as exc:
            logger.warning("llama-server call failed: %s", exc)
            break
        if validate_numbers(text, measured):
            return text
        logger.warning("llm text rejected (invented number): %r", text)
    return fallback


def generate_report(features, result: dict, call_llama=_call_llama) -> str:
    measured = _measured_values(features, result)
    prompt = build_prompt(features, result)
    return _generate(prompt, measured, _fallback_report(features, result), call_llama)


def build_guard_note_prompt(features, result: dict, heat: float) -> str:
    return (
        "You are writing a short daily note for the owner of a motor under "
        "continuous guard monitoring. Use ONLY the measurements given below - "
        "never invent a number, a band, or a measurement that isn't listed below. "
        "Write 2-3 plain sentences: how the motor is doing right now and whether "
        "the owner needs to act.\n\n"
        f"ISO 10816 zone: {result['zone']}\n"
        f"Faults detected: {', '.join(result['faults']) or 'none'}\n"
        f"Heat budget (0 = cool, 1 = stop threshold): {heat:.2f}\n"
        f"Rotation speed: {features.rotation_hz:.1f} Hz\n"
        f"Velocity RMS: {features.velocity_rms_mm_s:.2f} mm/s\n"
    )


def _fallback_guard_note(features, result: dict, heat: float) -> str:
    fault_text = ", ".join(result["faults"]) if result["faults"] else "no fault signature matched"
    return (
        f"Guard note: ISO 10816 zone {result['zone']}, heat budget {heat:.2f}. {fault_text}. "
        f"Rotation {features.rotation_hz:.1f} Hz, velocity RMS {features.velocity_rms_mm_s:.2f} mm/s."
    )


def generate_guard_note(features, result: dict, heat: float, call_llama=_call_llama) -> str:
    measured = _measured_values(features, result)
    measured["heat_budget"] = round(heat, 2)
    prompt = build_guard_note_prompt(features, result, heat)
    return _generate(prompt, measured, _fallback_guard_note(features, result, heat), call_llama)
