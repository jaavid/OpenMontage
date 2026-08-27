#!/usr/bin/env python3
"""Resumable long-form Cat TV production runner.

The runner keeps one polished environment stable across every segment, varies
only prey motion seeds, renders numbered PNGs with resume support, encodes each
approved segment, stitches with OpenMontage's ``video_stitch``, and produces
representative QA frames plus an ffprobe-backed final validation report.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.analysis.frame_sampler import FrameSampler
from tools.analysis.visual_qa import VisualQA
from tools.graphics.blender_world import BlenderWorld
from tools.graphics.cat_prey_blender import CatPreyBlender
from tools.graphics.cat_prey_motion import CatPreyMotion
from tools.graphics.cat_tv_world_polish import CatTVWorldPolish
from tools.video.video_stitch import VideoStitch


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*$", re.I)


def parse_duration(value: str) -> float:
    """Parse seconds or a compact ``30m``/``2h`` duration string."""
    match = _DURATION_RE.match(value)
    if not match:
        raise argparse.ArgumentTypeError("duration must look like 120, 30m, or 2h")
    amount = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    seconds = amount * multiplier
    if seconds < 10:
        raise argparse.ArgumentTypeError("Cat TV duration must be at least 10 seconds")
    return seconds


def segment_durations(total_seconds: float, target_seconds: float) -> list[float]:
    """Split a production into balanced valid 10..600 second render segments."""
    total = float(total_seconds)
    target = float(target_seconds)
    if total < 10:
        raise ValueError("total duration must be at least 10 seconds")
    if target < 10 or target > 600:
        raise ValueError("segment_seconds must be between 10 and 600")

    count = max(1, math.ceil(total / target))
    while count > 1 and total / count < 10:
        count -= 1
    duration = total / count
    if duration < 10 or duration > 600:
        raise ValueError(
            f"Could not split {total_seconds}s into valid Cat TV segments with target {target_seconds}s"
        )

    result = [duration for _ in range(count)]
    result[-1] += total - sum(result)
    return result


def env_expand(value: Any) -> Any:
    """Expand ${VARS} recursively in recipe values."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [env_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: env_expand(item) for key, item in value.items()}
    return value


def canonical_digest(payload: Any) -> str:
    """Return a stable digest for resume/config invalidation."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_ffmpeg_encode(prefix: Path, fps: int, output: Path, crf: int, preset: str) -> None:
    """Encode one complete numbered PNG sequence into a high-quality segment."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", str(prefix) + "%04d.png",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)


def mux_ambience(video: Path, ambience: Path, output: Path, volume: float) -> None:
    """Loop subtle natural ambience for the exact final-video duration."""
    command = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-stream_loop", "-1", "-i", str(ambience),
        "-filter_complex", f"[1:a]volume={volume:.4f}[amb]",
        "-map", "0:v:0", "-map", "[amb]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)


def write_json(path: Path, payload: Any) -> None:
    """Write stable, readable JSON artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any] | None:
    """Read an optional JSON artifact, returning None when unavailable or invalid."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def build_world(
    recipe: dict[str, Any],
    project: Path,
    force: bool,
    world_asset: Path | None,
) -> tuple[Path, str]:
    """Build and polish the one environment shared by all prey segments."""
    base = project / "base.blend"
    polished = project / "base-polished.blend"
    config_path = project / "world-config.json"
    effective_polish = copy.deepcopy(recipe.get("world_polish") or {})
    if world_asset is not None:
        effective_polish["surface_asset_path"] = str(world_asset.resolve())
    world_config = {
        "world": recipe["world"],
        "world_polish": effective_polish,
    }
    world_digest = canonical_digest(world_config)
    previous = read_json(config_path)
    if polished.is_file() and not force and previous and previous.get("digest") == world_digest:
        return polished, world_digest

    for path in (base, polished, polished.with_suffix(".world-polish.json")):
        if path.exists():
            path.unlink()

    world_inputs = copy.deepcopy(recipe["world"])
    world_inputs["blend_path"] = str(base)
    world_result = BlenderWorld().execute(world_inputs)
    if not world_result.success:
        raise RuntimeError(f"blender_world failed: {world_result.error}")
    if not base.is_file():
        raise RuntimeError(f"blender_world did not produce {base}")

    polish_inputs = effective_polish
    polish_inputs.update({
        "operation": "polish",
        "base_blend_path": str(base),
        "blend_path": str(polished),
    })
    polish_result = CatTVWorldPolish().execute(polish_inputs)
    if not polish_result.success:
        raise RuntimeError(f"cat_tv_world_polish failed: {polish_result.error}")
    write_json(config_path, {"digest": world_digest, **world_config})
    return polished, world_digest


def segment_signature(
    recipe: dict[str, Any],
    duration: float,
    seed: int,
    asset: Path,
    world_digest: str,
) -> dict[str, Any]:
    """Return the fields that must match before old rendered frames may be resumed."""
    return {
        "seed": seed,
        "duration_seconds": duration,
        "fps": int(recipe["motion"].get("fps", 60)),
        "world_digest": world_digest,
        "asset_path": str(asset.resolve()),
        "target_height": float(recipe["prey_render"].get("target_height", 0.34)),
        "heading_offset_degrees": float(recipe["prey_render"].get("heading_offset_degrees", 0.0)),
    }


def clear_stale_segment(segment_dir: Path) -> None:
    """Delete stale derived artifacts while keeping the segment directory address stable."""
    if segment_dir.exists():
        shutil.rmtree(segment_dir)
    segment_dir.mkdir(parents=True, exist_ok=True)


def render_segment(
    recipe: dict[str, Any],
    base_blend: Path,
    world_digest: str,
    project: Path,
    index: int,
    duration: float,
    seed: int,
    asset: Path,
    crf: int,
    preset: str,
    resume: bool,
) -> dict[str, Any]:
    """Generate, render, encode and mechanically QA one long-form segment."""
    fps = int(recipe["motion"].get("fps", 60))
    segment_dir = project / "segments" / f"segment-{index:03d}"
    record_path = segment_dir / "segment.json"
    expected_signature = segment_signature(recipe, duration, seed, asset, world_digest)
    existing_record = read_json(record_path)

    if existing_record:
        recorded_signature = existing_record.get("signature")
        if recorded_signature != expected_signature:
            clear_stale_segment(segment_dir)
            existing_record = None
    elif segment_dir.exists():
        existing_motion = read_json(segment_dir / "motion.json")
        motion_matches = bool(
            existing_motion
            and existing_motion.get("seed") == seed
            and abs(float(existing_motion.get("duration_seconds", -1)) - duration) < 1e-6
            and int(existing_motion.get("fps", -1)) == fps
        )
        if not motion_matches and any(segment_dir.iterdir()):
            clear_stale_segment(segment_dir)

    frame_dir = segment_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    motion_path = segment_dir / "motion.json"
    blend_path = segment_dir / "mouse-hunt.blend"
    frame_prefix = frame_dir / "frame-"
    clip_path = segment_dir / "segment.mp4"
    qa_dir = segment_dir / "qa"

    motion_inputs = copy.deepcopy(recipe["motion"])
    motion_inputs.update({
        "duration_seconds": duration,
        "seed": seed,
        "output_path": str(motion_path),
    })
    motion_result = CatPreyMotion().execute(motion_inputs)
    if not motion_result.success:
        raise RuntimeError(f"segment {index}: motion failed: {motion_result.error}")

    render_inputs = copy.deepcopy(recipe["prey_render"])
    render_inputs.update({
        "base_blend_path": str(base_blend),
        "asset_path": str(asset),
        "motion_plan_path": str(motion_path),
        "blend_path": str(blend_path),
        "output_path": str(frame_prefix),
        "start_frame": 1,
        "end_frame": max(1, round(duration * fps)),
        "resume": resume,
        "decorate_world": False,
    })
    render_result = CatPreyBlender().execute(render_inputs)
    if not render_result.success:
        raise RuntimeError(f"segment {index}: Blender render failed: {render_result.error}")

    expected_frames = round(duration * fps)
    actual_frames = sum(1 for _ in frame_dir.glob("frame-*.png"))
    if actual_frames != expected_frames:
        raise RuntimeError(
            f"segment {index}: expected {expected_frames} PNG frames, found {actual_frames}; rerun with resume enabled"
        )

    if not clip_path.is_file() or not existing_record:
        run_ffmpeg_encode(frame_prefix, fps, clip_path, crf, preset)

    probe = VisualQA().execute({
        "operation": "probe",
        "input_path": str(clip_path),
        "expected": {
            "width": int(recipe["world"].get("width", 1920)),
            "height": int(recipe["world"].get("height", 1080)),
            "min_duration": max(0.1, duration - 0.08),
            "max_duration": duration + 0.08,
            "pixel_format": "yuv420p",
            "has_audio": False,
        },
    })
    if not probe.success:
        raise RuntimeError(f"segment {index}: visual_qa probe failed: {probe.error}")
    if not probe.data.get("validation_passed", False):
        raise RuntimeError(
            f"segment {index}: mechanical QA failed: {probe.data.get('validation_issues', [])}"
        )

    sampled = FrameSampler().execute({
        "input_path": str(clip_path),
        "strategy": "count",
        "count": 7,
        "output_dir": str(qa_dir),
        "format": "jpg",
        "quality": 2,
    })
    if not sampled.success:
        raise RuntimeError(f"segment {index}: frame sampling failed: {sampled.error}")

    record = {
        "index": index,
        "signature": expected_signature,
        "seed": seed,
        "duration_seconds": duration,
        "fps": fps,
        "frames": expected_frames,
        "motion_path": str(motion_path),
        "blend_path": str(blend_path),
        "clip_path": str(clip_path),
        "qa_frames": sampled.data.get("frames", []),
        "probe": probe.data,
    }
    write_json(record_path, record)
    return record


def stitch_segments(records: list[dict[str, Any]], output: Path) -> None:
    """Validate and concatenate approved segment encodes with OpenMontage."""
    clips = [record["clip_path"] for record in records]
    if len(clips) == 1:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(clips[0], output)
        return
    validate = VideoStitch().execute({"operation": "validate", "clips": clips})
    if not validate.success:
        raise RuntimeError(f"video_stitch validation failed: {validate.error}")
    if not validate.data.get("compatible", False):
        raise RuntimeError(f"segment encodes are not stitch-compatible: {validate.data.get('mismatches')}")
    stitched = VideoStitch().execute({
        "operation": "stitch",
        "clips": clips,
        "output_path": str(output),
        "transition": "cut",
        "auto_normalize": False,
    })
    if not stitched.success:
        raise RuntimeError(f"video_stitch failed: {stitched.error}")


def main() -> int:
    """Run one resumable long-form Cat TV production."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", default="examples/cat-tv/mouse-hunt-60s.json")
    parser.add_argument("--duration", type=parse_duration, default=parse_duration("60m"))
    parser.add_argument("--segment-seconds", type=float, default=300.0)
    parser.add_argument("--project-dir", default="projects/cat-tv/mouse-hunt-longform")
    parser.add_argument("--asset", help="Prey asset path; defaults to recipe/MOUSE_GLB_PATH")
    parser.add_argument("--world-asset", help="Optional GLB/GLTF/FBX/OBJ forest-floor surface layered over the procedural safety terrain")
    parser.add_argument("--base-seed", type=int)
    parser.add_argument("--crf", type=int, default=16)
    parser.add_argument("--preset", default="slow")
    parser.add_argument("--ambience", help="Optional natural ambience file to loop under the final master")
    parser.add_argument("--ambience-volume", type=float, default=0.13)
    parser.add_argument("--force-world", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--max-segments", type=int, help="Useful for local production smoke tests")
    args = parser.parse_args()

    recipe_path = Path(args.recipe).expanduser().resolve()
    recipe = env_expand(json.loads(recipe_path.read_text(encoding="utf-8")))
    project = Path(args.project_dir).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)

    asset_value = args.asset or recipe["prey_render"].get("asset_path", "")
    asset = Path(str(asset_value)).expanduser().resolve()
    if not asset.is_file():
        raise SystemExit(f"Prey asset not found: {asset}. Set --asset or MOUSE_GLB_PATH.")

    world_asset = None
    if args.world_asset:
        world_asset = Path(args.world_asset).expanduser().resolve()
        if not world_asset.is_file():
            raise SystemExit(f"World surface asset not found: {world_asset}")

    durations = segment_durations(args.duration, args.segment_seconds)
    if args.max_segments:
        durations = durations[: max(1, args.max_segments)]
    base_seed = int(args.base_seed if args.base_seed is not None else recipe["motion"].get("seed", 184321))
    plan = [
        {"index": index + 1, "duration_seconds": duration, "seed": base_seed + index}
        for index, duration in enumerate(durations)
    ]
    write_json(project / "production-plan.json", {
        "recipe": str(recipe_path),
        "requested_duration_seconds": args.duration,
        "planned_duration_seconds": sum(durations),
        "segment_target_seconds": args.segment_seconds,
        "segments": plan,
        "environment_seed": int((recipe.get("world_polish") or {}).get("seed", base_seed)),
        "asset": str(asset),
        "world_asset": str(world_asset) if world_asset else None,
    })
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0

    base_blend, world_digest = build_world(recipe, project, args.force_world, world_asset)
    records: list[dict[str, Any]] = []
    for entry in plan:
        print(f"[cat-tv] segment {entry['index']}/{len(plan)} seed={entry['seed']} duration={entry['duration_seconds']:.2f}s")
        record = render_segment(
            recipe,
            base_blend,
            world_digest,
            project,
            entry["index"],
            entry["duration_seconds"],
            entry["seed"],
            asset,
            args.crf,
            args.preset,
            not args.no_resume,
        )
        records.append(record)
        write_json(project / "production-state.json", {"completed_segments": records})

    silent_master = project / "mouse-hunt-master-silent.mp4"
    stitch_segments(records, silent_master)
    final_master = silent_master

    if args.ambience:
        ambience = Path(args.ambience).expanduser().resolve()
        if not ambience.is_file():
            raise SystemExit(f"Ambience file not found: {ambience}")
        final_master = project / "mouse-hunt-master.mp4"
        mux_ambience(silent_master, ambience, final_master, args.ambience_volume)

    expected_duration = sum(record["frames"] / record["fps"] for record in records)
    final_probe = VisualQA().execute({
        "operation": "probe",
        "input_path": str(final_master),
        "expected": {
            "width": int(recipe["world"].get("width", 1920)),
            "height": int(recipe["world"].get("height", 1080)),
            "min_duration": max(0.1, expected_duration - 0.25),
            "max_duration": expected_duration + 0.25,
            "pixel_format": "yuv420p",
            "has_audio": bool(args.ambience),
        },
    })
    if not final_probe.success:
        raise RuntimeError(f"Final VisualQA probe failed: {final_probe.error}")
    if not final_probe.data.get("validation_passed", False):
        raise RuntimeError(f"Final mechanical QA failed: {final_probe.data.get('validation_issues', [])}")

    final_frames = FrameSampler().execute({
        "input_path": str(final_master),
        "strategy": "count",
        "count": min(20, max(8, len(records) * 2)),
        "output_dir": str(project / "final-qa-frames"),
        "format": "jpg",
        "quality": 2,
    })
    if not final_frames.success:
        raise RuntimeError(f"Final frame sampling failed: {final_frames.error}")

    report = {
        "final_master": str(final_master),
        "silent_master": str(silent_master),
        "duration_seconds": expected_duration,
        "segment_count": len(records),
        "world_digest": world_digest,
        "world_asset": str(world_asset) if world_asset else None,
        "segments": records,
        "final_probe": final_probe.data,
        "final_qa_frames": final_frames.data.get("frames", []),
        "human_review_required": [
            "terrain edge/horizon is absent",
            "prey stays in the lower TV play zone and remains trackable and grounded",
            "prey faces the direction of travel rather than appearing to reverse",
            "segment joins do not create distracting prey/background jumps",
            "no flicker, clipping, strobing, or broken visibility transitions",
            "ambience, when present, remains subtle and non-fatiguing",
        ],
    }
    write_json(project / "render-report.json", report)
    print(f"[cat-tv] final master: {final_master}")
    print(f"[cat-tv] QA report: {project / 'render-report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
