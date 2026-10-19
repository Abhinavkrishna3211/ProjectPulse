"""Guard mode: off-floor gate (is the motor even running?) and a per-motor
"normal" model (IsolationForest), per planning/spec.md.

Off-floor gate: calibrate once on a 30 s off/stationary window, then compare
each live velocity RMS reading against floor * k. This has to come before
the learned model - there's no point scoring "normal" on a motor that's off.

Learn normal: trained on a handful of healthy running windows (the spec's
3 x 3 min), one feature vector per KX134Features row. No history is kept
beyond the fitted forest - each later row is scored independently.
"""

from sklearn.ensemble import IsolationForest

from features import KX134Features

OFF_FLOOR_K = 1.5  # running if velocity RMS >= floor * k
# ponytail: tuned against real board readings on 2026-10-19 (floor ~2.2-2.4 mm/s,
# an apparent sensor/integration noise floor present regardless of motor or
# surface); 3.0x left the gate unclearable even for a motor with real faults.


def off_floor(calibration_rms: list[float]) -> float:
    """Average velocity RMS over an off/stationary calibration window."""
    if not calibration_rms:
        raise ValueError("off_floor needs at least one calibration sample")
    return sum(calibration_rms) / len(calibration_rms)


def is_running(velocity_rms_mm_s: float, floor: float, k: float = OFF_FLOOR_K) -> bool:
    return velocity_rms_mm_s >= floor * k


def _to_vector(f: KX134Features) -> list[float]:
    return list(f)


class GuardModel:
    """Wraps an IsolationForest fitted on this motor's own healthy feature
    rows. Call learn() once per motor before is_anomaly()."""

    def __init__(self):
        self._forest = None

    def learn(self, rows: list[KX134Features]) -> None:
        if len(rows) < 2:
            raise ValueError("learn() needs at least 2 healthy feature rows")
        # contamination='auto' fixes a score threshold that, on a small
        # training set like ours (a few minutes of healthy rows), flags most
        # of the training data itself as outliers. An explicit contamination
        # sets the threshold from this data's own score distribution instead.
        self._forest = IsolationForest(n_estimators=100, random_state=0, contamination=0.1)
        self._forest.fit([_to_vector(f) for f in rows])

    @property
    def is_learned(self) -> bool:
        return self._forest is not None

    def is_anomaly(self, f: KX134Features) -> bool:
        if self._forest is None:
            raise RuntimeError("call learn() before is_anomaly()")
        return bool(self._forest.predict([_to_vector(f)])[0] == -1)
