# tif-to-avi

Convert multi-page TIFF stacks to MJPEG-in-AVI videos sized for PowerPoint
embedding.

For each input `.tif`:

1. Estimate a global 1%–99% percentile from a uniformly-spaced subset of
   pages — so brightness is consistent across all frames in the output and
   the video doesn't flicker between slices.
2. For each requested duration (seconds), pick evenly-spaced page indices
   with `np.linspace` so the motion covers the entire stack regardless of
   how many pages the source has.
3. Stream uint8 frames through `ffmpeg`'s stdin to encode MJPEG at quality
   `-q:v 5` inside an `.avi` container.

## Why MJPEG-in-AVI for slides

- MJPEG is intra-only — every frame is a keyframe. PowerPoint's timeline
  scrubber stays smooth instead of stalling on inter-frame predictions.
- AVI + MJPEG plays natively on modern Windows PowerPoint without
  third-party codecs.
- File sizes are tens of MB for typical short clips, fitting comfortably
  inside a `.pptx`.
- Trade-off: H.264-in-MP4 would be ~5–10× smaller, but PPT's scrubber on
  H.264 lags and some Office installations refuse certain MP4 profiles.
  MJPEG-in-AVI is the boring-but-bulletproof choice for slide videos.

## Requirements

- Python ≥ 3.9
- `numpy`, `tifffile`, `imageio-ffmpeg` (bundles the ffmpeg binary — no
  system install needed)

```bash
pip install numpy tifffile imageio-ffmpeg
```

## Usage

```bash
python tif_to_avi.py [--fps 30|60] <out_dir> <tif1> [<tif2> ...]
```

Produces, for every input TIFF, one `.avi` per duration in `DURATIONS_S`
(default `[5, 10, 15, 30]` seconds). Output filename pattern:

```
<input_stem>_<duration>s_<fps>fps.avi
```

Files from a 30 fps run and a 60 fps run co-exist in the same folder
without overwriting.

## Example file sizes

896×448 uint16 source, 2668 pages, MJPEG `-q:v 5`:

| duration | 30 fps | 60 fps |
| --- | --- | --- |
| 5s   | 3–4 MB   | 7–8 MB    |
| 10s  | 7–9 MB   | 14–17 MB  |
| 15s  | 10–13 MB | 21–25 MB  |
| 30s  | 21–25 MB | 41–51 MB  |

Lower `MJPEG_Q` to `7` or `10` to shrink output ~30–50% with mild quality
loss. To switch to H.264-in-MP4 entirely, change the ffmpeg flags in
`encode_one` to `-c:v libx264 -crf 23 -preset slow` and change the output
extension to `.mp4`.

## What the constants do

- `DURATIONS_S` — list of output durations (seconds). One AVI per entry per
  input TIFF.
- `MJPEG_Q` — ffmpeg `-q:v` for MJPEG (1 best, 31 worst). `5` is visually
  lossless for tomography-like content.
- `PERCENTILE_SAMPLE_N` — how many evenly-spaced pages to sample when
  estimating the per-source 1–99% percentile for normalization. Increase
  for very inhomogeneous stacks.
