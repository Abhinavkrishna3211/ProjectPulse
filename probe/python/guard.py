"""Guard mode state machine, per planning/spec.md: off-floor calibration ->
learn normal -> guarding, driven by the probe's learn/ack button.

Simplification: the spec calls for "3 x 3 min healthy runs"; this build
learns from one continuous LEARN_S window of running rows instead of three
separate ones. Revisit if the model needs more varied training data.

Trip verify (confirming vibration falls to the off floor within ~5 s of the
plug opening) needs the stop plug, which doesn't exist yet (build step 5) -
only the heat-budget latch is wired here.
"""

import time

from features import KX134Features
from heat import HeatBudget
from model import GuardModel, is_running, off_floor

CALIBRATION_S = 30
LEARN_S = 180
T_MAX_S = 300
T_COOL_S = 120
ANOMALY_DEBOUNCE = 3  # consecutive anomalous rows needed before flagging amber

IDLE, CALIBRATING, LEARNING, GUARDING, STOPPED = (
    "idle",
    "calibrating",
    "learning",
    "guarding",
    "stopped",
)


class GuardController:
    """feed() is called once per live KX134Features row (1 Hz) and returns
    the LED state this row implies; button_press()/button_hold() come from
    the probe's physical button (see probe/sketch/button.cpp)."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.state = IDLE
        self.floor = None
        self.model = GuardModel()
        self.heat = HeatBudget(T_MAX_S, T_COOL_S)
        self._cal_samples: list[float] = []
        self._cal_started = None
        self._learn_rows: list[KX134Features] = []
        self._learn_started = None
        self._anomaly_streak = 0

    def button_press(self) -> None:
        if self.state == IDLE:
            self.state = CALIBRATING
            self._cal_samples = []
            self._cal_started = self._clock()

    def button_hold(self) -> None:
        if self.state == STOPPED:
            self.state = GUARDING
            self.heat.h = 0.0

    def feed(self, row: KX134Features, result: dict) -> str:
        if self.state == CALIBRATING:
            return self._calibrate(row)
        if self.state == LEARNING:
            return self._learn(row)
        if self.state == GUARDING:
            return self._guard(row, result)
        if self.state == STOPPED:
            self.heat.update(1.0, running=False, faults=[])
            return "red"
        return "off"

    def _calibrate(self, row: KX134Features) -> str:
        self._cal_samples.append(row.velocity_rms_mm_s)
        if self._clock() - self._cal_started >= CALIBRATION_S:
            self.floor = off_floor(self._cal_samples)
            self.state = LEARNING
            self._learn_rows = []
            self._learn_started = self._clock()
        return "blue"

    def _learn(self, row: KX134Features) -> str:
        if is_running(row.velocity_rms_mm_s, self.floor):
            self._learn_rows.append(row)
        if self._clock() - self._learn_started >= LEARN_S:
            self.model.learn(self._learn_rows)
            self.state = GUARDING
        return "blue"

    def _guard(self, row: KX134Features, result: dict) -> str:
        running = is_running(row.velocity_rms_mm_s, self.floor)
        self.heat.update(1.0, running, result["faults"])
        heat_level = self.heat.state()
        if heat_level == "stop":
            self.state = STOPPED
            return "red"
        anomaly = running and self.model.is_anomaly(row)
        self._anomaly_streak = self._anomaly_streak + 1 if anomaly else 0
        if self._anomaly_streak >= ANOMALY_DEBOUNCE or heat_level == "amber" or result["faults"]:
            return "amber"
        return "green"
