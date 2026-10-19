"""Pluggable TTS. Each provider writes an audio file for one line of voiceover."""

import asyncio
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from ..util import run


def _edge(text: str, out: Path, voice: str | None) -> Path:
    import edge_tts

    out = out.with_suffix(".mp3")
    comm = edge_tts.Communicate(text, voice or "zh-CN-XiaoxiaoNeural", rate="+8%")
    asyncio.run(comm.save(str(out)))
    return out


def _openai(text: str, out: Path, voice: str | None) -> Path:
    out = out.with_suffix(".mp3")
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            "voice": voice or "alloy",
            "input": text,
            "instructions": "用自然、有活力的普通话口播语气。",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())
    return out


def _silent(text: str, out: Path, voice: str | None) -> Path:
    out = out.with_suffix(".wav")
    seconds = max(1.5, len(text) / 4.5)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.2f}", str(out)])
    return out


PROVIDERS = {"edge": _edge, "openai": _openai, "silent": _silent}


def pick_tts(name: str) -> str:
    if name != "auto":
        return name
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    try:
        import edge_tts  # noqa: F401

        return "edge"
    except ImportError:
        return "silent"


def synthesize(provider: str, text: str, out: Path, voice: str | None) -> tuple[Path, str]:
    """Returns (audio_path, provider_actually_used). Falls back to silent so the render never blocks."""
    try:
        return PROVIDERS[provider](text, out, voice), provider
    except (Exception, subprocess.CalledProcessError) as e:  # network/key failures
        if provider == "silent":
            raise
        print(f"  ! tts '{provider}' failed ({e}); using silent placeholder")
        return _silent(text, out, voice), "silent"
