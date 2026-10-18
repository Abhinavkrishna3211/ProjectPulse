import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

from features import KX134Features
from report import generate_guard_note, generate_report, validate_numbers

FEATURES = KX134Features(49.0, 1.2, 0.03, 0.01, 0.005, 0.03, 2.1, 2.5)
RESULT = {"zone": "B", "faults": []}


def test_validate_numbers_accepts_rounded_measured_values():
    measured = {"rotation_hz": 49.0, "velocity_rms_mm_s": 1.2}
    assert validate_numbers("Rotation is about 49 Hz at 1.2 mm/s.", measured)


def test_validate_numbers_accepts_a_hz_range_without_misreading_the_dash_as_minus():
    measured = {"band_edge_lo_hz": 10, "band_edge_hi_hz": 800}
    assert validate_numbers("The 10-800 Hz vibration band is healthy.", measured)


def test_validate_numbers_rejects_invented_number():
    measured = {"rotation_hz": 49.0, "velocity_rms_mm_s": 1.2}
    assert not validate_numbers("Rotation is about 73 Hz.", measured)


def test_generate_report_accepts_good_llm_output():
    def good_llm(prompt):
        return "Zone B, rotation 49.0 Hz, velocity RMS 1.2 mm/s, no faults detected."

    text = generate_report(FEATURES, RESULT, call_llama=good_llm)
    assert "49.0" in text


def test_generate_report_falls_back_on_invented_numbers():
    def bad_llm(prompt):
        return "The motor is spinning at 999 Hz, which is dangerously fast."

    text = generate_report(FEATURES, RESULT, call_llama=bad_llm)
    assert "999" not in text
    assert "zone b" in text.lower()


def test_generate_report_falls_back_when_llama_unreachable():
    def broken_llm(prompt):
        raise ConnectionError("no server")

    text = generate_report(FEATURES, RESULT, call_llama=broken_llm)
    assert "zone b" in text.lower()


def test_generate_guard_note_accepts_good_llm_output():
    def good_llm(prompt):
        return "Zone B at heat budget 0.10, running at 49.0 Hz. No action needed."

    text = generate_guard_note(FEATURES, RESULT, 0.1, call_llama=good_llm)
    assert "49.0" in text


def test_generate_guard_note_falls_back_on_invented_numbers():
    def bad_llm(prompt):
        return "Heat budget is 0.99, about to overheat!"

    text = generate_guard_note(FEATURES, RESULT, 0.1, call_llama=bad_llm)
    assert "0.99" not in text
    assert "zone b" in text.lower()
