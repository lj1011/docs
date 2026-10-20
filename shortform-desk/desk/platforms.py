"""Platform format packs. Rendering only reads these values; switching platform = pick another key."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    id: str
    label: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    min_sec: float = 20
    max_sec: float = 40
    max_caption_chars: int = 14
    caption_font_size: int = 76
    # Bottom margin keeps captions above the like/comment/description UI most apps overlay.
    caption_margin_bottom: int = 420


PLATFORMS: dict[str, Platform] = {
    "neutral": Platform("neutral", "平台中立（默认）"),
    "douyin": Platform("douyin", "抖音", min_sec=15, max_sec=45),
    "shorts": Platform("shorts", "YouTube Shorts", min_sec=15, max_sec=60, max_caption_chars=16),
    "reels": Platform("reels", "Instagram Reels", min_sec=15, max_sec=30, max_caption_chars=12, caption_font_size=84),
    "channels": Platform("channels", "视频号", min_sec=20, max_sec=60, max_caption_chars=16),
    "kuaishou": Platform("kuaishou", "快手", min_sec=15, max_sec=40, caption_font_size=84),
}

DEFAULT_PLATFORM = "neutral"


def get_platform(platform_id: str | None) -> Platform:
    key = platform_id or DEFAULT_PLATFORM
    if key not in PLATFORMS:
        raise SystemExit(f"unknown platform '{key}', choose one of: {', '.join(PLATFORMS)}")
    return PLATFORMS[key]
