# -*- coding: utf-8 -*-
"""Generate BtDeck wordmark PNGs, favicon, and PWA icons."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = PROJECT_ROOT / "public"
BRAND_DIR = PUBLIC_DIR / "img" / "brand"
ICONS_DIR = PUBLIC_DIR / "img" / "icons"
MARK_PATH = BRAND_DIR / "btdeck-mark.png"
INVERSE_MARK_PATH = BRAND_DIR / "btdeck-mark-inverse.png"
MICRO_INVERSE_MARK_PATH = BRAND_DIR / "btdeck-mark-micro-inverse.png"
LOGO_PATH = BRAND_DIR / "btdeck-logo.png"
INVERSE_LOGO_PATH = BRAND_DIR / "btdeck-logo-inverse.png"

# PWA surfaces use the product emerald and a white mark so the icon remains
# legible without the old black board treatment.
ICON_BACKGROUND = (5, 150, 105, 255)
RESAMPLING = getattr(Image, "Resampling", Image).LANCZOS
WORDMARK_DARK = (31, 41, 55, 255)
WINDOWS_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
WORDMARK_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
)


def load_mark(path: Path = MARK_PATH) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(
            f"Brand mark not found: {path}. "
            "Add the matching SVG/PNG mark under frontend/public/img/brand first."
        )
    return Image.open(path).convert("RGBA")


def rounded_mask(size: int, radius_ratio: float = 0.18) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def load_wordmark_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in WORDMARK_FONT_CANDIDATES:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    raise FileNotFoundError(
        "No bold sans-serif font found for BtDeck wordmark PNG generation."
    )


def write_wordmark(mark_path: Path, output_path: Path, *, inverse: bool) -> None:
    width, height = 1050, 288
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mark = load_mark(mark_path).resize((288, 288), RESAMPLING)
    canvas.alpha_composite(mark, (0, 0))

    draw = ImageDraw.Draw(canvas)
    font = load_wordmark_font(204)
    origin = (312, height // 2)
    if inverse:
        draw.text(origin, "BtDeck", font=font, fill=(255, 255, 255, 255), anchor="lm")
    else:
        draw.text(origin, "Bt", font=font, fill=ICON_BACKGROUND, anchor="lm")
        deck_x = origin[0] + int(draw.textlength("Bt", font=font))
        draw.text((deck_x, origin[1]), "Deck", font=font, fill=WORDMARK_DARK, anchor="lm")

    canvas.save(output_path, format="PNG", optimize=True)
    print(f"wrote {output_path} ({width}x{height})")


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
    write_wordmark(MARK_PATH, LOGO_PATH, inverse=False)
    write_wordmark(INVERSE_MARK_PATH, INVERSE_LOGO_PATH, inverse=True)
    app_mark = load_mark(MICRO_INVERSE_MARK_PATH)

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
            app_mark,
            filename,
            size,
            maskable=maskable,
            mark_scale=mark_scale,
        )

    windows_icon = render_icon(app_mark, 256, maskable=False, mark_scale=0.70)
    windows_icon.save(
        PUBLIC_DIR / "favicon.ico",
        format="ICO",
        sizes=[(size, size) for size in WINDOWS_ICON_SIZES],
    )
    print(
        f"wrote {PUBLIC_DIR / 'favicon.ico'} "
        f"({'/'.join(str(size) for size in WINDOWS_ICON_SIZES)})"
    )


if __name__ == "__main__":
    main()
