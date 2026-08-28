# Cat TV examples

The first supported production is a deterministic **Mouse Hunt** for the CatFactory / Cat TV Lab workflow. Core footage is local and procedural; it does not require a paid generative-video provider.

## Requirements

- Blender 4.5+ available to OpenMontage (`BLENDER_PATH` or the normal `blender_world` setup).
- FFmpeg and ffprobe on `PATH`.
- A legally usable mouse model in GLB/GLTF, FBX, or OBJ format.
- Optionally, a licensed forest-floor GLB/GLTF/FBX/OBJ used as a real central surface over the procedural safety terrain.

`mouse-hunt-60s.json` uses `${MOUSE_GLB_PATH}` intentionally. Do not commit third-party binary models without recording source and license.

## Production flow

1. Run `cat_prey_motion` with the recipe `motion` object. This writes renderer-neutral seeded motion JSON.
2. Run `blender_world` with the recipe `world` object. This creates the geometric safety environment.
3. Run `cat_tv_world_polish` once. It creates `base-polished.blend` with a stable organic ground palette, terrain-edge guard, optional real forest-floor surface, sparse static litter, and a fixed environment seed.
4. Render a 10-15 second sample with `cat_prey_blender` using `base-polished.blend`. Keep `decorate_world=false`; environment detail must not follow the prey-motion seed.
5. Review that the prey faces its direction of travel, spends most visible time in the lower TV play zone, remains grounded and trackable, and does not reveal terrain edges.
6. Render production PNG sequences with resume enabled. Re-running the same request continues from the first missing frame.
7. Encode reviewed PNG sequences to high-quality H.264 intermediates.
8. Use `video_stitch` for long-form cut-only concatenation after compatibility validation.
9. Use `frame_sampler` and `visual_qa` for representative-frame and ffprobe-backed QA.
10. Optionally add subtle natural ambience. Narration, captions, spoken branding, and music are off by default for the continuous Cat TV stimulus.

## Real forest-floor assets

The long-form runner accepts `--world-asset`. The imported surface is centered, normalized to the configured target size, placed just above the procedural terrain, and saved into the reusable polished world. The procedural terrain remains underneath as a continuity and horizon safety layer.

Example:

```bash
python -m scripts.cat_tv_longform \
  --recipe examples/cat-tv/mouse-hunt-60s.json \
  --duration 12s \
  --segment-seconds 12 \
  --project-dir projects/cat-tv/mouse-hunt-preview-pine \
  --asset "$MOUSE_GLB_PATH" \
  --world-asset assets/cat-tv/world/pine_needle_forest_floor.glb
```

Use a separate `--project-dir` when comparing different world assets so their frames and QA artifacts remain isolated.

## Long-form runner

Invoke the runner as a module from the repository root:

```bash
python -m scripts.cat_tv_longform \
  --recipe examples/cat-tv/mouse-hunt-60s.json \
  --duration 2h \
  --segment-seconds 300 \
  --asset "$MOUSE_GLB_PATH" \
  --world-asset assets/cat-tv/world/pine_needle_forest_floor.glb
```

Useful first checks:

```bash
# Plan only; no Blender render.
python -m scripts.cat_tv_longform --duration 2h --plan-only

# Render only the first five-minute segment as a production smoke test.
python -m scripts.cat_tv_longform \
  --duration 2h \
  --segment-seconds 300 \
  --max-segments 1 \
  --asset "$MOUSE_GLB_PATH" \
  --world-asset assets/cat-tv/world/pine_needle_forest_floor.glb
```

The runner creates one polished base world, then independent prey-motion segments with incrementing seeds. Each segment retains its motion JSON, editable `.blend`, resumable PNG sequence, encoded intermediate, QA frames, and mechanical probe report. The final master is validated and representative frames are extracted for human/agent visual review.

For a two-hour program, the default strategy is **24 x 5-minute segments** rather than one two-hour Blender process or a repeated short loop.

## Optional ambience

If a natural ambience file is available, pass it only after the silent visual master is stable:

```bash
python -m scripts.cat_tv_longform \
  --duration 2h \
  --asset "$MOUSE_GLB_PATH" \
  --world-asset assets/cat-tv/world/pine_needle_forest_floor.glb \
  --ambience assets/cat-tv/audio/forest-ambience.wav \
  --ambience-volume 0.13
```

Keep ambience subtle and continuous. Avoid obvious short-loop resets or loud transient effects.

## Current scope

The deterministic motion grammar currently supports `mouse` only. The repository can store other licensed prey assets, but bird, butterfly, beetle/insect, gecko, fish, and other prey should be added as separate tested behavior grammars rather than aliases of mouse motion.
