#!/usr/bin/env python3
"""Draw the simple frame mark at native launcher sizes; requires Pillow."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "mobile"


def icon(size):
    image = Image.new("RGB", (1024, 1024), "#f5f3ed")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((144, 208, 880, 780), radius=64, fill="#203a34")
    draw.rounded_rectangle((200, 264, 824, 682), radius=18, fill="#fffdf8")
    draw.polygon([(224, 642), (390, 370), (510, 555), (622, 430), (800, 642)], fill="#608573")
    draw.ellipse((655, 306, 731, 382), fill="#e3b148")
    for i, color in enumerate(["#000000", "#ffffff", "#ffe300", "#f11400", "#0069f6", "#14a65d"]):
        x = 337 + i * 64
        draw.ellipse((x, 711, x + 28, 739), fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


for density, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
    icon(size).save(root / f"android/app/src/main/res/mipmap-{density}/ic_launcher.png")
directory = root / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
for item in json.loads((directory / "Contents.json").read_text())["images"]:
    if "filename" in item:
        size = round(float(item["size"].split("x")[0]) * float(item["scale"].removesuffix("x")))
        icon(size).save(directory / item["filename"])
print("Android and iOS launcher assets generated.")
