#!/usr/bin/env python3
"""品牌图标生成器：从 btdeck-mark 几何生成各打包形态的位图图标。

源头是 frontend/public/img/brand/btdeck-mark.svg（viewBox 64x64）：
绿色 D 形轨道 + 三条深色甲板线 + 连接节点。本脚本按同一几何在
"品牌绿底 + 白色单色标志" 风格下（2026-09-11 确认）光栅化为：

  1. Android 传统启动图标（API 24-25 回退；API 26+ 走 mipmap-anydpi-v26
     自适应矢量，不经本脚本）：
       android/app/src/main/res/mipmap-{mdpi..xxxhdpi}/ic_launcher.png      48/72/96/144/192
       android/app/src/main/res/mipmap-{mdpi..xxxhdpi}/ic_launcher_round.png（圆形裁切）
  2. Linux DEB/RPM hicolor 桌面图标（build-linux.sh 装入 /usr/share/icons）：
       deploy/icons/hicolor/{48x48,64x64,128x128,256x256}/apps/btdeck.png

用法（仅重新生成时需要；产物已入库，常规构建不依赖 Pillow）：
    python tools/generate_brand_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent

BRAND_GREEN = (5, 150, 105, 255)  # #059669，与前端主题色一致
WHITE = (255, 255, 255, 255)

# ---- btdeck-mark.svg 几何常量（viewBox 64x64，修改品牌标志时同步更新）----
ARC_CENTER = (28.0, 32.0)  # D 形轨道圆心
ARC_RADIUS = 18.0          # D 形轨道半径（右侧半圆，-90°..90°）
ARC_STROKE = 6.5           # 轨道描边宽
DECK_LINES = ((12, 34, 24), (12, 39, 32), (12, 34, 40))  # (x1, x2, y)
LINE_STROKE = 5.0          # 甲板线描边宽
NODE_CENTER = (46.0, 32.0)
NODE_RADIUS = 5.5
# 内容包围盒（含描边/线帽外延）：x 6.75..51.5，y 10.75..53.25
CONTENT_CENTER = (29.125, 32.0)
CONTENT_WIDTH = 44.75

# Android mipmap 密度 → 像素
ANDROID_DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
# hicolor 图标尺寸（另由 deploy/icons/btdeck.svg 提供 scalable 矢量）
HICOLOR_SIZES = (48, 64, 128, 256)

SS = 8  # 超采样倍数（抗锯齿）


def _draw_mark(draw: ImageDraw.ImageDraw, scale: float, cx: float, cy: float) -> None:
    """按 64 空间几何绘制白色单标志，内容包围盒中心对齐到 (cx, cy)。

    弧线以参数化折线绘制而非 PIL arc：PIL arc 的描边不一定居中于路径，
    折线 + 圆帽可保证与 SVG stroke 居中语义一致。
    """

    def pt(x: float, y: float) -> tuple[float, float]:
        return (cx + scale * (x - CONTENT_CENTER[0]), cy + scale * (y - CONTENT_CENTER[1]))

    def dot(center: tuple[float, float], r: float) -> None:
        x, y = center
        draw.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)

    # D 形轨道（右侧半圆，圆帽收端）
    arc_w = ARC_STROKE * scale
    steps = 96
    points = [
        pt(
            ARC_CENTER[0] + ARC_RADIUS * math.cos(math.radians(-90 + 180 * i / steps)),
            ARC_CENTER[1] + ARC_RADIUS * math.sin(math.radians(-90 + 180 * i / steps)),
        )
        for i in range(steps + 1)
    ]
    draw.line(points, fill=WHITE, width=max(1, round(arc_w)), joint="curve")
    cap_r = ARC_STROKE * scale / 2
    for x, y in ((10, 14), (28, 14), (28, 50), (10, 50)):
        dot(pt(x, y), cap_r)

    # 三条甲板线（圆帽收端）
    line_w = max(1, round(LINE_STROKE * scale))
    line_cap_r = LINE_STROKE * scale / 2
    for x1, x2, y in DECK_LINES:
        a, b = pt(x1, y), pt(x2, y)
        draw.line([a, b], fill=WHITE, width=line_w)
        dot(a, line_cap_r)
        dot(b, line_cap_r)

    # 连接节点
    dot(pt(*NODE_CENTER), NODE_RADIUS * scale)


def render_tile(size: int, shape: str = "square", mark_ratio: float = 0.58) -> Image.Image:
    """渲染单枚图标：圆角方形（或圆形）绿底 + 居中白色标志。"""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if shape == "round":
        draw.ellipse([0, 0, big - 1, big - 1], fill=BRAND_GREEN)
    else:
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=round(big * 0.22), fill=BRAND_GREEN)
    _draw_mark(draw, scale=mark_ratio * big / CONTENT_WIDTH, cx=big / 2, cy=big / 2)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    outputs: list[Path] = []

    res_dir = REPO_ROOT / "android" / "app" / "src" / "main" / "res"
    for density, px in ANDROID_DENSITIES.items():
        mipmap = res_dir / f"mipmap-{density}"
        mipmap.mkdir(parents=True, exist_ok=True)
        square = mipmap / "ic_launcher.png"
        round_ = mipmap / "ic_launcher_round.png"
        render_tile(px, "square", 0.58).save(square)
        # 圆形模板裁切更狠，标志略收
        render_tile(px, "round", 0.52).save(round_)
        outputs += [square, round_]

    icons_dir = REPO_ROOT / "deploy" / "icons"
    for px in HICOLOR_SIZES:
        target = icons_dir / "hicolor" / f"{px}x{px}" / "apps"
        target.mkdir(parents=True, exist_ok=True)
        png = target / "btdeck.png"
        render_tile(px, "square", 0.58).save(png)
        outputs.append(png)

    for path in outputs:
        print(f"[OK] {path.relative_to(REPO_ROOT)} ({path.stat().st_size} bytes)")
    print(f"\n共生成 {len(outputs)} 枚图标（风格：#059669 底 + 白色 btdeck-mark）")


if __name__ == "__main__":
    main()
