"""Check-mode report generation: Gemma 3 1B via llama-server, with a number
validator (every number in the generated text must trace back to a measured
value) and a fixed-template fallback - never show an invented number.

The llama-server setup and this check-and-retry idea are reused from the
author's own prior (Daybreak) project; see README Credits.
"""

import json
import re
import urllib.request

LLAMA_SERVER_URL = "http://127.0.0.1:8080/completion"
NUMBER_TOLERANCE_REL = 0.05  # 5% relative tolerance for rounding in the report text
NUMBER_TOLERANCE_ABS = 0.05  # absolute floor so near-zero measured values aren't impossibly strict


def _numbers_in(text):
    return [float(m) for m in re.findall(r"-?\d+\.?\d*", text)]


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
        "tested a motor with a vibration probe. Use ONLY the numbers given below - "
        "never invent or round a number that isn't listed. Be concise (3-4 sentences).\n\n"
        f"ISO 10816 zone: {result['zone']}\n"
        f"Faults detected: {', '.join(result['faults']) or 'none'}\n"
        f"Rotation speed: {features.rotation_hz:.1f} Hz\n"
        f"Velocity RMS: {features.velocity_rms_mm_s:.2f} mm/s\n"
        f"1x amplitude: {features.amp_1x_g:.3f} g\n"
        f"2x amplitude: {features.amp_2x_g:.3f} g\n"
        f"3x amplitude: {features.amp_3x_g:.3f} g\n"
        f"High-band (400-800 Hz) energy share: {features.band_high_ratio:.2f}\n"
        f"Kurtosis: {features.kurtosis:.2f}\n"
        f"Crest factor: {features.crest:.2f}\n"
    )


def _call_llama(prompt: str, n_predict: int = 160) -> str:
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "temperature": 0.2}).encode()
    req = urllib.request.Request(
        LLAMA_SERVER_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["content"].strip()


def _fallback_report(features, result: dict) -> str:
    fault_text = ", ".join(result["faults"]) if result["faults"] else "no fault signature matched"
    return (
        f"ISO 10816 zone {result['zone']}. {fault_text}. "
        f"Rotation {features.rotation_hz:.1f} Hz, velocity RMS {features.velocity_rms_mm_s:.2f} mm/s, "
        f"1x/2x/3x {features.amp_1x_g:.3f}/{features.amp_2x_g:.3f}/{features.amp_3x_g:.3f} g, "
        f"kurtosis {features.kurtosis:.2f}, crest {features.crest:.2f}."
    )


def generate_report(features, result: dict, call_llama=_call_llama) -> str:
    """One try + one retry against llama-server; a response with any number
    that doesn't trace back to a measured value is rejected. Falls back to a
    fixed template (built straight from the measured values) on repeated
    validation failure or if llama-server is unreachable."""
    measured = _measured_values(features, result)
    prompt = build_prompt(features, result)
    for _ in range(2):
        try:
            text = call_llama(prompt)
        except Exception:
            break
        if validate_numbers(text, measured):
            return text
    return _fallback_report(features, result)
