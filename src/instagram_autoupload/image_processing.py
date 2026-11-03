"""Crop/resize a JPEG to Instagram's supported aspect ratio and max dimensions.

Mirrors the Lightroom Classic plugin's cropAndResizeForInstagram logic:
only crops when outside the valid range, and only by the minimum amount
needed to reach the nearest boundary ratio.
"""

from __future__ import annotations

from PIL import Image

MAX_WIDTH = 1080
MAX_HEIGHT = 1350
MIN_ASPECT_RATIO = 0.8  # 4:5 portrait
MAX_ASPECT_RATIO = 1.91  # widest supported landscape
JPEG_QUALITY = 90


def crop_and_resize_for_instagram(path: str) -> None:
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        ratio = width / height

        crop_width, crop_height = width, height
        if ratio < MIN_ASPECT_RATIO:
            crop_height = int(width / MIN_ASPECT_RATIO)
        elif ratio > MAX_ASPECT_RATIO:
            crop_width = int(height * MAX_ASPECT_RATIO)

        if (crop_width, crop_height) != (width, height):
            left = (width - crop_width) // 2
            top = (height - crop_height) // 2
            img = img.crop((left, top, left + crop_width, top + crop_height))
            width, height = crop_width, crop_height

        final_ratio = width / height
        final_width = min(MAX_WIDTH, width)
        final_height = int(final_width / final_ratio)
        if final_height > MAX_HEIGHT:
            final_height = MAX_HEIGHT
            final_width = int(final_height * final_ratio)

        if (final_width, final_height) != (width, height):
            img = img.resize((final_width, final_height), Image.LANCZOS)

        img.save(path, "JPEG", quality=JPEG_QUALITY)
