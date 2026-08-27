"""Contracts for the deterministic Cat TV production tools."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from tools.graphics.cat_prey_motion import CatPreyMotion, generate_mouse_plan
from tools.tool_registry import ToolRegistry


EXPECTED_BEHAVIORS = {"explore", "pause", "sprint", "hide", "peek", "edge_exit", "reentry"}


def test_registry_discovers_cat_tv_tools():
    registry = ToolRegistry()
    registry.discover("tools")
    assert {tool.name for tool in registry.get_by_capability("prey_motion_generation")} >= {"cat_prey_motion"}
    assert {tool.name for tool in registry.get_by_capability("prey_animation_rendering")} >= {"cat_prey_blender"}
    assert {tool.name for tool in registry.get_by_capability("cat_tv_world_polish")} >= {"cat_tv_world_polish"}


def test_mouse_motion_is_seeded_and_repeatable():
    first = generate_mouse_plan(duration_seconds=60, fps=60, seed=184321)
    second = generate_mouse_plan(duration_seconds=60, fps=60, seed=184321)
    different = generate_mouse_plan(duration_seconds=60, fps=60, seed=184322)
    assert first == second
    assert first != different


def test_mouse_motion_has_core_hunt_behaviors_and_valid_timeline():
    plan = generate_mouse_plan(duration_seconds=60, fps=60, seed=184321)
    behaviors = {segment["behavior"] for segment in plan["segments"]}
    assert EXPECTED_BEHAVIORS <= behaviors
    times = [frame["time"] for frame in plan["keyframes"]]
    assert times == sorted(times)
    assert times[0] == 0.0
    assert times[-1] == 60.0
    xmin, xmax, ymin, ymax = plan["bounds"]
    for frame in plan["keyframes"]:
        x, y = frame["position"]
        assert xmin <= x <= xmax
        assert ymin <= y <= ymax
        assert frame["interpolation"] in {"CONSTANT", "LINEAR", "BEZIER"}


def test_motion_tool_can_write_renderer_neutral_plan(tmp_path):
    output = tmp_path / "mouse.motion.json"
    result = CatPreyMotion().execute({
        "duration_seconds": 30,
        "fps": 60,
        "seed": 99,
        "output_path": str(output),
    })
    assert result.success, result.error
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["seed"] == 99
    assert payload["prey_type"] == "mouse"
    assert payload == result.data["motion_plan"]


def test_cat_tv_tool_schemas_are_valid_draft_2020_12():
    for name in ("cat_prey_motion", "cat_prey_blender", "cat_tv_world_polish"):
        schema = json.loads(Path(f"schemas/tools/{name}.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
