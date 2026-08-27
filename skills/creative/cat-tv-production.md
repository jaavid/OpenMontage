# Cat TV Production

Use this Layer 2 skill for long-form videos whose primary audience is a cat watching a display. The default production route is deterministic procedural prey motion rendered in a real 3D scene, not repeated AI-generated clips.

## Production route

1. Use the `cat-tv` pipeline.
2. Generate a renderer-neutral motion plan with `cat_prey_motion` and preserve its seed.
3. Build the reusable environment with `blender_world`. Keep the camera fixed or very stable unless the user explicitly requests camera motion.
4. Import a licensed or user-supplied prey mesh and apply the motion plan with `cat_prey_blender`.
5. Render a 10-15 second sample at the final resolution and frame rate before committing to long-form output.
6. Render production footage as PNG image sequences with resume enabled. If rendering is interrupted, continue from the first missing frame rather than restarting completed work.
7. Keep each motion plan at or below 600 seconds. For local production, prefer 120-300 second segments when practical because shorter segments are easier to recover, review, and replace.
8. Give every long-form segment an explicit seed and avoid repeating one short loop. Segment joins should occur on safe beats such as edge exits, hidden prey, or calm holds.
9. Encode reviewed segments to a high-quality intermediate and concatenate with `video_stitch`/FFmpeg. Normalize frame size and frame rate before stitching if necessary.
10. Use `audio_mixer` only for subtle natural ambience or prey SFX. Narration, on-screen text, and music are off by default.
11. Run representative-frame and composition QA before final delivery.

## Motion principles

For the mouse MVP, preserve a mixed hunt grammar:

- slow exploration;
- short pauses;
- brief fast sprints;
- hiding and peeking;
- edge exits;
- unpredictable re-entry.

Do not turn the path into a smooth screensaver loop. Preserve irregular timing and direction changes while keeping motion continuous enough to avoid visual flicker.

Micro-motion may add subtle body bob, pitch, and roll to reduce the impression of a rigid mesh sliding across the ground. It must not create excessive bouncing or break ground contact.

## Environment principles

- Keep the prey silhouette easy to distinguish from the background.
- Prefer a large continuous terrain so the camera never reveals an artificial world edge.
- Organic detail should be irregular and sparse enough to preserve prey readability.
- Procedural leaf litter, twigs, stones, and similar low-cost detail are preferable to large circular color patches.
- Avoid decoration directly on the prey path when it would visually obstruct the target.

## Long-form master strategy

Treat a one- or two-hour Cat TV video as a master project made from independently reproducible render segments, not one monolithic Blender invocation.

A production manifest should retain for every segment:

- segment id;
- duration;
- seed;
- environment/world version;
- prey asset and license/source;
- motion plan path;
- blend path;
- PNG frame range;
- encoded segment path;
- QA result.

For a two-hour program, a practical local starting point is 24 x 5-minute segments. The hard motion-plan limit is 10 minutes per segment, but smaller chunks reduce the cost of rerendering failures or replacing weak sections.

Keep a high-quality master separate from the delivery encode. Use the final platform-specific H.264/H.265 encode only after segment QA and stitching are complete.

## QA route

Before long rendering:

- inspect the 10-15 second sample;
- verify ground contact, prey scale, contrast, body motion, visibility transitions, framing, and environment detail.

During and after long production:

- ensure the expected final PNG exists for every segment;
- use `frame_sampler` to inspect representative frames;
- use `visual_qa` for visual artifact review where available;
- use `composition_validator`/ffprobe for duration, resolution, frame-rate, and stream validation;
- inspect the beginning, middle, end, and every segment join;
- verify there are no strobing events, terrain-edge exposures, broken hides/re-entries, clipping, or obvious repeated short loops.

## Audio route

Cat TV does not require narration or music. If audio is used, prefer a continuous low-level natural ambience bed with occasional subtle prey-appropriate SFX. `audio_mixer` can mix, fade, normalize, and layer ambience/SFX. Keep joins inaudible and avoid abrupt loud events.

## Optional OpenMontage augmentation

OpenMontage also provides stock-footage search, local/cloud generative-video providers, Remotion/HyperFrames composition, and other post-production tools. For Cat TV, these should augment rather than replace the deterministic Blender prey layer. Good optional uses include:

- generating or sourcing distant environment plates;
- creating short branded intros/outros for human viewers;
- preparing thumbnails or promotional derivatives;
- creating alternate vertical/social versions with auto-reframing;
- producing reaction/behind-the-scenes clips around the core Cat TV footage.

Do not use short generative-video clips as the repeated core of a long Cat TV program when deterministic prey trajectory and continuity are required.

## Safety and viewing quality

- Do not add strobing, rapid full-frame flashes, or high-frequency brightness changes.
- Keep the prey large enough to remain trackable at the target viewing distance.
- Avoid frequent hard editorial cuts; prefer one continuous environment or infrequent safe scene changes.
- Do not claim the generated motion is scientifically validated animal-behavior research.
- Keep prey assets and environmental assets license-traceable in the asset manifest.

## Current scope

`cat_prey_motion` currently implements the mouse `mixed_hunt` profile. Other prey types should not be represented as supported until their motion grammars and tests are implemented.
