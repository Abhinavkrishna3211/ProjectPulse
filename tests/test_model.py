import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

import pytest

from features import KX134Features
from model import GuardModel, is_running, off_floor

QUIET = KX134Features(25.0, 0.5, 0.002, 0.0004, 0.0002, 0.05, 2.5, 3.0)
RUNNING = KX134Features(50.0, 2.5, 0.02, 0.005, 0.002, 0.05, 2.5, 3.0)
WILD = KX134Features(50.0, 2.5, 0.5, 0.5, 0.5, 0.9, 20.0, 15.0)

# A real motor's healthy readings jitter window to window; identical rows
# give IsolationForest zero variance to learn from, which is degenerate.
HEALTHY_ROWS = [
    KX134Features(
        50.0 + i % 3 * 0.1,
        2.5 + i % 5 * 0.02,
        0.02 + i % 4 * 0.001,
        0.005 + i % 3 * 0.0005,
        0.002 + i % 2 * 0.0003,
        0.05 + i % 3 * 0.005,
        2.5 + i % 4 * 0.1,
        3.0 + i % 3 * 0.1,
    )
    for i in range(20)
]


def test_off_floor_averages_calibration_samples():
    assert off_floor([0.4, 0.5, 0.6]) == pytest.approx(0.5)


def test_off_floor_rejects_empty_calibration():
    with pytest.raises(ValueError):
        off_floor([])


def test_is_running_above_floor_times_k():
    floor = 0.5
    assert is_running(2.5, floor)  # 2.5 >= 0.5 * 1.5
    assert not is_running(0.5, floor)  # below the 0.75 running threshold


def test_guard_model_requires_learning_first():
    model = GuardModel()
    with pytest.raises(RuntimeError):
        model.is_anomaly(RUNNING)


def test_guard_model_flags_a_wildly_different_row_as_anomalous():
    model = GuardModel()
    model.learn(HEALTHY_ROWS)
    assert model.is_anomaly(WILD)
    assert not model.is_anomaly(RUNNING)
