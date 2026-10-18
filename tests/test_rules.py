import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

from features import KX134Features
from rules import evaluate


def test_quiet_baseline_is_zone_a_no_faults():
    quiet = KX134Features(25.0, 0.5, 0.002, 0.0004, 0.0002, 0.05, 2.5, 3.0)
    r = evaluate(quiet)
    assert r["zone"] == "A"
    assert r["faults"] == []


def test_dominant_1x_flags_imbalance():
    imbalance = KX134Features(25.0, 2.0, 0.5, 0.02, 0.01, 0.05, 2.5, 3.0)
    assert "imbalance" in evaluate(imbalance)["faults"]


def test_strong_harmonics_flag_looseness():
    loose = KX134Features(25.0, 1.0, 0.1, 0.08, 0.05, 0.05, 2.5, 3.0)
    assert "looseness_or_misalignment" in evaluate(loose)["faults"]


def test_high_band_plus_kurtosis_flags_bearing():
    bearing = KX134Features(25.0, 1.0, 0.1, 0.01, 0.01, 0.5, 6.0, 5.0)
    assert "bearing_or_impact" in evaluate(bearing)["faults"]


def test_slow_rotation_vs_rated_flags_overload():
    overload = KX134Features(40.0, 0.5, 0.05, 0.01, 0.01, 0.05, 2.5, 3.0)
    assert "overload" in evaluate(overload, rated_hz=50.0)["faults"]
