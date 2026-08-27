# Cat TV rendering with GitHub Actions

Cat TV renders can run on Linux with Blender in background/headless mode. The repository ships a manual GitHub Actions workflow at `.github/workflows/cat-tv-render.yml`.

## Runner profiles

### `ubuntu-24.04`

Use the GitHub-hosted runner for final-resolution previews and short validation renders. The workflow downloads and checksum-verifies Blender 5.2.1, starts a software X display, installs FFmpeg, pulls Git LFS assets, runs the Cat TV tests, renders the requested program, encodes MP4, and removes generated render workspaces after success.

Hosted renders are deliberately limited to:

- total duration: <= 60 seconds
- Blender segment size: <= 20 seconds

The limits protect GitHub-hosted ephemeral disk and execution time. They are intended for visual A/B tests, not two-hour production masters.

### `cat-tv-linux`

Use a self-hosted Linux runner with the custom label `cat-tv-linux` for long production renders. Recommended host characteristics:

- Ubuntu 22.04+ or another GitHub-supported Linux distribution
- recent x64 CPU
- 32 GB RAM or more
- a supported discrete GPU where possible
- fast local SSD/NVMe sized for at least one uncompressed PNG render segment
- FFmpeg and Git LFS installed

Blender itself may already be installed on the runner. If `BLENDER_PATH` is not configured and `blender` is not on `PATH`, the workflow downloads the official Blender 5.2.1 Linux x64 binary.

## 3D assets

Cat TV GLB files are tracked with Git LFS:

```text
assets/cat-tv/**/*.glb
```

The current Mouse Hunt workflow expects:

```text
assets/cat-tv/prey/mouse.glb
assets/cat-tv/world/pine_needle_forest_floor.glb
assets/cat-tv/world/rocky_forest_floor_texture.glb
assets/cat-tv/world/forest_floor.glb
```

The Hercules beetle model can remain in the same asset tree but is not used until a dedicated beetle behavior grammar exists.

Do not add a third-party model until its source URL, author, and license have been recorded. The source binary and attribution requirements are independent: Git LFS solves repository transport, not licensing.

## Frame lifecycle

PNG sequences are transient production data.

During a multi-segment render the workflow watches for a completed `segment.json`. That marker is written only after the segment has been rendered, encoded, mechanically validated, and sampled for QA. Once the marker exists, the workflow deletes that segment's `frames/` and `qa/` directories while later segments continue rendering.

After the complete program succeeds:

1. the final master MP4 is copied to runner temporary storage;
2. the full project workspace is deleted, including PNGs, `.blend` files, reports, QA JPEGs, and intermediate segment MP4s;
3. only the final MP4 is uploaded as a GitHub Actions artifact.

This keeps Actions storage focused on delivery files rather than regenerable frames.

## Manual runs

Once the workflow exists on the repository default branch, open **Actions -> Cat TV Render -> Run workflow** and choose:

- runner: `ubuntu-24.04` or `cat-tv-linux`
- duration: e.g. `12s`, `60s`, `30m`, `2h`
- segment size in seconds
- world: `pine`, `rocky`, or `forest`
- final MP4 artifact retention period

While the Cat TV work is still only on `feature/cat-tv-mvp`, pushing a GLB under `assets/cat-tv/` triggers one automatic 12-second Pine preview on `ubuntu-24.04`. This allows the workflow to be exercised before the feature branch is merged.

## Suggested production settings

Preview:

```text
runner: ubuntu-24.04
duration: 12s
segment_seconds: 12
world: pine
```

Long-form production on a suitably provisioned self-hosted runner:

```text
runner: cat-tv-linux
duration: 2h
segment_seconds: 60-300
world: the approved A/B winner
```

Use shorter segments when render-frame disk usage is the limiting factor. Completed segment frames are deleted automatically, so peak disk usage is approximately one active segment rather than the complete program.
