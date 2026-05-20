"""
Convert multi-page TIFFs to MJPEG-in-AVI for PPT embedding.

For each input .tif:
  - Compute a global 1-99% percentile from a uniformly-spaced subset of pages
    (so brightness is consistent within the resulting video, no flicker).
  - For each requested duration in seconds, pick evenly-spaced page indices
    (np.linspace) so the motion covers the whole stack at fps=30.
  - Stream uint8 frames through ffmpeg's stdin to encode MJPEG@quality=5 inside
    an .avi container.  MJPEG is intra-only => every frame is a keyframe
    (good for scrubbing inside PowerPoint).

Usage:
    python tif_to_avi.py [--fps N] <out_dir> <tif_path> [<tif_path> ...]
"""

import argparse
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import tifffile

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DURATIONS_S = [5, 10, 15, 30]
MJPEG_Q = 5            # ffmpeg -q:v scale (1=best, 31=worst)
PERCENTILE_SAMPLE_N = 30


def estimate_norm(tif_path):
    with tifffile.TiffFile(str(tif_path)) as tf:
        n = len(tf.pages)
        idxs = np.linspace(0, n - 1, min(PERCENTILE_SAMPLE_N, n)).round().astype(int)
        chunks = [tf.pages[int(i)].asarray().ravel() for i in idxs]
    pooled = np.concatenate(chunks)
    lo, hi = np.percentile(pooled, [1.0, 99.0])
    return float(lo), float(hi), n


def to_u8(arr, lo, hi):
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    a = (arr.astype(np.float32) - lo) / (hi - lo)
    a = np.clip(a, 0, 1) * 255.0
    return a.astype(np.uint8)


def encode_one(tif_path, duration_s, fps, lo, hi, n_pages, out_path):
    n_target = min(duration_s * fps, n_pages)
    idxs = np.linspace(0, n_pages - 1, n_target).round().astype(int)
    actual_fps = n_target / duration_s
    with tifffile.TiffFile(str(tif_path)) as tf:
        H, W = tf.pages[0].shape
        cmd = [
            FFMPEG, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{W}x{H}", "-pix_fmt", "gray",
            "-r", f"{actual_fps:.6f}",
            "-i", "-",
            "-c:v", "mjpeg",
            "-q:v", str(MJPEG_Q),
            "-pix_fmt", "yuvj420p",
            str(out_path),
        ]
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            for i in idxs:
                page = tf.pages[int(i)].asarray()
                u8 = to_u8(page, lo, hi)
                proc.stdin.write(u8.tobytes())
            proc.stdin.close()
            _, err = proc.communicate(timeout=300)
        except Exception:
            proc.kill()
            raise
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exit {proc.returncode}: "
                f"{err.decode('utf-8', errors='replace')[-500:]}"
            )
    return len(idxs), actual_fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30,
                    help="Target frame rate (default 30)")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("tifs", nargs="+", type=Path)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[setup] ffmpeg: {FFMPEG}")
    print(f"[setup] out_dir: {out_dir}")
    print(f"[setup] {len(args.tifs)} input files, durations={DURATIONS_S}s, "
          f"fps={args.fps}, codec=mjpeg, q={MJPEG_Q}")
    print()

    rows = []
    for tif in args.tifs:
        print(f"=== {tif.name} ===")
        lo, hi, n = estimate_norm(tif)
        print(f"  norm lo={lo:.1f} hi={hi:.1f} pages={n}")
        for d in DURATIONS_S:
            out = out_dir / f"{tif.stem}_{d}s_{args.fps}fps.avi"
            n_frames, actual_fps = encode_one(tif, d, args.fps, lo, hi, n, out)
            size_mb = out.stat().st_size / (1024 * 1024)
            print(f"  -> {out.name}  "
                  f"frames={n_frames}  fps={actual_fps:.2f}  size={size_mb:.1f}MB")
            rows.append((tif.name, d, n_frames, actual_fps, size_mb,
                         str(out)))
        print()

    print("--- summary ---")
    print(f"{'source':50s}  {'dur':>4s}  {'frames':>7s}  {'fps':>6s}  {'MB':>6s}")
    for src, d, nf, fp, mb, _ in rows:
        print(f"{src:50s}  {d:4d}  {nf:7d}  {fp:6.2f}  {mb:6.1f}")


if __name__ == "__main__":
    main()
