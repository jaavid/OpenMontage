"""Apply a Cat TV prey motion plan to a Blender world and optionally render it."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ResourceProfile, ToolResult,
    ToolRuntime, ToolStability, ToolStatus, ToolTier,
)
from tools.graphics.blender_world import find_blender, first_missing_frame


_RUNTIME_SCRIPT = Path(__file__).resolve().parent / "templates" / "cat-prey-runtime.py"


class CatPreyBlender(BaseTool):
    name = "cat_prey_blender"
    version = "0.3.0"
    tier = ToolTier.GENERATE
    capability = "prey_animation_rendering"
    provider = "blender"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU
    dependencies: list[str] = []
    install_instructions = "Install Blender 4.5+ or configure BLENDER_PATH as documented by blender_world."
    capabilities = [
        "apply_prey_motion", "render_prey_animation", "ground_following_motion",
        "procedural_body_micro_motion", "procedural_forest_floor", "resumable_png_render",
    ]
    supports = {"glb": True, "gltf": True, "fbx": True, "obj": True, "animation": True, "resume": True}
    best_for = ["Adding deterministic prey movement to a Blender world built by blender_world"]
    not_good_for = ["Generating the prey mesh itself"]
    input_schema = {
        "type": "object",
        "required": ["operation", "base_blend_path", "asset_path"],
        "properties": {
            "operation": {"type": "string", "enum": ["apply", "render_animation", "doctor"]},
            "base_blend_path": {"type": "string"},
            "asset_path": {"type": "string"},
            "motion_plan": {"type": "object"},
            "motion_plan_path": {"type": "string"},
            "blend_path": {"type": "string"},
            "output_path": {"type": "string"},
            "target_height": {"type": "number", "exclusiveMinimum": 0, "default": 0.34},
            "fps": {"type": "integer", "minimum": 1, "maximum": 120},
            "start_frame": {"type": "integer", "minimum": 1},
            "end_frame": {"type": "integer", "minimum": 1},
            "resume": {"type": "boolean", "default": True},
            "timeout_seconds": {"type": "integer", "minimum": 120},
            "seconds_per_frame_budget": {"type": "number", "minimum": 1, "default": 8.0},
            "decorate_world": {"type": "boolean", "default": True},
        },
    }
    output_schema = {"type": "object"}
    artifact_schema = {"artifact": "3d_world"}
    resource_profile = ResourceProfile(cpu_cores=8, ram_mb=8192, vram_mb=6000, disk_mb=20000)
    idempotency_key_fields = [
        "operation", "base_blend_path", "asset_path", "motion_plan", "motion_plan_path",
        "target_height", "start_frame", "end_frame",
    ]
    side_effects = ["writes a .blend project", "may render a resumable PNG image sequence"]
    user_visible_verification = ["Review a 10-15 second sample before a long Cat TV render"]
    quality_score = 0.95

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if find_blender() and _RUNTIME_SCRIPT.is_file() else ToolStatus.UNAVAILABLE

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        if inputs.get("operation") != "render_animation":
            return 15.0
        start = int(inputs.get("start_frame") or 1)
        end = int(inputs.get("end_frame") or start)
        frame_count = max(1, end - start + 1)
        return frame_count * float(inputs.get("seconds_per_frame_budget", 8.0))

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        blender = find_blender()
        if not blender:
            return ToolResult(success=False, error="Blender not found. " + self.install_instructions)
        operation = str(inputs.get("operation") or "")
        if operation == "doctor":
            return ToolResult(success=True, data={"blender_path": str(blender), "runtime_script": str(_RUNTIME_SCRIPT)})
        if operation not in {"apply", "render_animation"}:
            return ToolResult(success=False, error=f"Unknown operation: {operation}")

        base_blend = Path(str(inputs.get("base_blend_path", ""))).expanduser().resolve()
        asset = Path(str(inputs.get("asset_path", ""))).expanduser().resolve()
        if not base_blend.is_file():
            return ToolResult(success=False, error=f"Base blend file not found: {base_blend}")
        if not asset.is_file():
            return ToolResult(success=False, error=f"Prey asset not found: {asset}")

        plan: dict[str, Any] | None = inputs.get("motion_plan") if isinstance(inputs.get("motion_plan"), dict) else None
        plan_path_raw = inputs.get("motion_plan_path")
        if plan is None and plan_path_raw:
            try:
                plan = json.loads(Path(str(plan_path_raw)).expanduser().resolve().read_text(encoding="utf-8"))
            except Exception as exc:
                return ToolResult(success=False, error=f"Could not read motion plan: {exc}")
        if not plan or not isinstance(plan.get("keyframes"), list):
            return ToolResult(success=False, error="motion_plan or motion_plan_path with keyframes is required")

        blend_path = Path(
            str(inputs.get("blend_path") or base_blend.with_name(base_blend.stem + "-cat-tv.blend"))
        ).expanduser().resolve()
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        serialized_plan = blend_path.with_suffix(".motion.json")
        serialized_plan.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        fps = int(inputs.get("fps") or plan.get("fps") or 60)
        duration = float(plan.get("duration_seconds") or 60)
        requested_start = int(inputs.get("start_frame") or 1)
        requested_end = int(inputs.get("end_frame") or round(duration * fps))
        effective_start = requested_start

        output_path = inputs.get("output_path")
        resolved_output: Path | None = None
        if operation == "render_animation":
            if not output_path:
                return ToolResult(success=False, error="output_path is required for render_animation")
            resolved_output = Path(str(output_path)).expanduser().resolve()
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            if bool(inputs.get("resume", True)):
                missing = first_missing_frame(resolved_output, requested_start, requested_end)
                if missing is None:
                    return ToolResult(
                        success=True,
                        data={
                            "blend_path": str(blend_path),
                            "output": str(resolved_output),
                            "already_complete": True,
                            "start_frame": requested_start,
                            "end_frame": requested_end,
                            "resumed": False,
                        },
                        artifacts=[str(resolved_output.parent)],
                        seed=plan.get("seed"),
                        model="blender-eevee-cat-tv-v3",
                    )
                effective_start = missing

        command = [
            str(blender), "--background", str(base_blend), "--python", str(_RUNTIME_SCRIPT), "--",
            "--operation", operation,
            "--asset", str(asset),
            "--motion", str(serialized_plan),
            "--blend", str(blend_path),
            "--target-height", str(float(inputs.get("target_height", 0.34))),
            "--fps", str(fps),
            "--start-frame", str(effective_start),
            "--end-frame", str(requested_end),
        ]
        if bool(inputs.get("decorate_world", True)):
            command.append("--decorate-world")
        if resolved_output is not None:
            command.extend(["--output", str(resolved_output)])

        frame_count = max(1, requested_end - effective_start + 1)
        frame_budget = float(inputs.get("seconds_per_frame_budget", 8.0))
        timeout_seconds = int(inputs.get("timeout_seconds") or max(600, frame_count * frame_budget))

        started = time.time()
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            completed = 0
            if resolved_output is not None:
                completed = sum(
                    1
                    for frame in range(effective_start, requested_end + 1)
                    if (resolved_output.parent / f"{resolved_output.name}{frame:04d}.png").is_file()
                )
            return ToolResult(
                success=False,
                error=(
                    f"Blender render timed out after {timeout_seconds}s with {completed}/{frame_count} "
                    "frames completed in this range. Re-run the same request with resume=true to continue. "
                    f"Last output: {(exc.stderr or exc.stdout or '')[-1500:]}"
                ),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Blender invocation failed: {exc}")

        combined_output = "\n".join(part for part in (process.stdout, process.stderr) if part)
        runtime_marker = "OPENMONTAGE_CAT_TV_REPORT=" in process.stdout
        if (
            process.returncode != 0
            or "Traceback (most recent call last):" in combined_output
            or not runtime_marker
        ):
            return ToolResult(success=False, error="Cat prey Blender step failed: " + combined_output[-3000:])
        if not blend_path.is_file():
            return ToolResult(
                success=False,
                error=f"Blender completed without writing the expected Cat TV blend file: {blend_path}\n{combined_output[-2000:]}",
            )

        if operation == "render_animation" and resolved_output is not None:
            last_frame = resolved_output.parent / f"{resolved_output.name}{requested_end:04d}.png"
            if not last_frame.is_file():
                next_missing = first_missing_frame(resolved_output, requested_start, requested_end)
                return ToolResult(
                    success=False,
                    error=(
                        f"Blender exited without producing the requested final frame: {last_frame}. "
                        f"Next missing frame is {next_missing}; re-run with resume=true."
                    ),
                )

        artifacts = [str(blend_path), str(serialized_plan)]
        report_path = blend_path.with_suffix(".cat-tv-report.json")
        if report_path.is_file():
            artifacts.append(str(report_path))
        if resolved_output is not None:
            artifacts.append(str(resolved_output.parent))
        return ToolResult(
            success=True,
            data={
                "blend_path": str(blend_path),
                "output": str(output_path or ""),
                "report": str(report_path),
                "start_frame": effective_start,
                "end_frame": requested_end,
                "resumed": effective_start > requested_start,
                "frames_rendered": frame_count,
            },
            artifacts=artifacts,
            duration_seconds=round(time.time() - started, 2),
            seed=plan.get("seed"),
            model="blender-eevee-cat-tv-v3",
        )
