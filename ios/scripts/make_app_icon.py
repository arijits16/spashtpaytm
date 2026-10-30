#!/usr/bin/env python3
"""Draw the Spasht app icon (build plan sections 5.1, phase 0).

A generic navy rounded square with a white "S". Deliberately generic: section
5.1 forbids using Paytm's official app icon or logo artwork, so the icon must be
recognisably *ours* and recognisably not theirs.

Written against the standard library only - no Pillow, no new dependency for a
file that changes roughly never. The PNG is committed, so a normal build never
runs this script; `make ios-icon` regenerates it.

The glyph is defined geometrically rather than with a font, so it renders
identically on any machine: an "S" is two stacked circular rings, each with a
slice removed, meeting at the centre.

    python3 ios/scripts/make_app_icon.py [--size 1024] [--out <path>]
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import zlib
from pathlib import Path

# Section 5.2 tokens.
NAVY = (0x00, 0x2E, 0x6E)
WHITE = (0xFF, 0xFF, 0xFF)

DEFAULT_SIZE = 1024
DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "SpashtPaytm"
    / "Resources"
    / "Assets.xcassets"
    / "AppIcon.appiconset"
    / "AppIcon.png"
)

# Supersampling factor per axis. 3 is the point where the diagonal edges of the
# "S" stop looking stepped at Home-screen size.
SAMPLES = 3


def _rounded_square_contains(x: float, y: float, size: float, radius: float) -> bool:
    """Is (x, y) inside a square of `size` with corner radius `radius`?

    The square fills the canvas; iOS applies its own superellipse mask on top, so
    this radius only matters in contexts that show the raw image (Spotlight,
    Settings, the App Store listing we will never have).
    """
    # Fold into the top-left quadrant: the shape is symmetric in both axes.
    dx = min(x, size - x)
    dy = min(y, size - y)
    if dx >= radius or dy >= radius:
        return 0 <= x <= size and 0 <= y <= size
    # Inside a corner box: the pixel must be within the corner circle.
    return (radius - dx) ** 2 + (radius - dy) ** 2 <= radius**2


def _angle_deg(dx: float, dy: float) -> float:
    """Angle in degrees, y pointing *down* (screen coordinates).

    Right is 0, down is +90, up is -90, left is 180.
    """
    return math.degrees(math.atan2(dy, dx))


def _in_ring(
    x: float,
    y: float,
    cx: float,
    cy: float,
    radius: float,
    half_stroke: float,
    gap: tuple[float, float],
) -> bool:
    """Is (x, y) on a circular ring, outside the angular `gap`?

    @param gap  (from, to) in degrees; angles strictly inside are the open part
                of the bowl - the gap is what makes a ring an "S" half rather
                than an "O".
    """
    dx, dy = x - cx, y - cy
    distance = math.hypot(dx, dy)
    if abs(distance - radius) > half_stroke:
        return False

    angle = _angle_deg(dx, dy)
    start, end = gap
    return not (start < angle < end)


def _s_glyph_contains(x: float, y: float, size: float) -> bool:
    """Is (x, y) inside the "S"?

    Two rings of radius R with centres R above and R below the middle, so the
    glyph is 4R tall and the bowls meet exactly at the centre point.
    """
    centre = size / 2
    radius = size * 0.1465  # 4R ~= 0.586 of the canvas: a comfortable optical size
    stroke = size * 0.0645
    half_stroke = stroke / 2

    # Upper bowl: open towards the lower right.
    if _in_ring(x, y, centre, centre - radius, radius, half_stroke, gap=(20.0, 90.0)):
        return True
    # Lower bowl: open towards the upper left (the mirror image).
    return _in_ring(x, y, centre, centre + radius, radius, half_stroke, gap=(-160.0, -90.0))


def render(size: int) -> bytearray:
    """Render the icon as raw RGB rows, anti-aliased by supersampling."""
    corner_radius = size * 0.2237  # close to the iOS superellipse, for raw views
    step = 1.0 / SAMPLES
    offset = step / 2
    total_samples = SAMPLES * SAMPLES

    pixels = bytearray(size * size * 3)
    sub_offsets = [offset + index * step for index in range(SAMPLES)]

    for row in range(size):
        row_base = row * size * 3
        ys = [row + dy for dy in sub_offsets]

        for column in range(size):
            xs = [column + dx for dx in sub_offsets]

            inside_square = 0
            inside_glyph = 0
            for y in ys:
                for x in xs:
                    if _rounded_square_contains(x, y, size, corner_radius):
                        inside_square += 1
                        if _s_glyph_contains(x, y, size):
                            inside_glyph += 1

            index = row_base + column * 3
            if inside_square == 0:
                # Outside the rounded square. Navy rather than transparent: iOS
                # app icons must be fully opaque or the App Store rejects them,
                # and a transparent corner shows black on the Home screen.
                pixels[index : index + 3] = bytes(NAVY)
                continue

            # Coverage-weighted blend of white over navy.
            glyph_coverage = inside_glyph / total_samples
            square_coverage = inside_square / total_samples
            for channel in range(3):
                navy_level = NAVY[channel] * square_coverage + NAVY[channel] * (
                    1 - square_coverage
                )
                value = navy_level * (1 - glyph_coverage) + WHITE[channel] * glyph_coverage
                pixels[index + channel] = int(round(value))

    return pixels


def write_png(path: Path, size: int, pixels: bytearray) -> None:
    """Write a minimal 8-bit RGB PNG. No Pillow needed."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    # Each scanline is prefixed with its filter byte (0 = none).
    raw = bytearray()
    stride = size * 3
    for row in range(size):
        raw.append(0)
        raw += pixels[row * stride : (row + 1) * stride]

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit, truecolour
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.size < 64:
        print("size must be at least 64", file=sys.stderr)
        return 2

    print(f"==> drawing a {args.size}x{args.size} icon ({SAMPLES}x{SAMPLES} supersampled)")
    pixels = render(args.size)
    write_png(args.out, args.size, pixels)
    print(f"    wrote {args.out} ({args.out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
