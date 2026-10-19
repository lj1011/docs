import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])}...\n{res.stderr[-2000:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(out)


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH")


def find_cjk_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    out = subprocess.run(["fc-list", ":lang=zh", "file"], capture_output=True, text=True).stdout.split("\n")
    for line in out:
        if line.strip():
            return line.split(":")[0].strip()
    raise SystemExit("no Chinese font found; install fonts-noto-cjk or fonts-wqy-microhei")
