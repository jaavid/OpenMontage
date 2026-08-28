"""Polish a reusable Blender world for long-form Cat TV production."""

from __future__ import annotations

import json
import subprocess
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
    ToolStatus,
    ToolTier,
)
from tools.graphics.blender_world import find_blender


_RUNTIME_SCRIPT = Path(__file__).resolve().parent / "templates" / "cat-tv-world-polish-runtime.py"


class CatTVWorldPolish(BaseTool):
    """Create a stable, reusable Cat TV environment before prey segments render."""

    name = "cat_tv_world_polish"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "cat_tv_world_polish"
    provider = "blender"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU
    dependencies: list[str] = []
    install_instructions = "Install Blender 4.5+ or configure BLENDER_PATH."
    capabilities = [
        "stable_environment_seed",
        "organic_terrain_palette",
        "static_forest_floor",
        "external_forest_floor_asset",
        "terrain_edge_guard",
        "reusable_long_form_world",
    ]
    supports = {"resume": False, "editable_blend": True, "offline": True, "glb": True, "gltf": True, "fbx": True, "obj": True}
    best_for = ["Polishing one Blender base world that is reused by every Cat TV render segment"]
    not_good_for = ["Animating prey", "Generating external photorealistic assets"]
    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {"type": "string", "enum": ["polish", "doctor"]},
            "base_blend_path": {"type": "string"},
            "blend_path": {"type": "string"},
            "seed": {"type": "integer", "default": 184321},
            "extension_size": {"type": "number", "minimum": 40, "default": 100},
            "leaf_count": {"type": "integer", "minimum": 0, "maximum": 600, "default": 180},
            "twig_count": {"type": "integer", "minimum": 0, "maximum": 200, "default": 28},
            "stone_count": {"type": "integer", "minimum": 0, "maximum": 100, "default": 14},
            "surface_asset_path": {"type": "string"},
            "surface_target_size": {"type": "number", "exclusiveMinimum": 0, "default": 14},
            "surface_z_offset": {"type": "number", "default": 0.02},
            "surface_rotation_degrees": {"type": "number", "default": 0},
        },
        "allOf": [
            {
                "if": {"properties": {"operation": {"const": "polish"}}},
                "then": {"required": ["base_blend_path", "blend_path"]},
            }
        ],
        "additionalProperties": False,
    }
    output_schema = {"type": "object"}
    artifact_schema = {"artifact": "3d_world"}
    resource_profile = ResourceProfile(cpu_cores=4, ram_mb=4096, vram_mb=2048, disk_mb=5000)
    idempotency_key_fields = [
        "base_blend_path", "seed", "extension_size", "leaf_count", "twig_count", "stone_count",
        "surface_asset_path", "surface_target_size", "surface_z_offset", "surface_rotation_degrees",
    ]
    side_effects = ["writes a polished .blend project and JSON report"]
    user_visible_verification = ["Review a final-resolution sample and verify that terrain edges and obvious procedural patterns are absent"]
    quality_score = 0.96

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if find_blender() and _RUNTIME_SCRIPT.is_file() else ToolStatus.UNAVAILABLE

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 25.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        blender = find_blender()
        if not blender:
            return ToolResult(success=False, error="Blender not found. " + self.install_instructions)
        operation = str(inputs.get("operation") or "")
        if operation == "doctor":
            return ToolResult(success=True, data={"blender_path": str(blender), "runtime_script": str(_RUNTIME_SCRIPT)})
        if operation != "polish":
            return ToolResult(success=False, error=f"Unknown operation: {operation}")

        base_blend = Path(str(inputs.get("base_blend_path", ""))).expanduser().resolve()
        output_blend = Path(str(inputs.get("blend_path", ""))).expanduser().resolve()
        if not base_blend.is_file():
            return ToolResult(success=False, error=f"Base blend file not found: {base_blend}")
        output_blend.parent.mkdir(parents=True, exist_ok=True)

        surface_raw = str(inputs.get("surface_asset_path") or "").strip()
        surface_asset = Path(surface_raw).expanduser().resolve() if surface_raw else None
        if surface_asset is not None and not surface_asset.is_file():
            return ToolResult(success=False, error=f"Surface asset not found: {surface_asset}")

        command = [
            str(blender),
            "--background",
            str(base_blend),
            "--python",
            str(_RUNTIME_SCRIPT),
            "--",
            "--blend",
            str(output_blend),
            "--seed",
            str(int(inputs.get("seed", 184321))),
            "--extension-size",
            str(float(inputs.get("extension_size", 100))),
            "--leaf-count",
            str(int(inputs.get("leaf_count", 180))),
            "--twig-count",
            str(int(inputs.get("twig_count", 28))),
            "--stone-count",
            str(int(inputs.get("stone_count", 14))),
            "--surface-target-size",
            str(float(inputs.get("surface_target_size", 14))),
            "--surface-z-offset",
            str(float(inputs.get("surface_z_offset", 0.02))),
            "--surface-rotation-degrees",
            str(float(inputs.get("surface_rotation_degrees", 0))),
        ]
        if surface_asset is not None:
            command.extend(["--surface-asset", str(surface_asset)])

        started = time.time()
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Cat TV world polish failed to start: {exc}")

        combined = "\n".join(part for part in (process.stdout, process.stderr) if part)
        if (
            process.returncode != 0
            or "Traceback (most recent call last):" in combined
            or "OPENMONTAGE_CAT_TV_WORLD_POLISH=" not in process.stdout
            or not output_blend.is_file()
        ):
            return ToolResult(success=False, error="Cat TV world polish failed: " + combined[-4000:])

        report_path = output_blend.with_suffix(".world-polish.json")
        data: dict[str, Any] = {
            "blend_path": str(output_blend),
            "report": str(report_path),
            "seed": int(inputs.get("seed", 184321)),
            "surface_asset_path": str(surface_asset) if surface_asset else None,
        }
        if report_path.is_file():
            try:
                data["world_polish"] = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        artifacts = [str(output_blend)]
        if report_path.is_file():
            artifacts.append(str(report_path))
        return ToolResult(
            success=True,
            data=data,
            artifacts=artifacts,
            duration_seconds=round(time.time() - started, 2),
            seed=int(inputs.get("seed", 184321)),
            model="blender-cat-tv-world-polish-v2",
        )
