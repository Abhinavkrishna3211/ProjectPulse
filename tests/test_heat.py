import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe" / "python"))

from heat import HeatBudget


def test_heat_fills_while_overloaded_and_running():
    budget = HeatBudget(t_max_s=10.0, t_cool_s=10.0)
    budget.update(5.0, running=True, faults=["overload"])
    assert budget.h == 0.5
    assert budget.state() == "ok"


def test_heat_reaches_stop_and_clamps_at_one():
    budget = HeatBudget(t_max_s=10.0, t_cool_s=10.0)
    budget.update(20.0, running=True, faults=["overload"])
    assert budget.h == 1.0
    assert budget.state() == "stop"


def test_heat_does_not_fill_when_running_without_overload():
    budget = HeatBudget(t_max_s=10.0, t_cool_s=10.0)
    budget.update(5.0, running=True, faults=[])
    assert budget.h == 0.0


def test_heat_drains_while_off_and_clamps_at_zero():
    budget = HeatBudget(t_max_s=10.0, t_cool_s=10.0)
    budget.h = 0.3
    budget.update(20.0, running=False, faults=[])
    assert budget.h == 0.0


def test_heat_amber_threshold():
    budget = HeatBudget(t_max_s=10.0, t_cool_s=10.0)
    budget.h = 0.8
    assert budget.state() == "amber"
