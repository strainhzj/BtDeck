# -*- coding: utf-8 -*-
"""生成 BtDeck PWA 品牌图标（v1.0.6 移动独有优化）。

品牌参数与前端主题同源：--color-primary #059669（theme-variables.scss），
白色 "BT" 字样（与 public/img/icons/favicon.svg 构图一致）。

产物（写入 public/img/icons/）：
- android-chrome-192x192.png / android-chrome-512x512.png（manifest 常规图标）
- android-chrome-maskable-512x512.png（maskable：全出血背景，内容收进 80% 安全区）
- apple-touch-icon-152x152.png / apple-touch-icon-180x180.png（iOS 主屏，全出血）
- favicon-16x16.png / favicon-32x32.png
- msapplication-icon-144x144.png / mstile-150x150.png

用法：python scripts/generate-pwa-icons.py（在 frontend/ 目录下执行）
"""
import os

from PIL import Image, ImageDraw, ImageFont

BRAND_COLOR = (5, 150, 105)  # #059669
TEXT_COLOR = (255, 255, 255)
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "img", "icons")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def draw_icon(size: int, maskable: bool, corner_ratio: float = 0.18) -> Image.Image:
    """画一枚图标：圆角实底 + 居中 BT 字样。

    maskable 需全出血背景（系统裁切任意形状），文字缩至 56% 落在安全区内；
    常规图标圆角 18%，文字 60%。
    """
    image = Image.new("RGBA", (size, size), BRAND_COLOR + (255,))
    draw = ImageDraw.Draw(image)

    if not maskable:
        # 圆角遮罩：先画到临时图层再贴回，得到透明圆角
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        radius = int(size * corner_ratio)
        mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
        rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        rounded.paste(image, (0, 0), mask)
        image = rounded
        draw = ImageDraw.Draw(image)

    text_ratio = 0.56 if maskable else 0.60
    font = load_font(int(size * text_ratio))
    text = "BT"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = right - left, bottom - top
    position = ((size - text_width) / 2 - left, (size - text_height) / 2 - top)
    draw.text(position, text, font=font, fill=TEXT_COLOR + (255,))
    return image


def main() -> None:
    targets = [
        ("android-chrome-192x192.png", 192, False),
        ("android-chrome-512x512.png", 512, False),
        ("android-chrome-maskable-512x512.png", 512, True),
        ("apple-touch-icon-152x152.png", 152, True),
        ("apple-touch-icon-180x180.png", 180, True),
        ("favicon-16x16.png", 16, False),
        ("favicon-32x32.png", 32, False),
        ("msapplication-icon-144x144.png", 144, True),
        ("mstile-150x150.png", 150, True),
    ]
    os.makedirs(ICONS_DIR, exist_ok=True)
    for filename, size, maskable in targets:
        path = os.path.join(ICONS_DIR, filename)
        draw_icon(size, maskable).save(path)
        print(f"wrote {path} ({size}x{size}{', maskable' if maskable else ''})")


if __name__ == "__main__":
    main()
