# Cat TV Production

Use this Layer 2 skill for long-form videos whose primary audience is a cat watching a display. The default production route is deterministic procedural prey motion rendered in a real 3D scene, not repeated AI-generated clips.

## Production route

1. Use the `cat-tv` pipeline.
2. Generate a renderer-neutral motion plan with `cat_prey_motion` and preserve its seed.
3. Build the environment with `blender_world`. Keep the camera fixed or very stable unless the user explicitly requests camera motion.
4. Import a licensed or user-supplied prey mesh and apply the motion plan with `cat_prey_blender`.
5. Render a 10-15 second sample before committing to a long render.
6. For productions longer than 600 seconds, render independent seeded segments of at most 600 seconds and concatenate with `video_stitch`/FFmpeg.
7. Use `audio_mixer` only for subtle natural ambience or prey SFX. Narration, on-screen text, and music are off by default.

## Motion principles

For the mouse MVP, preserve a mixed hunt grammar:

- slow exploration;
- short pauses;
- brief fast sprints;
- hiding and peeking;
- edge exits;
- unpredictable re-entry.

Do not turn the path into a smooth screensaver loop. Preserve irregular timing and direction changes while keeping motion continuous enough to avoid visual flicker.

## Safety and viewing quality

- Do not add strobing, rapid full-frame flashes, or high-frequency brightness changes.
- Keep the prey large enough to remain trackable at the target viewing distance.
- Avoid frequent hard cuts; prefer one continuous environment or infrequent scene changes.
- Do not claim the generated motion is scientifically validated animal-behavior research.
- Keep prey assets and environmental assets license-traceable in the asset manifest.

## Review gate

Before a long render, inspect a 10-15 second sample at final frame rate and resolution. Verify ground contact, scale, visibility transitions, camera framing, motion variety, and absence of clipping. Long output must use the same approved seed/configuration unless a change is recorded deliberately.

## Current scope

`cat_prey_motion` v0.1 implements the mouse `mixed_hunt` profile. Other prey types should not be represented as supported until their motion grammars and tests are implemented.
