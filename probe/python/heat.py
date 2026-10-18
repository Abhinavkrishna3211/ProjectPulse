"""Guard mode heat budget: no temperature sensor, so this is a proxy that
fills while the motor runs overloaded and drains while it's off, per
planning/spec.md. Fault detection comes from rules.evaluate() - this module
just turns an "overload" fault into a slow-building stop decision so a
single noisy reading can't trip it.
"""

AMBER = 0.8
STOP = 1.0


class HeatBudget:
    def __init__(self, t_max_s: float, t_cool_s: float):
        """t_max_s: seconds continuously overloaded to fill from 0 to 1 (STOP).
        t_cool_s: seconds off/at rest to drain from 1 back to 0."""
        self.t_max_s = t_max_s
        self.t_cool_s = t_cool_s
        self.h = 0.0

    def update(self, dt_s: float, running: bool, faults: list[str]) -> float:
        if running and "overload" in faults:
            self.h += dt_s / self.t_max_s
        elif not running:
            self.h -= dt_s / self.t_cool_s
        self.h = max(0.0, min(1.0, self.h))
        return self.h

    def state(self) -> str:
        if self.h >= STOP:
            return "stop"
        if self.h >= AMBER:
            return "amber"
        return "ok"
