# Cat TV Production

Use this Layer 2 skill for long-form videos whose primary audience is a cat watching a display. The default production route is deterministic procedural prey motion rendered in a real 3D scene, not repeated AI-generated clips.

For the CatFactory content system, Cat TV Lab is one of the core content pillars alongside personality-led Ninoosh & Liam videos and interactive/human-facing stories. The continuous Cat TV stimulus should therefore optimize first for feline trackability and viewing comfort; channel branding, narration, captions, and human-facing story devices belong outside the core stimulus unless explicitly approved.

## Production route

1. Use the `cat-tv` pipeline.
2. Generate a renderer-neutral motion plan with `cat_prey_motion` and preserve its seed.
3. Build the base environment with `blender_world`. Keep the camera fixed or very stable unless the user explicitly requests camera motion.
4. Run `cat_tv_world_polish` once per environment/world chapter. Preserve this polished `.blend` across every prey segment so terrain, litter, lighting, and framing do not jump between segment seeds.
5. Import a licensed or user-supplied prey mesh and apply the motion plan with `cat_prey_blender`.
6. Render a 10-15 second final-resolution sample before committing to a long render.
7. For productions longer than 600 seconds, prefer 120-300 second independent prey segments with distinct recorded motion seeds. Keep the environment seed fixed, render resumable PNG sequences, encode approved segments, and concatenate with `video_stitch`/FFmpeg.
8. Use `frame_sampler` and `visual_qa` on samples, representative segment frames, and the final master. Verify joins as well as beginning/middle/end frames.
9. Use `audio_mixer` or a delivery mux only for subtle natural ambience or prey SFX. Narration, on-screen text, and music are off by default.
10. Retain a high-quality master and derive YouTube/delivery encodes from that master rather than treating a low-bitrate upload file as the archive.

`scripts/cat_tv_longform.py` implements the local resumable production route for multi-segment Mouse Hunt output.

## Motion principles

For the mouse profile, preserve a mixed hunt grammar:

- slow exploration;
- short pauses;
- brief fast sprints;
- hiding and peeking;
- edge exits;
- unpredictable re-entry.

Do not turn the path into a smooth screensaver loop. Preserve irregular timing and direction changes while keeping motion continuous enough to avoid visual flicker. A prey-motion seed should vary by long-form segment; the world/environment seed should not.

Micro-motion may add subtle body bob, pitch, and roll to reduce the impression of a rigid mesh sliding across the ground. It must not create excessive bouncing or break ground contact.

## Environment principles

- Keep prey/background contrast high enough that the prey remains trackable at television viewing distance.
- Avoid a visible terrain boundary, horizon break, or dark backdrop strip.
- Prefer low-frequency organic ground variation over large circular color patches or uniform flat color.
- Forest-floor detail should use small, irregular, clustered litter rather than evenly spaced decorative primitives.
- Background detail must remain subordinate to the prey and should not create high-frequency visual noise.
- Reuse the same polished environment across adjoining prey segments.

## Long-form composition

Treat a 30-minute, one-hour, or two-hour program as a production made of recoverable master segments, not one enormous Blender process and not one short repeated loop.

A typical two-hour Mouse Hunt is 24 five-minute segments. Each segment has its own motion JSON, editable prey `.blend`, resumable PNG sequence, QA frames, and high-quality intermediate encode. `video_stitch` validates matching resolution/fps/codec before a cut-only concat. Cuts are preferable to crossfades because crossfades can briefly create ghost prey. Where practical, joins should land on hidden prey, edge exits, or calm holds.

A production manifest should retain for every segment:

- segment id;
- duration;
- motion seed;
- environment/world version and fixed environment seed;
- prey asset and license/source;
- motion plan path;
- blend path;
- PNG frame range;
- encoded segment path;
- QA result.

## QA route

Before long rendering:

- inspect the 10-15 second sample at final resolution and frame rate;
- verify ground contact, prey scale, contrast, body motion, visibility transitions, framing, environment stability, and terrain-edge absence.

During and after long production:

- ensure the expected final PNG exists for every segment;
- mechanically validate each encoded segment with `visual_qa`/ffprobe;
- use `frame_sampler` to extract representative beginning/middle/end frames;
- inspect every segment join for prey/background discontinuity;
- verify there are no strobing events, terrain-edge exposures, broken hides/re-entries, clipping, or obvious repeated short loops;
- run final probe validation after stitching and audio muxing.

## Audio

The default Cat TV Lab sound policy is no narration, no spoken branding, and no music. When sound is used, prefer low-level continuous natural ambience plus rare subtle prey/environment cues. Avoid repetitive short ambience loops that audibly reset at every video segment. `audio_mixer` can be used for layered ambience/SFX preparation; final muxing should preserve video quality.

## Optional OpenMontage augmentation

OpenMontage also provides reference analysis, stock-footage search, local/cloud generative-video providers, Remotion/HyperFrames composition, audio tools, and post-production QA. For Cat TV, these should augment rather than replace the deterministic Blender prey layer. Good optional uses include:

- analyzing successful Cat TV references for prey size, pacing, camera policy, and scene density;
- sourcing or generating distant environment plates or licensed assets;
- creating short branded intros/outros for human viewers;
- preparing thumbnails and promotional derivatives;
- creating vertical/social versions and reaction/behind-the-scenes clips around the core Cat TV footage.

Do not use short generative-video clips as the repeated core of a long Cat TV program when deterministic prey trajectory and continuity are required.

## Safety and viewing quality

- Do not add strobing, rapid full-frame flashes, or high-frequency brightness changes.
- Keep the prey large enough to remain trackable at the target viewing distance.
- Avoid frequent hard editorial cuts; prefer one continuous environment or infrequent safe scene changes.
- Do not claim the generated motion is scientifically validated animal-behavior research.
- Keep prey assets and environmental assets license-traceable in the asset manifest.

## Current scope

`cat_prey_motion` currently implements the mouse `mixed_hunt` profile. Other prey types should not be represented as supported until their motion grammars and tests are implemented. Bird, butterfly, fly/insect, gecko, and fish should become separate tested behavior grammars rather than aliases of mouse motion.
