#!/usr/bin/env python3
"""Compare two renders for a speed-vs-fidelity trade: PSNR, SSIM, pixel deltas, optional strip.

Run it with the ComfyUI venv python (needs cv2 + scipy, no scikit-image there):

    /mnt/data2/ComfyUI/.venv/bin/python image_fidelity_ab.py baseline.png variant.png \
        [--strip /path/out.png] [--labels A B]

Two ways to use it as a check on the harness itself:

  * pass the same file twice -> expect an identical-pixels verdict;
  * pass two renders of the SAME config -> expect max diff 0 (PNG bytes differ only because
    metadata is embedded, so never compare file hashes for determinism).
"""

import argparse
import sys

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter


def ssim_gray(a, b, sigma=1.5):
    """Mean SSIM over grey channel, Gaussian window (no scikit-image dependency)."""
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float64)
    b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a, mu_b = gaussian_filter(a, sigma), gaussian_filter(b, sigma)
    sa = gaussian_filter(a * a, sigma) - mu_a ** 2
    sb = gaussian_filter(b * b, sigma) - mu_b ** 2
    sab = gaussian_filter(a * b, sigma) - mu_a * mu_b
    return float((((2 * mu_a * mu_b + c1) * (2 * sab + c2)) /
                  ((mu_a ** 2 + mu_b ** 2 + c1) * (sa + sb + c2))).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("variant")
    ap.add_argument("--strip", help="write an A | B | 6x amplified diff strip here")
    ap.add_argument("--labels", nargs=2, default=["baseline", "variant"])
    args = ap.parse_args()

    a = cv2.imread(args.baseline, cv2.IMREAD_COLOR)
    b = cv2.imread(args.variant, cv2.IMREAD_COLOR)
    if a is None or b is None:
        sys.exit(f"could not read {args.baseline if a is None else args.variant}")
    if a.shape != b.shape:
        sys.exit(f"shape mismatch: {a.shape} vs {b.shape}")

    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    identical = bool(np.array_equal(a, b))
    print(f"{args.labels[0]} {a.shape} mean {a.mean():.1f} std {a.std():.1f}")
    print(f"{args.labels[1]} {b.shape} mean {b.mean():.1f} std {b.std():.1f}")
    if identical:
        print("identical pixels: True (max abs diff 0)")
        return
    print(f"PSNR        : {cv2.PSNR(a, b):.2f} dB")
    print(f"SSIM        : {ssim_gray(a, b):.4f}")
    print(f"mean |diff| : {d.mean():.3f} / 255   p99: {np.percentile(d, 99):.0f}   max: {d.max()}")
    over8 = (d.max(axis=2) > 8).mean() * 100
    over16 = (d.max(axis=2) > 16).mean() * 100
    print(f"pixels over 8/255: {over8:.2f}%   over 16/255: {over16:.2f}%")
    print("reading: PSNR > 39 dB, SSIM > 0.98, ~2% over 8/255 = texture-level noise, not a different image")

    if args.strip:
        diff = cv2.cvtColor(np.clip(d.max(axis=2) * 6, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        strip = np.hstack([a, b, diff])
        h, w = strip.shape[:2]
        cv2.imwrite(args.strip, cv2.resize(strip, (w // max(1, round(h / 850)), h // max(1, round(h / 850))),
                                          interpolation=cv2.INTER_AREA))
        print(f"strip written: {args.strip} (left {args.labels[0]} | middle {args.labels[1]} | right 6x diff)")


if __name__ == "__main__":
    main()
