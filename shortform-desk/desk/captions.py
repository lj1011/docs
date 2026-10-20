"""Split voiceover into short caption lines, time them, and emit ASS (burned in) + SRT (for the export pack)."""

import re

PUNCT = "，。！？、；：,.!?;:…"


def split_caption(text: str, max_chars: int) -> list[str]:
    parts = [p.strip() for p in re.split(f"[{re.escape(PUNCT)}]+", text) if p.strip()]
    lines = []
    for p in parts:
        while len(p) > max_chars:
            cut = max_chars if len(p) - max_chars >= 4 else len(p) // 2
            lines.append(p[:cut])
            p = p[cut:]
        lines.append(p)
    return lines


def timed_lines(text: str, start: float, speech_sec: float, max_chars: int) -> list[tuple[float, float, str]]:
    lines = split_caption(text, max_chars)
    total = sum(len(l) for l in lines) or 1
    out, t = [], start
    for l in lines:
        d = speech_sec * len(l) / total
        out.append((t, t + d, l))
        t += d
    return out


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def to_ass(cues, width: int, height: int, font_name: str, font_size: int, margin_bottom: int) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,2,0,1,6,2,2,60,60,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(f"Dialogue: 0,{_ts_ass(a)},{_ts_ass(b)},Cap,,0,0,0,,{t}\n" for a, b, t in cues)
    return head + body


def to_srt(cues) -> str:
    return "\n".join(f"{i}\n{_ts_srt(a)} --> {_ts_srt(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))
