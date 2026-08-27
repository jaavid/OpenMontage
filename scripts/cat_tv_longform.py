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
import json
import os
import re
import shutil
import subprocess
import sys
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
    """Split a production into valid 10..600 second render segments."""
    if target_seconds < 10 or target_seconds > 600:
        raise ValueError("segment_seconds must be between 10 and 600")
    remaining = float(total_seconds)
    result: list[float] = []
    while remaining > target_seconds:
        result.append(float(target_seconds))
        remaining -= target_seconds
    if remaining > 0:
        if remaining < 10 and result and result[-1] + remaining <= 600:
            result[-1] += remaining
        else:
            result.append(remaining)
    if any(value < 10 or value > 600 for value in result):
        raise ValueError(f"Could not create valid Cat TV segments: {result}")
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


def build_world(recipe: dict[str, Any], project: Path, force: bool) -> Path:
    """Build and polish the one environment shared by all prey segments."""
    base = project / "base.blend"
    polished = project / "base-polished.blend"
    if polished.is_file() and not force:
        return polished

    world_inputs = copy.deepcopy(recipe["world"])
    world_inputs["blend_path"] = str(base)
    world_result = BlenderWorld().execute(world_inputs)
    if not world_result.success:
        raise RuntimeError(f"blender_world failed: {world_result.error}")
    if not base.is_file():
        raise RuntimeError(f"blender_world did not produce {base}")

    polish_inputs = copy.deepcopy(recipe.get("world_polish") or {})
    polish_inputs.update({
        "operation": "polish",
        "base_blend_path": str(base),
        "blend_path": str(polished),
    })
    polish_result = CatTVWorldPolish().execute(polish_inputs)
    if not polish_result.success:
        raise RuntimeError(f"cat_tv_world_polish failed: {polish_result.error}")
    return polished


def render_segment(
    recipe: dict[str, Any],
    base_blend: Path,
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
        # Static litter belongs to base-polished.blend, never to a prey seed.
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

    if not clip_path.is_file():
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
    write_json(segment_dir / "segment.json", record)
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
    })
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0

    base_blend = build_world(recipe, project, args.force_world)
    records: list[dict[str, Any]] = []
    for entry in plan:
        print(f"[cat-tv] segment {entry['index']}/{len(plan)} seed={entry['seed']} duration={entry['duration_seconds']:.2f}s")
        record = render_segment(
            recipe,
            base_blend,
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

    expected_duration = sum(record["duration_seconds"] for record in records)
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
        "segments": records,
        "final_probe": final_probe.data,
        "final_qa_frames": final_frames.data.get("frames", []),
        "human_review_required": [
            "terrain edge/horizon is absent",
            "prey stays trackable and grounded",
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
