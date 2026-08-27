# Cat TV examples

The first supported production is a deterministic **Mouse Hunt**. The core footage does not require a paid generative-video provider.

## Requirements

- Blender 4.5 LTS available to OpenMontage (`BLENDER_PATH` or the normal `blender_world` setup).
- A legally usable mouse model in GLB/GLTF, FBX, or OBJ format.
- FFmpeg/OpenMontage composition tools for packaging the rendered PNG sequence.

`mouse-hunt-60s.json` uses `${MOUSE_GLB_PATH}` as an intentional placeholder. Do not commit a binary model without recording its source and license.

## Production flow

1. Run `cat_prey_motion` with the `motion` object from `mouse-hunt-60s.json`. This writes `mouse.motion.json`.
2. Run `blender_world` with the `world` object. This creates the deterministic base environment as `base.blend`.
3. Before the full render, set the prey render to roughly 12 seconds (720 frames at 60 fps) and run `cat_prey_blender` using your mouse asset.
4. Review scale, ground contact, exits/re-entry, visibility changes, framing, and flicker.
5. Render the approved 60-second sequence to numbered PNG frames.
6. Package the sequence with `video_compose`/FFmpeg. Add only subtle ambience/SFX when desired; narration, text, and music are off by default.

## Long-form output

`blender_world`/Cat TV production is intentionally segmented. For a 30-minute, 1-hour, or 2-hour video, render segments of at most 600 seconds with distinct recorded seeds, then concatenate them with `video_stitch`. Avoid repeating one short loop.

## Current scope

The deterministic motion grammar currently supports `mouse` only. Bird, butterfly, insect, fish, and other prey types should be added as separate tested behavior grammars rather than aliases of mouse motion.
