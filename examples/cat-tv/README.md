# Cat TV examples

The first supported production is a deterministic **Mouse Hunt** for the CatFactory / Cat TV Lab workflow. Core footage is local and procedural; it does not require a paid generative-video provider.

## Requirements

- Blender 4.5+ available to OpenMontage (`BLENDER_PATH` or the normal `blender_world` setup).
- FFmpeg and ffprobe on `PATH`.
- A legally usable mouse model in GLB/GLTF, FBX, or OBJ format.

`mouse-hunt-60s.json` uses `${MOUSE_GLB_PATH}` intentionally. Do not commit a third-party binary model without recording its source and license.

## Production flow

1. Run `cat_prey_motion` with the recipe `motion` object. This writes renderer-neutral seeded motion JSON.
2. Run `blender_world` with the recipe `world` object. This creates the geometric base environment.
3. Run `cat_tv_world_polish` once. It creates `base-polished.blend` with a stable organic ground palette, static clustered forest-floor detail, a terrain-edge guard, and a fixed environment seed.
4. Render a 10-15 second sample with `cat_prey_blender` using `base-polished.blend`. Keep `decorate_world=false`; environment detail must not follow the prey-motion seed.
5. Review scale, ground contact, body motion, exits/re-entry, visibility, framing, terrain-edge absence, background density, and flicker.
6. Render production PNG sequences with resume enabled. Re-running the same request continues from the first missing frame.
7. Encode reviewed PNG sequences to high-quality H.264 intermediates.
8. Use `video_stitch` for long-form cut-only concatenation after compatibility validation.
9. Use `frame_sampler` and `visual_qa` for representative-frame and ffprobe-backed QA.
10. Optionally add subtle natural ambience. Narration, captions, spoken branding, and music are off by default for the continuous Cat TV stimulus.

## 60-second sample recipe

`mouse-hunt-60s.json` is the reference recipe. The production environment is now deliberately larger than the camera footprint, then polished into a separate reusable blend before prey rendering.

## Long-form runner

Invoke the runner as a module from the repository root so the OpenMontage tool packages are always importable:

```bash
python -m scripts.cat_tv_longform \
  --recipe examples/cat-tv/mouse-hunt-60s.json \
  --duration 2h \
  --segment-seconds 300 \
  --asset "$MOUSE_GLB_PATH"
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
  --asset "$MOUSE_GLB_PATH"
```

The runner creates one polished base world, then independent prey-motion segments with incrementing seeds. Each segment retains its motion JSON, editable `.blend`, resumable PNG sequence, encoded intermediate, QA frames, and mechanical probe report. The final master is validated and representative frames are extracted for human/agent visual review.

For a two-hour program, the default strategy is **24 x 5-minute segments** rather than one two-hour Blender process or a repeated short loop.

## Optional ambience

If a natural ambience file is available, pass it only after the silent visual master is stable:

```bash
python -m scripts.cat_tv_longform \
  --duration 2h \
  --asset "$MOUSE_GLB_PATH" \
  --ambience assets/cat-tv/audio/forest-ambience.wav \
  --ambience-volume 0.13
```

Keep ambience subtle and continuous. Avoid obvious short-loop resets or loud transient effects.

## Current scope

The deterministic motion grammar currently supports `mouse` only. Bird, butterfly, fly/insect, gecko, fish, and other prey should be added as separate tested behavior grammars rather than aliases of mouse motion.
