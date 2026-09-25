"""程序图标。

用 Pillow 直接绘制，不依赖任何二进制资源文件 —— 这样仓库里不会多出
一个「谁也说不清怎么改」的 .ico，而且打包脚本可以随时重新生成。

图标同时被两处使用：
* GUI 运行时：``QIcon(pil_to_qpixmap(render_icon(256)))``
* 打包时：``ensure_ico()`` 生成多尺寸 .ico 交给 PyInstaller
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND = (37, 99, 235, 255)  # #2563eb
PAPER = (255, 255, 255, 255)
FOLD = (219, 231, 253, 255)

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

_FONT_CANDIDATES = (
    "segoeuib.ttf",
    "arialbd.ttf",
    "msyhbd.ttc",
    "msyh.ttc",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 老版本 Pillow 不支持 size 参数
        return ImageFont.load_default()


def render_icon(size: int = 256) -> Image.Image:
    """绘制一张 ``size × size`` 的图标（RGBA）。"""
    scale = 8  # 先放大再缩小，得到抗锯齿的圆角与边缘
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    unit = size * scale

    draw.rounded_rectangle(
        (0, 0, unit - 1, unit - 1),
        radius=int(unit * 0.22),
        fill=BRAND,
    )

    # 一张白色纸张，右上角折角
    margin = unit * 0.20
    paper = (margin, margin * 1.05, unit - margin, unit - margin * 0.95)
    fold = (paper[2] - paper[0]) * 0.34
    radius = unit * 0.035

    draw.rounded_rectangle(paper, radius=radius, fill=PAPER)
    draw.polygon(
        [
            (paper[2] - fold, paper[1]),
            (paper[2], paper[1] + fold),
            (paper[2] - fold, paper[1] + fold),
        ],
        fill=FOLD,
    )

    # 纸张上的文字
    font_size = int(unit * 0.145)
    font = _load_font(font_size)
    text = "PDF"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = right - left, bottom - top
    center_x = (paper[0] + paper[2]) / 2
    center_y = paper[1] + (paper[3] - paper[1]) * 0.60
    draw.text(
        (center_x - text_width / 2 - left, center_y - text_height / 2 - top),
        text,
        font=font,
        fill=BRAND,
    )

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def ensure_ico(path: str | Path) -> Path:
    """生成多尺寸 .ico 文件，已存在且比脚本新则直接复用。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    base = render_icon(256)
    base.save(target, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    return target
