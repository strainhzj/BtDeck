# -*- coding: utf-8 -*-
"""Generate BtDeck favicon and PWA icons from the project brand mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = PROJECT_ROOT / "public"
BRAND_DIR = PUBLIC_DIR / "img" / "brand"
ICONS_DIR = PUBLIC_DIR / "img" / "icons"
MARK_PATH = BRAND_DIR / "btdeck-mark.png"

# The navy deck color keeps the green orbit visible at small sizes and matches
# the dark surface used by the supplied logo.
ICON_BACKGROUND = (24, 38, 52, 255)
RESAMPLING = getattr(Image, "Resampling", Image).LANCZOS


def load_mark() -> Image.Image:
    if not MARK_PATH.exists():
        raise FileNotFoundError(
            f"Brand mark not found: {MARK_PATH}. "
            "Add frontend/public/img/brand/btdeck-mark.png first."
        )
    return Image.open(MARK_PATH).convert("RGBA")


def rounded_mask(size: int, radius_ratio: float = 0.18) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def render_icon(
    mark: Image.Image,
    size: int,
    *,
    maskable: bool,
    mark_scale: float,
) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), ICON_BACKGROUND)
    max_dimension = max(1, int(size * mark_scale))
    scale = min(max_dimension / mark.width, max_dimension / mark.height)
    mark_size = (
        max(1, int(mark.width * scale)),
        max(1, int(mark.height * scale)),
    )
    resized_mark = mark.resize(mark_size, RESAMPLING)
    position = (
        (size - resized_mark.width) // 2,
        (size - resized_mark.height) // 2,
    )
    canvas.alpha_composite(resized_mark, position)

    if not maskable:
        rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        rounded.paste(canvas, (0, 0), rounded_mask(size))
        canvas = rounded
    return canvas


def write_icon(
    mark: Image.Image,
    filename: str,
    size: int,
    *,
    maskable: bool,
    mark_scale: float,
) -> None:
    path = ICONS_DIR / filename
    render_icon(
        mark,
        size,
        maskable=maskable,
        mark_scale=mark_scale,
    ).save(path, format="PNG", optimize=True)
    print(f"wrote {path} ({size}x{size})")


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    mark = load_mark()

    targets = [
        ("android-chrome-192x192.png", 192, False, 0.62),
        ("android-chrome-512x512.png", 512, False, 0.62),
        ("android-chrome-maskable-512x512.png", 512, True, 0.56),
        ("apple-touch-icon.png", 180, True, 0.56),
        ("apple-touch-icon-60x60.png", 60, True, 0.56),
        ("apple-touch-icon-76x76.png", 76, True, 0.56),
        ("apple-touch-icon-120x120.png", 120, True, 0.56),
        ("apple-touch-icon-152x152.png", 152, True, 0.56),
        ("apple-touch-icon-180x180.png", 180, True, 0.56),
        ("favicon-16x16.png", 16, False, 0.70),
        ("favicon-32x32.png", 32, False, 0.70),
        ("msapplication-icon-144x144.png", 144, True, 0.56),
        ("mstile-150x150.png", 150, True, 0.56),
    ]

    for filename, size, maskable, mark_scale in targets:
        write_icon(
            mark,
            filename,
            size,
            maskable=maskable,
            mark_scale=mark_scale,
        )

    favicon = render_icon(mark, 48, maskable=False, mark_scale=0.70)
    favicon.save(
        PUBLIC_DIR / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print(f"wrote {PUBLIC_DIR / 'favicon.ico'} (16/32/48)")


if __name__ == "__main__":
    main()
