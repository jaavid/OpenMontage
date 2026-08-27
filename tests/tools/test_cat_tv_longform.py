"""Fast unit tests for the Cat TV long-form production planner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "cat_tv_longform.py"
SPEC = importlib.util.spec_from_file_location("cat_tv_longform_script", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_duration_supports_seconds_minutes_and_hours():
    assert MODULE.parse_duration("90") == 90
    assert MODULE.parse_duration("5m") == 300
    assert MODULE.parse_duration("2h") == 7200


def test_two_hour_plan_is_24_five_minute_segments():
    segments = MODULE.segment_durations(7200, 300)
    assert len(segments) == 24
    assert all(segment == 300 for segment in segments)
    assert sum(segments) == 7200


def test_segment_planner_balances_small_remainders_without_invalid_chunks():
    segments = MODULE.segment_durations(605, 600)
    assert len(segments) == 2
    assert sum(segments) == pytest.approx(605)
    assert all(10 <= segment <= 600 for segment in segments)


def test_segment_planner_rejects_invalid_target_size():
    with pytest.raises(ValueError):
        MODULE.segment_durations(60, 5)
    with pytest.raises(ValueError):
        MODULE.segment_durations(1200, 601)
