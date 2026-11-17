"""Dev only: draw FileSweep's icon with Pillow (no runtime dependency)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (37, 99, 235)
BLUE_DARK = (29, 78, 216)
WHITE = (255, 255, 255)


def draw(size: int) -> Image.Image:
    scale = 8  # draw big, then downscale for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BLUE)

    # folder body
    left, right = int(s * 0.18), int(s * 0.82)
    top, bottom = int(s * 0.33), int(s * 0.72)
    d.rounded_rectangle([left, top, right, bottom], radius=int(s * 0.05), fill=WHITE)
    # folder tab
    d.rounded_rectangle(
        [left, int(s * 0.24), int(s * 0.52), int(s * 0.38)],
        radius=int(s * 0.04),
        fill=WHITE,
    )
    # sweep: three lines sliding into the folder
    for i, y in enumerate((0.42, 0.50, 0.58)):
        width = 0.30 - i * 0.05
        d.rounded_rectangle(
            [int(s * 0.30), int(s * y), int(s * (0.30 + width)), int(s * (y + 0.045))],
            radius=int(s * 0.02),
            fill=BLUE_DARK,
        )
    # check mark
    d.line(
        [(int(s * 0.60), int(s * 0.62)), (int(s * 0.66), int(s * 0.68)), (int(s * 0.76), int(s * 0.53))],
        fill=BLUE,
        width=int(s * 0.055),
        joint="curve",
    )
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    master = draw(1024)
    master.save(assets / "filesweep.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.resize((256, 256), Image.LANCZOS).save(root / "docs" / "icon.png")
    print("icon written to assets/filesweep.ico and docs/icon.png")


if __name__ == "__main__":
    main()
