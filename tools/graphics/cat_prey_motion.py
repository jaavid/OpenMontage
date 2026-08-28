"""Deterministic prey-motion plans for long-form Cat TV productions.

The tool deliberately generates motion data rather than video. Blender (or a
future renderer) consumes the resulting keyframes, which keeps motion cheap,
repeatable, editable, and suitable for long-form output.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


DEFAULT_BOUNDS = [-4.5, 4.5, -2.3, 2.3]
_REQUIRED_BEHAVIORS = (
    "explore",
    "pause",
    "sprint",
    "hide",
    "peek",
    "edge_exit",
    "reentry",
)


def _bounded_point(rng: random.Random, bounds: list[float], margin: float = 0.08) -> tuple[float, float]:
    """Return a seeded point inside the bounds with an optional edge margin."""
    xmin, xmax, ymin, ymax = bounds
    mx = (xmax - xmin) * margin
    my = (ymax - ymin) * margin
    return rng.uniform(xmin + mx, xmax - mx), rng.uniform(ymin + my, ymax - my)


def _edge_point(rng: random.Random, bounds: list[float]) -> tuple[float, float]:
    """Return a seeded point on one of the four motion bounds."""
    xmin, xmax, ymin, ymax = bounds
    edge = rng.choice(("left", "right", "bottom", "top"))
    if edge == "left":
        return xmin, rng.uniform(ymin, ymax)
    if edge == "right":
        return xmax, rng.uniform(ymin, ymax)
    if edge == "bottom":
        return rng.uniform(xmin, xmax), ymin
    return rng.uniform(xmin, xmax), ymax


def _heading_degrees(a: tuple[float, float], b: tuple[float, float], fallback: float) -> float:
    """Return the heading from point a to b, preserving fallback when stationary."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return fallback
    return math.degrees(math.atan2(dy, dx))


def generate_mouse_plan(
    *,
    duration_seconds: float,
    fps: int,
    seed: int,
    bounds: list[float] | None = None,
    z_offset: float = 0.03,
) -> dict[str, Any]:
    """Generate a deterministic mouse hunt plan with the core Cat TV behaviors."""
    duration = float(duration_seconds)
    if duration < 10 or duration > 600:
        raise ValueError("duration_seconds must be between 10 and 600")
    if fps < 1 or fps > 120:
        raise ValueError("fps must be between 1 and 120")

    safe_bounds = list(bounds or DEFAULT_BOUNDS)
    if len(safe_bounds) != 4:
        raise ValueError("bounds must be [xmin, xmax, ymin, ymax]")
    xmin, xmax, ymin, ymax = (float(v) for v in safe_bounds)
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("bounds must have positive width and height")
    safe_bounds = [xmin, xmax, ymin, ymax]

    rng = random.Random(int(seed))
    position = _bounded_point(rng, safe_bounds)
    heading = 0.0
    visible = True
    now = 0.0
    keyframes: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []

    def add_keyframe(
        at: float,
        pos: tuple[float, float],
        behavior: str,
        *,
        is_visible: bool,
        interpolation: str,
    ) -> None:
        nonlocal heading, position
        at = min(duration, max(0.0, float(at)))
        new_heading = _heading_degrees(position, pos, heading)
        heading = new_heading
        position = pos
        keyframes.append({
            "time": round(at, 4),
            "position": [round(pos[0], 5), round(pos[1], 5)],
            "z_offset": round(float(z_offset), 5),
            "heading_degrees": round(new_heading, 3),
            "visible": bool(is_visible),
            "behavior": behavior,
            "interpolation": interpolation,
        })

    add_keyframe(0.0, position, "explore", is_visible=True, interpolation="BEZIER")

    guaranteed = list(_REQUIRED_BEHAVIORS)
    random_pool = ["explore", "pause", "sprint", "explore", "sprint", "hide", "peek", "edge_exit", "reentry"]
    behavior_index = 0

    while now < duration - 0.05:
        behavior = guaranteed[behavior_index] if behavior_index < len(guaranteed) else rng.choice(random_pool)
        behavior_index += 1
        start = now

        if behavior == "explore":
            step = rng.uniform(3.2, 5.8)
            target = _bounded_point(rng, safe_bounds)
            end = min(duration, now + step)
            add_keyframe(end, target, behavior, is_visible=True, interpolation="BEZIER")
            visible = True

        elif behavior == "pause":
            step = rng.uniform(1.0, 2.2)
            end = min(duration, now + step)
            add_keyframe(end, position, behavior, is_visible=visible, interpolation="CONSTANT")

        elif behavior == "sprint":
            step = rng.uniform(0.75, 1.45)
            target = _bounded_point(rng, safe_bounds, margin=0.03)
            end = min(duration, now + step)
            add_keyframe(end, target, behavior, is_visible=True, interpolation="LINEAR")
            visible = True

        elif behavior == "hide":
            step = rng.uniform(1.3, 2.6)
            switch = min(duration, now + min(0.05, step / 3))
            add_keyframe(switch, position, behavior, is_visible=False, interpolation="CONSTANT")
            end = min(duration, now + step)
            if end > switch:
                add_keyframe(end, position, behavior, is_visible=False, interpolation="CONSTANT")
            visible = False

        elif behavior == "peek":
            step = rng.uniform(0.65, 1.15)
            switch = min(duration, now + min(0.05, step / 3))
            add_keyframe(switch, position, behavior, is_visible=True, interpolation="CONSTANT")
            target = _bounded_point(rng, safe_bounds, margin=0.12)
            target = (
                position[0] + (target[0] - position[0]) * 0.16,
                position[1] + (target[1] - position[1]) * 0.16,
            )
            end = min(duration, now + step)
            if end > switch:
                add_keyframe(end, target, behavior, is_visible=True, interpolation="BEZIER")
            visible = True

        elif behavior == "edge_exit":
            step = rng.uniform(0.75, 1.35)
            target = _edge_point(rng, safe_bounds)
            travel_end = min(duration, now + step * 0.9)
            add_keyframe(travel_end, target, behavior, is_visible=True, interpolation="LINEAR")
            end = min(duration, now + step)
            if end > travel_end:
                add_keyframe(end, target, behavior, is_visible=False, interpolation="CONSTANT")
            visible = False

        else:  # reentry
            step = rng.uniform(0.9, 1.55)
            edge = _edge_point(rng, safe_bounds)
            add_keyframe(now, edge, behavior, is_visible=False, interpolation="CONSTANT")
            reveal = min(duration, now + min(0.05, step / 3))
            add_keyframe(reveal, edge, behavior, is_visible=True, interpolation="CONSTANT")
            target = _bounded_point(rng, safe_bounds, margin=0.15)
            end = min(duration, now + step)
            if end > reveal:
                add_keyframe(end, target, behavior, is_visible=True, interpolation="LINEAR")
            visible = True

        now = end
        segments.append({
            "behavior": behavior,
            "start": round(start, 4),
            "end": round(end, 4),
        })

    if keyframes[-1]["time"] < duration:
        add_keyframe(duration, position, "pause", is_visible=visible, interpolation="CONSTANT")

    return {
        "schema_version": "1.0",
        "prey_type": "mouse",
        "profile": "mixed_hunt",
        "seed": int(seed),
        "duration_seconds": duration,
        "fps": int(fps),
        "coordinate_system": "world_xy",
        "bounds": safe_bounds,
        "segments": segments,
        "keyframes": keyframes,
    }


class CatPreyMotion(BaseTool):
    name = "cat_prey_motion"
    version = "0.1.1"
    tier = ToolTier.GENERATE
    capability = "prey_motion_generation"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL
    dependencies: list[str] = []
    capabilities = ["mouse_motion_plan", "seeded_motion", "cat_tv_stimulus_timeline"]
    supports = {"mouse": True, "offline": True, "editable_keyframes": True}
    best_for = [
        "Deterministic Cat TV prey movement",
        "Long-form motion generation without paid video APIs",
        "Reusable motion plans for Blender or other renderers",
    ]
    not_good_for = ["Photorealistic rendering", "Animal behavior simulation for scientific use"]
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["generate"], "default": "generate"},
            "prey_type": {"type": "string", "enum": ["mouse"], "default": "mouse"},
            "duration_seconds": {"type": "number", "minimum": 10, "maximum": 600, "default": 60},
            "fps": {"type": "integer", "minimum": 1, "maximum": 120, "default": 60},
            "seed": {"type": "integer", "default": 184321},
            "bounds": {
                "type": "array", "minItems": 4, "maxItems": 4,
                "items": {"type": "number"}, "default": DEFAULT_BOUNDS,
            },
            "z_offset": {"type": "number", "default": 0.03},
            "output_path": {"type": "string"},
        },
    }
    output_schema = {"type": "object"}
    artifact_schema = {"artifact": "motion_plan"}
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=10)
    idempotency_key_fields = ["prey_type", "duration_seconds", "fps", "seed", "bounds", "z_offset"]
    side_effects = ["optionally writes a motion-plan JSON file"]
    user_visible_verification = [
        "Preview 10-15 seconds before a long render",
        "Confirm exits, re-entries, hiding, pauses, and bursts feel unpredictable without flicker",
    ]
    quality_score = 0.9

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 0.05

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        if str(inputs.get("operation", "generate")) != "generate":
            return ToolResult(success=False, error="Only operation='generate' is supported")
        prey_type = str(inputs.get("prey_type", "mouse"))
        if prey_type != "mouse":
            return ToolResult(success=False, error=f"Unsupported prey_type: {prey_type}")
        try:
            plan = generate_mouse_plan(
                duration_seconds=float(inputs.get("duration_seconds", 60)),
                fps=int(inputs.get("fps", 60)),
                seed=int(inputs.get("seed", 184321)),
                bounds=list(inputs.get("bounds") or DEFAULT_BOUNDS),
                z_offset=float(inputs.get("z_offset", 0.03)),
            )
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))

        data: dict[str, Any] = {"motion_plan": plan}
        artifacts: list[str] = []
        if inputs.get("output_path"):
            output = Path(str(inputs["output_path"])).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
            artifacts.append(str(output))
            data["output"] = str(output)

        return ToolResult(
            success=True,
            data=data,
            artifacts=artifacts,
            duration_seconds=round(time.time() - started, 4),
            seed=plan["seed"],
            model="openmontage-cat-prey-motion-v1",
        )
