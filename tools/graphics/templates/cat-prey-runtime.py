"""Blender-side adapter for deterministic Cat TV prey motion plans."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def args_after_separator() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True, choices=["apply", "render_animation"])
    parser.add_argument("--asset", required=True)
    parser.add_argument("--motion", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--target-height", type=float, default=0.34)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--start-frame", type=int, default=1)
    parser.add_argument("--end-frame", type=int)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def select_eevee_engine(scene) -> str:
    """Select Eevee across Blender 4.5 and Blender 5.x."""
    errors = []
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            return candidate
        except (TypeError, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("No supported Eevee engine found; " + "; ".join(errors))


def import_asset(path: Path):
    before = set(bpy.context.scene.objects)
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise ValueError(f"Unsupported prey asset format: {path}")

    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    if not imported:
        raise RuntimeError("Prey asset import created no Blender objects")

    path_root = bpy.data.objects.new("CAT_TV_PREY_ROOT", None)
    body_root = bpy.data.objects.new("CAT_TV_PREY_BODY", None)
    bpy.context.collection.objects.link(path_root)
    bpy.context.collection.objects.link(body_root)
    body_root.parent = path_root

    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            matrix_world = obj.matrix_world.copy()
            obj.parent = body_root
            obj.matrix_world = matrix_world
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.use_smooth = True

    points = []
    for obj in imported:
        if obj.type == "MESH":
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        source_height, source_floor = 1.0, 0.0
    else:
        z_values = [point.z for point in points]
        source_height = max(0.001, max(z_values) - min(z_values))
        source_floor = min(z_values)
    return path_root, body_root, imported, source_height, source_floor


def ground_height(x: float, y: float, imported: list) -> float:
    states = [(obj, obj.hide_viewport) for obj in imported]
    for obj, _state in states:
        obj.hide_viewport = True
    bpy.context.view_layer.update()
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        hit, location, _normal, _index, _object, _matrix = bpy.context.scene.ray_cast(
            depsgraph, Vector((x, y, 1000.0)), Vector((0.0, 0.0, -1.0)), distance=2000.0
        )
        return float(location.z) if hit else 0.0
    finally:
        for obj, state in states:
            obj.hide_viewport = state
        bpy.context.view_layer.update()


def set_visibility(imported: list, visible: bool, frame: int) -> None:
    for obj in imported:
        obj.hide_render = not visible
        obj.hide_viewport = not visible
        obj.keyframe_insert("hide_render", frame=frame)
        obj.keyframe_insert("hide_viewport", frame=frame)


def iter_action_fcurves(obj):
    """Return F-Curves for Blender 4.x legacy Actions and Blender 5.x slotted Actions."""
    animation_data = obj.animation_data
    if not animation_data or not animation_data.action:
        return []

    action = animation_data.action
    if hasattr(action, "fcurves"):
        return action.fcurves

    slot = getattr(animation_data, "action_slot", None)
    if slot is None:
        return []

    for layer in action.layers:
        for strip in layer.strips:
            if not hasattr(strip, "channelbag"):
                continue
            channelbag = strip.channelbag(slot)
            if channelbag is not None:
                return channelbag.fcurves
    return []


def set_curve_interpolation(obj, frame: int, interpolation: str) -> None:
    requested = interpolation if interpolation in {"CONSTANT", "LINEAR", "BEZIER"} else "LINEAR"
    for curve in iter_action_fcurves(obj):
        for point in curve.keyframe_points:
            if abs(point.co.x - frame) < 0.01:
                point.interpolation = requested


def micro_profile(behavior: str) -> tuple[float, float, float, float, float]:
    """Return cadence, bob amplitude/frequency, pitch and roll amplitudes."""
    profiles = {
        "sprint": (0.10, 0.018, 5.2, 3.8, 2.1),
        "edge_exit": (0.10, 0.016, 4.8, 3.2, 1.8),
        "reentry": (0.11, 0.015, 4.5, 3.0, 1.7),
        "explore": (0.16, 0.010, 3.1, 2.0, 1.2),
        "peek": (0.18, 0.006, 2.2, 3.0, 1.5),
        "pause": (0.28, 0.0025, 1.2, 0.7, 0.4),
        "hide": (0.32, 0.0015, 0.9, 0.4, 0.3),
    }
    return profiles.get(behavior, profiles["explore"])


def add_body_micro_motion(body_root, segments: list[dict], fps: int) -> int:
    """Add deterministic body bob/tilt without disturbing the world-space prey path."""
    inserted = 0
    for segment in segments:
        behavior = str(segment.get("behavior", "explore"))
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if end <= start:
            continue
        cadence, bob_amp, frequency, pitch_deg, roll_deg = micro_profile(behavior)
        duration = end - start
        steps = max(1, math.ceil(duration / cadence))
        for index in range(steps + 1):
            at = min(end, start + duration * index / steps)
            phase = math.tau * frequency * at
            # Always bob upward from the grounded baseline: no terrain penetration.
            bob = bob_amp * abs(math.sin(phase))
            pitch = math.radians(pitch_deg) * math.sin(phase)
            roll = math.radians(roll_deg) * math.sin(phase * 0.5 + 0.8)
            frame = 1 + round(at * fps)
            body_root.location = (0.0, 0.0, bob)
            body_root.rotation_euler = (pitch, roll, 0.0)
            body_root.keyframe_insert("location", frame=frame)
            body_root.keyframe_insert("rotation_euler", frame=frame)
            set_curve_interpolation(body_root, frame, "BEZIER")
            inserted += 1
    return inserted


def apply_motion(plan: dict, asset: Path, target_height: float, fps: int) -> dict:
    path_root, body_root, imported, source_height, source_floor = import_asset(asset)
    scale = target_height / source_height
    body_root.scale = (scale, scale, scale)

    keyframes = plan.get("keyframes") or []
    if not keyframes:
        raise ValueError("Motion plan contains no keyframes")

    for key in keyframes:
        at = float(key["time"])
        frame = 1 + round(at * fps)
        x, y = [float(value) for value in key.get("position", [0, 0])[:2]]
        z_offset = float(key.get("z_offset", 0.03))
        z = ground_height(x, y, imported) - source_floor * scale + z_offset
        path_root.location = (x, y, z)
        path_root.rotation_euler[2] = math.radians(float(key.get("heading_degrees", 0.0)))
        path_root.keyframe_insert("location", frame=frame)
        path_root.keyframe_insert("rotation_euler", frame=frame)
        set_curve_interpolation(path_root, frame, str(key.get("interpolation", "LINEAR")))
        set_visibility(imported, bool(key.get("visible", True)), frame)

    micro_keyframes = add_body_micro_motion(body_root, list(plan.get("segments") or []), fps)

    return {
        "prey_objects": len(imported),
        "keyframes": len(keyframes),
        "micro_keyframes": micro_keyframes,
        "source_height": source_height,
        "target_height": target_height,
        "seed": plan.get("seed"),
    }


def main() -> None:
    args = args_after_separator()
    motion_path = Path(args.motion).expanduser().resolve()
    asset_path = Path(args.asset).expanduser().resolve()
    plan = json.loads(motion_path.read_text(encoding="utf-8"))
    report = apply_motion(plan, asset_path, args.target_height, args.fps)

    scene = bpy.context.scene
    scene.render.fps = args.fps
    scene.frame_start = args.start_frame
    scene.frame_end = args.end_frame or max(1, round(float(plan.get("duration_seconds", 60)) * args.fps))
    engine = select_eevee_engine(scene)
    report["engine"] = engine
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    blend_path = Path(args.blend).expanduser().resolve()
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    report_path = blend_path.with_suffix(".cat-tv-report.json")
    report_path.write_text(json.dumps({"version": "1.1", **report}, indent=2), encoding="utf-8")

    if args.operation == "render_animation":
        if not args.output:
            raise ValueError("--output is required for render_animation")
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(output)
        bpy.ops.render.render(animation=True)

    print("OPENMONTAGE_CAT_TV_REPORT=" + json.dumps(report, sort_keys=True))


main()
