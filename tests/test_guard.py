import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "probe" / "python"))

from features import KX134Features
from guard import CALIBRATING, GUARDING, IDLE, LEARNING, STOPPED, GuardController

OFF = KX134Features(0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 2.5, 3.0)
RUNNING = KX134Features(50.0, 2.5, 0.02, 0.005, 0.002, 0.05, 2.5, 3.0)
WILD = KX134Features(50.0, 2.5, 0.5, 0.5, 0.5, 0.9, 20.0, 15.0)
HEALTHY = {"zone": "A", "faults": []}


def _clock():
    t = [0.0]

    def tick(step=1.0):
        t[0] += step
        return t[0]

    def now():
        return t[0]

    return now, tick


def test_guard_cycles_idle_calibrating_learning_guarding():
    now, tick = _clock()
    guard = GuardController(clock=now)
    assert guard.state == IDLE

    guard.button_press()
    assert guard.state == CALIBRATING

    for _ in range(30):
        tick()
        guard.feed(OFF, HEALTHY)
    assert guard.state == LEARNING

    for _ in range(180):
        tick()
        guard.feed(RUNNING, HEALTHY)
    assert guard.state == GUARDING
    assert guard.model.is_learned


def test_guard_extends_learn_window_instead_of_crashing_when_motor_rarely_clears_floor():
    now, tick = _clock()
    guard = GuardController(clock=now)
    guard.button_press()
    for _ in range(30):
        tick()
        guard.feed(OFF, HEALTHY)
    assert guard.state == LEARNING

    # Quiet motor: only 1 row ever clears the running gate per window.
    for _ in range(180):
        tick()
        guard.feed(OFF, HEALTHY)
    guard.feed(RUNNING, HEALTHY)
    for _ in range(180):
        tick()
        guard.feed(OFF, HEALTHY)
    assert guard.state == LEARNING  # still collecting, not stuck erroring
    assert not guard.model.is_learned

    # Enough real running rows finally show up within one window.
    for _ in range(180):
        tick()
        guard.feed(RUNNING, HEALTHY)
    assert guard.state == GUARDING
    assert guard.model.is_learned


def test_guard_flags_anomaly_and_latches_stop_then_acks():
    now, tick = _clock()
    guard = GuardController(clock=now)
    guard.button_press()
    for _ in range(30):
        tick()
        guard.feed(OFF, HEALTHY)
    for _ in range(180):
        tick()
        guard.feed(RUNNING, HEALTHY)
    assert guard.state == GUARDING

    for _ in range(5):
        state = guard.feed(WILD, {"zone": "D", "faults": ["overload"]})
    assert state == "amber"

    # Heat budget fills from continuous "overload" faults while running.
    for _ in range(300):
        state = guard.feed(RUNNING, {"zone": "B", "faults": ["overload"]})
    assert state == "red"
    assert guard.state == STOPPED

    guard.button_hold()
    assert guard.state == GUARDING
    assert guard.heat.h == 0.0


def test_guard_debounces_anomaly_before_flagging_amber():
    now, tick = _clock()
    guard = GuardController(clock=now)
    guard.button_press()
    for _ in range(30):
        tick()
        guard.feed(OFF, HEALTHY)
    for _ in range(180):
        tick()
        guard.feed(RUNNING, HEALTHY)
    assert guard.state == GUARDING

    guard.model.is_anomaly = lambda row: True  # force every row anomalous
    no_fault = {"zone": "A", "faults": []}
    results = [guard.feed(RUNNING, no_fault) for _ in range(5)]
    assert results == ["green", "green", "green", "green", "amber"]


def test_guard_debounces_faults_before_flagging_amber():
    now, tick = _clock()
    guard = GuardController(clock=now)
    guard.button_press()
    for _ in range(30):
        tick()
        guard.feed(OFF, HEALTHY)
    for _ in range(180):
        tick()
        guard.feed(RUNNING, HEALTHY)
    assert guard.state == GUARDING

    flagged = {"zone": "B", "faults": ["imbalance"]}
    results = [guard.feed(RUNNING, flagged) for _ in range(5)]
    assert results == ["green", "green", "green", "green", "amber"]


if __name__ == "__main__":
    test_guard_cycles_idle_calibrating_learning_guarding()
    test_guard_extends_learn_window_instead_of_crashing_when_motor_rarely_clears_floor()
    test_guard_flags_anomaly_and_latches_stop_then_acks()
    print("ok")
