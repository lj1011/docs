"""Pluggable per-shot visuals. A provider returns a background image; compose() overlays the on-screen text."""

import base64
import json
import os
import random
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

PALETTES = {
    "sunset": ((255, 94, 98), (255, 195, 113)),
    "ocean": ((17, 153, 142), (56, 239, 125)),
    "night": ((20, 30, 48), (36, 59, 85)),
    "grape": ((131, 58, 180), (253, 29, 29)),
    "sky": ((41, 128, 185), (109, 213, 250)),
    "ink": ((15, 15, 20), (60, 60, 75)),
    "peach": ((237, 66, 100), (255, 237, 188)),
}
ORDER = ["night", "sunset", "ocean", "grape", "sky", "peach", "ink"]

# Backgrounds are oversized so the Ken Burns pan/zoom never reveals edges.
OVERSCAN = 1.2


def _card(shot, idx: int, size: tuple[int, int], seed: str) -> Image.Image:
    w, h = size
    top, bottom = PALETTES.get(shot.palette) or PALETTES[ORDER[idx % len(ORDER)]]
    grad = Image.linear_gradient("L").resize((w, h))
    img = ImageOps.colorize(grad, top, bottom).convert("RGBA")
    rng = random.Random(f"{seed}-{idx}")
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    for _ in range(6):
        r = rng.randint(w // 6, w // 2)
        x, y = rng.randint(0, w), rng.randint(0, h)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(18, 45)))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(w // 12)))
    return img.convert("RGB")


def _openai(shot, idx: int, size: tuple[int, int], seed: str) -> Image.Image:
    prompt = (shot.visual or shot.vo) + "。竖屏 9:16 画面，电影感，干净构图，画面中不要出现任何文字。"
    body = json.dumps(
        {"model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"), "prompt": prompt, "size": "1024x1536"}
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=body,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        b64 = json.loads(r.read())["data"][0]["b64_json"]
    tmp = Path(f"/tmp/desk-openai-{seed}-{idx}.png")
    tmp.write_bytes(base64.b64decode(b64))
    return ImageOps.fit(Image.open(tmp).convert("RGB"), size)


def _local(shot, idx: int, size: tuple[int, int], seed: str) -> Image.Image:
    return ImageOps.fit(Image.open(shot.visual).convert("RGB"), size)


PROVIDERS = {"card": _card, "openai": _openai}


def pick_visual(name: str) -> str:
    if name != "auto":
        return name
    return "openai" if os.environ.get("OPENAI_API_KEY") else "card"


def _wrap(text: str, max_chars: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        cur += ch
        if len(cur) >= max_chars:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def compose(provider: str, shot, idx: int, canvas: tuple[int, int], font_path: str, out: Path, seed: str) -> str:
    """Writes an oversized still to `out`; returns the provider actually used."""
    size = (int(canvas[0] * OVERSCAN), int(canvas[1] * OVERSCAN))
    used = provider
    if shot.visual and Path(shot.visual).is_file():
        bg, used = _local(shot, idx, size, seed), "local"
    else:
        try:
            bg = PROVIDERS[provider](shot, idx, size, seed)
        except Exception as e:  # missing key, quota, network
            if provider == "card":
                raise
            print(f"  ! visual '{provider}' failed ({e}); using card")
            bg, used = _card(shot, idx, size, seed), "card"

    if shot.screen_text:
        draw = ImageDraw.Draw(bg)
        font = ImageFont.truetype(font_path, int(size[0] * 0.115))
        lines = _wrap(shot.screen_text, 8)
        line_h = int(font.size * 1.3)
        y = int(size[1] * 0.30) - line_h * len(lines) // 2
        for line in lines:
            tw = draw.textlength(line, font=font)
            x = (size[0] - tw) / 2
            draw.text((x + 6, y + 8), line, font=font, fill=(0, 0, 0))
            draw.text((x, y), line, font=font, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
            y += line_h
    bg.save(out)
    return used
