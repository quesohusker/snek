import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZE = 1024
BG = (26, 107, 60, 255)
FG = (236, 248, 230, 255)
R = 150
W = 120


def point(cx, cy, angle):
    return cx + R * math.cos(math.radians(angle)), cy + R * math.sin(math.radians(angle))


def dot(d, x, y, r, fill):
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def arc(d, cx, cy, start, end):
    half = W / 2
    d.arc([cx - R - half, cy - R - half, cx + R + half, cy + R + half], start=start, end=end, fill=FG, width=W)


def draw():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, SIZE - 40, SIZE - 40], radius=220, fill=BG)
    top, bottom = (512, 360), (512, 360 + 2 * R)
    arc(d, *top, 90, 340)
    arc(d, *bottom, 270, 360)
    arc(d, *bottom, 0, 160)
    hx, hy = point(*top, 340)
    dot(d, hx, hy, 82, FG)
    dot(d, hx + 14, hy - 24, 20, BG)
    tx, ty = point(*bottom, 160)
    dot(d, tx, ty, W / 2, FG)
    return img


if __name__ == "__main__":
    icon = draw()
    icon.save(HERE / "snek.png")
    icon.save(HERE / "snek.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", HERE / "snek.png", HERE / "snek.ico")
