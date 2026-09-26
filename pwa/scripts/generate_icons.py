from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "public" / "icons"
BACKGROUND = "#08111f"
PANEL = "#0e1b2d"
ACCENT = "#32d7cc"


def draw_icon(size: int, *, maskable: bool = False) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    image = Image.new("RGB", (canvas_size, canvas_size), BACKGROUND)
    draw = ImageDraw.Draw(image)

    margin = int(canvas_size * (0.16 if maskable else 0.09))
    radius = int(canvas_size * 0.18)
    draw.rounded_rectangle(
        (margin, margin, canvas_size - margin, canvas_size - margin),
        radius=radius,
        fill=PANEL,
        outline=ACCENT,
        width=max(4, int(canvas_size * 0.018)),
    )

    mark_margin = int(canvas_size * (0.27 if maskable else 0.22))
    mark_size = canvas_size - (mark_margin * 2)
    cell = mark_size // 7
    stroke = max(4, int(cell * 0.26))

    def finder(col: int, row: int) -> None:
        x = mark_margin + (col * cell)
        y = mark_margin + (row * cell)
        box = (x, y, x + (cell * 2), y + (cell * 2))
        draw.rounded_rectangle(box, radius=stroke, outline=ACCENT, width=stroke)

    finder(0, 0)
    finder(5, 0)
    finder(0, 5)

    for col, row in ((3, 2), (4, 3), (3, 4), (5, 5), (4, 6), (6, 4)):
        x = mark_margin + (col * cell)
        y = mark_margin + (row * cell)
        inset = max(2, cell // 7)
        draw.rounded_rectangle(
            (x + inset, y + inset, x + cell - inset, y + cell - inset),
            radius=max(2, stroke // 2),
            fill=ACCENT,
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUTPUT_DIR / "icon-192.png", optimize=True)
    draw_icon(512).save(OUTPUT_DIR / "icon-512.png", optimize=True)
    draw_icon(512, maskable=True).save(OUTPUT_DIR / "maskable-512.png", optimize=True)
    draw_icon(180).save(OUTPUT_DIR / "apple-touch-icon.png", optimize=True)


if __name__ == "__main__":
    main()
