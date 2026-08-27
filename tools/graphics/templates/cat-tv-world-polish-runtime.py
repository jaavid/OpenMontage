"""Blender-side Cat TV world polish pass.

This pass is intentionally separate from prey animation. It turns one base
world into a stable long-form environment that can be reused by many seeded
prey segments without background discontinuities at segment joins.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def args_after_separator() -> argparse.Namespace:
    """Parse runtime arguments after Blender's ``--`` separator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--seed", type=int, default=184321)
    parser.add_argument("--extension-size", type=float, default=100.0)
    parser.add_argument("--leaf-count", type=int, default=180)
    parser.add_argument("--twig-count", type=int, default=28)
    parser.add_argument("--stone-count", type=int, default=14)
    parser.add_argument("--surface-asset", default="")
    parser.add_argument("--surface-target-size", type=float, default=14.0)
    parser.add_argument("--surface-z-offset", type=float, default=0.02)
    parser.add_argument("--surface-rotation-degrees", type=float, default=0.0)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def simple_material(name: str, color: tuple[float, float, float, float], roughness: float = 0.94):
    """Create or reuse a simple Principled material."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def polygon_center(mesh, polygon) -> Vector:
    """Return the local-space average vertex position for one polygon."""
    return sum((mesh.vertices[index].co for index in polygon.vertices), Vector()) / len(polygon.vertices)


def organic_field(x: float, y: float, seed: int) -> float:
    """Generate a deterministic low-frequency field without circular patch artifacts."""
    phase = seed * 0.017453292519943295
    return (
        math.sin(x * 0.39 + phase) * 0.48
        + math.sin(y * 0.27 - phase * 0.7) * 0.34
        + math.sin((x + y) * 0.16 + phase * 1.7) * 0.27
        + math.sin((x - y) * 0.71 - phase * 0.23) * 0.11
    )


def polish_terrain(seed: int) -> dict:
    """Give WorldTerrain a natural mottled palette while preserving its geometry."""
    terrain = bpy.data.objects.get("WorldTerrain")
    if terrain is None or terrain.type != "MESH":
        raise RuntimeError("Expected Blender object 'WorldTerrain' was not found")

    palette = [
        simple_material("CAT_TV_Ground_Moss", (0.205, 0.285, 0.105, 1.0), 0.97),
        simple_material("CAT_TV_Ground_Olive", (0.255, 0.315, 0.125, 1.0), 0.96),
        simple_material("CAT_TV_Ground_Earth", (0.255, 0.205, 0.105, 1.0), 0.98),
        simple_material("CAT_TV_Ground_Shadow", (0.155, 0.215, 0.085, 1.0), 0.98),
    ]
    for mat in palette:
        terrain.data.materials.append(mat)
    material_start = len(terrain.data.materials) - len(palette)

    counts = [0, 0, 0, 0]
    for polygon in terrain.data.polygons:
        center = polygon_center(terrain.data, polygon)
        value = organic_field(float(center.x), float(center.y), seed)
        if value > 0.56:
            choice = 2
        elif value > 0.12:
            choice = 1
        elif value < -0.52:
            choice = 3
        else:
            choice = 0
        polygon.material_index = material_start + choice
        counts[choice] += 1

    return {
        "object": terrain.name,
        "material_faces": {
            "moss": counts[0],
            "olive": counts[1],
            "earth": counts[2],
            "shadow": counts[3],
        },
    }


def add_ground_extension(size: float) -> str:
    """Add a low fallback plane so no dark world background appears beyond terrain."""
    existing = bpy.data.objects.get("CAT_TV_GROUND_EXTENSION")
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=max(40.0, size), location=(0.0, 0.0, -0.35))
    plane = bpy.context.object
    plane.name = "CAT_TV_GROUND_EXTENSION"
    plane.data.materials.append(simple_material("CAT_TV_Ground_Extension", (0.19, 0.255, 0.10, 1.0), 0.99))
    return plane.name


def ground_height(x: float, y: float) -> float:
    """Raycast to the visible ground while ignoring Cat TV litter itself."""
    ignored = [
        obj for obj in bpy.context.scene.objects
        if obj.name.startswith("CAT_TV_LITTER_")
    ]
    states = [(obj, obj.hide_viewport) for obj in ignored]
    for obj, _state in states:
        obj.hide_viewport = True
    bpy.context.view_layer.update()
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        hit, location, _normal, _index, _obj, _matrix = bpy.context.scene.ray_cast(
            depsgraph,
            Vector((x, y, 1000.0)),
            Vector((0.0, 0.0, -1.0)),
            distance=2000.0,
        )
        return float(location.z) if hit else -0.30
    finally:
        for obj, state in states:
            obj.hide_viewport = state
        bpy.context.view_layer.update()


def import_surface_asset(path: Path, target_size: float, z_offset: float, rotation_degrees: float) -> dict:
    """Import and normalize a real forest-floor asset over the procedural safety terrain."""
    base_ground = ground_height(0.0, 0.0)
    before = set(bpy.context.scene.objects)
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise ValueError(f"Unsupported surface asset format: {path}")

    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    if not imported:
        raise RuntimeError("Surface asset import created no Blender objects")

    root = bpy.data.objects.new("CAT_TV_SURFACE_ROOT", None)
    bpy.context.collection.objects.link(root)
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            matrix_world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = matrix_world
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.use_smooth = True

    points = []
    for obj in imported:
        if obj.type == "MESH":
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        raise RuntimeError("Surface asset contains no mesh bounding boxes")

    xmin, xmax = min(p.x for p in points), max(p.x for p in points)
    ymin, ymax = min(p.y for p in points), max(p.y for p in points)
    zmin, zmax = min(p.z for p in points), max(p.z for p in points)
    source_size = max(0.001, xmax - xmin, ymax - ymin)
    scale = float(target_size) / source_size
    cx, cy = (xmin + xmax) * 0.5, (ymin + ymax) * 0.5
    angle = math.radians(float(rotation_degrees))
    scaled_cx, scaled_cy = cx * scale, cy * scale
    rotated_cx = scaled_cx * math.cos(angle) - scaled_cy * math.sin(angle)
    rotated_cy = scaled_cx * math.sin(angle) + scaled_cy * math.cos(angle)

    root.scale = (scale, scale, scale)
    root.rotation_euler[2] = angle
    root.location = (
        -rotated_cx,
        -rotated_cy,
        base_ground + float(z_offset) - zmin * scale,
    )
    bpy.context.view_layer.update()

    return {
        "path": str(path),
        "objects": len(imported),
        "target_size": float(target_size),
        "source_xy_size": source_size,
        "source_height": zmax - zmin,
        "scale": scale,
        "rotation_degrees": float(rotation_degrees),
        "z_offset": float(z_offset),
    }


def terrain_bounds() -> tuple[float, float, float, float]:
    """Return XY bounds of the reusable terrain object."""
    terrain = bpy.data.objects.get("WorldTerrain")
    if terrain is None:
        return (-25.0, 25.0, -25.0, 25.0)
    points = [terrain.matrix_world @ Vector(corner) for corner in terrain.bound_box]
    return (
        min(point.x for point in points),
        max(point.x for point in points),
        min(point.y for point in points),
        max(point.y for point in points),
    )


def make_mesh(name: str, vertices: list[tuple], faces: list[tuple], mat):
    """Build one reusable low-poly litter mesh."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    return mesh


def build_litter_meshes():
    """Create compact organic meshes for static long-form forest-floor detail."""
    leaf_mats = [
        simple_material("CAT_TV_Litter_Leaf_Amber", (0.34, 0.19, 0.05, 1.0), 0.99),
        simple_material("CAT_TV_Litter_Leaf_Brown", (0.19, 0.085, 0.025, 1.0), 0.99),
        simple_material("CAT_TV_Litter_Leaf_Olive", (0.29, 0.255, 0.07, 1.0), 0.99),
    ]
    leaf_vertices = [
        (-0.09, 0.0, 0.0),
        (-0.025, 0.045, 0.008),
        (0.075, 0.012, 0.002),
        (0.035, -0.047, 0.011),
        (-0.035, -0.035, -0.002),
    ]
    leaves = [
        make_mesh(f"CAT_TV_LEAF_SOURCE_{i}", leaf_vertices, [(0, 1, 2, 3, 4)], mat)
        for i, mat in enumerate(leaf_mats)
    ]

    twig_mat = simple_material("CAT_TV_Litter_Twig", (0.115, 0.052, 0.018, 1.0), 0.98)
    twig = make_mesh(
        "CAT_TV_TWIG_SOURCE",
        [
            (-0.16, -0.010, -0.008), (0.16, -0.010, -0.008), (0.16, 0.010, -0.008), (-0.16, 0.010, -0.008),
            (-0.16, -0.010, 0.008), (0.16, -0.010, 0.008), (0.16, 0.010, 0.008), (-0.16, 0.010, 0.008),
        ],
        [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)],
        twig_mat,
    )

    stone_mats = [
        simple_material("CAT_TV_Litter_Stone_Warm", (0.18, 0.155, 0.115, 1.0), 0.96),
        simple_material("CAT_TV_Litter_Stone_Moss", (0.135, 0.17, 0.09, 1.0), 0.97),
    ]
    stone_vertices = [(0, 0, 0.075), (0.08, 0, 0), (0, 0.065, 0), (-0.08, 0, 0), (0, -0.065, 0), (0, 0, -0.035)]
    stones = [
        make_mesh(
            f"CAT_TV_STONE_SOURCE_{i}",
            stone_vertices,
            [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)],
            mat,
        )
        for i, mat in enumerate(stone_mats)
    ]
    return leaves, [twig], stones


def scatter_static_litter(seed: int, leaf_count: int, twig_count: int, stone_count: int) -> dict:
    """Scatter small static detail once so every prey segment sees the same world."""
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith("CAT_TV_LITTER_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    rng = random.Random(seed + 104729)
    xmin, xmax, ymin, ymax = terrain_bounds()
    margin = 1.5
    xmin += margin
    xmax -= margin
    ymin += margin
    ymax -= margin
    leaves, twigs, stones = build_litter_meshes()
    report = {"leaves": 0, "twigs": 0, "stones": 0}
    report_key = {"leaf": "leaves", "twig": "twigs", "stone": "stones"}

    cluster_count = max(8, min(28, leaf_count // 8 if leaf_count else 8))
    clusters = [
        (rng.uniform(xmin, xmax), rng.uniform(ymin, ymax), rng.uniform(0.45, 1.25))
        for _ in range(cluster_count)
    ]

    def spawn(kind: str, sources: list, count: int, scale_range: tuple[float, float], clustered: bool = False) -> None:
        for index in range(max(0, count)):
            if clustered:
                cx, cy, spread = rng.choice(clusters)
                x = max(xmin, min(xmax, rng.gauss(cx, spread)))
                y = max(ymin, min(ymax, rng.gauss(cy, spread * 0.72)))
            else:
                x = rng.uniform(xmin, xmax)
                y = rng.uniform(ymin, ymax)
            z = ground_height(x, y)
            source = rng.choice(sources)
            obj = bpy.data.objects.new(f"CAT_TV_LITTER_{kind.upper()}_{index:04d}", source)
            bpy.context.collection.objects.link(obj)
            obj.location = (x, y, z + (0.015 if kind == "leaf" else 0.025 if kind == "twig" else 0.045))
            obj.rotation_euler = (
                rng.uniform(-0.08, 0.08),
                rng.uniform(-0.08, 0.08),
                rng.uniform(0.0, math.tau),
            )
            scale = rng.uniform(*scale_range)
            obj.scale = (scale, scale * rng.uniform(0.72, 1.22), scale)
            report[report_key[kind]] += 1

    spawn("leaf", leaves, leaf_count, (0.42, 0.92), clustered=True)
    spawn("twig", twigs, twig_count, (0.45, 0.95))
    spawn("stone", stones, stone_count, (0.48, 0.95))
    return report


def tune_world_background() -> None:
    """Keep any residual far background close to the terrain palette."""
    world = bpy.context.scene.world
    if not world or not world.use_nodes or not world.node_tree:
        return
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.18, 0.245, 0.095, 1.0)
        background.inputs["Strength"].default_value = 0.42


def main() -> None:
    """Polish the loaded base world and save a reusable long-form blend."""
    args = args_after_separator()
    terrain_report = polish_terrain(args.seed)
    extension = add_ground_extension(args.extension_size)
    surface_report = None
    if args.surface_asset:
        surface_report = import_surface_asset(
            Path(args.surface_asset).expanduser().resolve(),
            args.surface_target_size,
            args.surface_z_offset,
            args.surface_rotation_degrees,
        )
    litter_report = scatter_static_litter(args.seed, args.leaf_count, args.twig_count, args.stone_count)
    tune_world_background()

    output = Path(args.blend).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report = {
        "version": "2.0",
        "seed": args.seed,
        "terrain": terrain_report,
        "ground_extension": extension,
        "surface_asset": surface_report,
        "static_litter": litter_report,
        "blend_path": str(output),
    }
    report_path = output.with_suffix(".world-polish.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("OPENMONTAGE_CAT_TV_WORLD_POLISH=" + json.dumps(report, sort_keys=True))


main()
