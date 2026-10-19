"""Script JSON -> finished vertical MP4 via ffmpeg."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import ImageFont

from . import captions
from .platforms import get_platform
from .providers import tts, visuals
from .script import Script
from .util import find_cjk_font, probe_duration, require_ffmpeg, run

LEAD = 0.15  # silence before each line so cuts don't clip the first syllable
TAIL = 0.35


def _clip(still: Path, out: Path, dur: float, p, zoom_in: bool) -> None:
    frames = max(1, round(dur * p.fps))
    step = 0.12 / frames
    z = f"min(1+{step:.6f}*on,1.12)" if zoom_in else f"max(1.12-{step:.6f}*on,1)"
    vf = (
        # Upscale before zoompan: it crops on integer pixels, so a bigger source hides the jitter.
        f"scale=iw*2:-1,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={p.width}x{p.height}:fps={p.fps},format=yuv420p"
    )
    run(["ffmpeg", "-y", "-i", str(still), "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])


def _padded_audio(src: Path, out: Path, dur: float) -> None:
    ms = int(LEAD * 1000)
    run(["ffmpeg", "-y", "-i", str(src), "-af", f"adelay={ms}:all=1,apad,atrim=0:{dur:.3f}",
         "-ar", "44100", "-ac", "2", str(out)])


def _concat(files: list[Path], out: Path, extra: list[str]) -> None:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{f.name}'\n" for f in files))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), *extra, str(out)])


def _auto_bgm(out: Path, dur: float) -> None:
    # Keyless placeholder pad (A-major chord with slow swell). Replace with a licensed track via --bgm FILE.
    expr = "+".join(
        f"{a}*sin(2*PI*{f}*t)*(0.6+0.4*sin(2*PI*{lfo}*t))"
        for a, f, lfo in [(0.05, 110, 0.11), (0.04, 220, 0.17), (0.03, 277.18, 0.13), (0.03, 329.63, 0.07)]
    )
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={dur:.2f}",
         "-af", f"lowpass=f=1200,afade=t=in:d=1.5,afade=t=out:st={max(0, dur - 2):.2f}:d=2",
         "-ac", "2", str(out)])


def render(script: Script, out: Path, *, platform_id=None, tts_name="auto", visual_name="auto",
           bgm=None, workdir: Path | None = None) -> dict:
    require_ffmpeg()
    p = get_platform(platform_id or script.platform)
    tts_provider = tts.pick_tts(tts_name)
    vis_provider = visuals.pick_visual(visual_name)
    font_path = find_cjk_font()
    font_name = ImageFont.truetype(font_path, 10).getname()[0]
    seed = hashlib.sha1(script.title.encode()).hexdigest()[:8]

    out = Path(out).resolve()
    work = Path(workdir or out.parent / f"{out.stem}.work").resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    clips, auds, cues, used = [], [], [], {"tts": set(), "visual": set()}
    t = 0.0
    for i, shot in enumerate(script.shots):
        print(f"[{i + 1}/{len(script.shots)}] {shot.vo[:24]}")
        raw, tts_used = tts.synthesize(tts_provider, shot.vo, work / f"vo{i:02d}", script.voice)
        speech = probe_duration(raw)
        dur = max(shot.min_sec, LEAD + speech + TAIL)
        still = work / f"still{i:02d}.png"
        vis_used = visuals.compose(vis_provider, shot, i, (p.width, p.height), font_path, still, seed)
        clip, aud = work / f"clip{i:02d}.mp4", work / f"aud{i:02d}.wav"
        _clip(still, clip, dur, p, zoom_in=i % 2 == 0)
        _padded_audio(raw, aud, dur)
        cues += captions.timed_lines(shot.vo, t + LEAD, speech, p.max_caption_chars)
        clips.append(clip)
        auds.append(aud)
        used["tts"].add(tts_used)
        used["visual"].add(vis_used)
        t += dur

    _concat(clips, work / "video.mp4", ["-c", "copy"])
    _concat(auds, work / "vo.wav", ["-c", "copy"])
    (work / "captions.ass").write_text(
        captions.to_ass(cues, p.width, p.height, font_name, p.caption_font_size, p.caption_margin_bottom),
        encoding="utf-8")
    (work / "captions.srt").write_text(captions.to_srt(cues), encoding="utf-8")

    inputs = ["-i", "video.mp4", "-i", "vo.wav"]
    if bgm == "auto":
        _auto_bgm(work / "bgm.wav", t)
        bgm = str(work / "bgm.wav")
    if bgm:
        inputs += ["-stream_loop", "-1", "-i", str(Path(bgm).resolve())]
        afilter = ["-filter_complex", "[2:a]volume=0.35[b];[1:a][b]amix=inputs=2:duration=first:normalize=0[a]",
                   "-map", "0:v", "-map", "[a]"]
    else:
        afilter = ["-map", "0:v", "-map", "1:a"]
    fontsdir = str(Path(font_path).parent)
    vf = f"ass=captions.ass:fontsdir={fontsdir},fade=t=in:d=0.3,fade=t=out:st={max(0, t - 0.4):.2f}:d=0.4"
    cmd = ["ffmpeg", "-y", *inputs, *afilter, "-vf", vf, "-t", f"{t:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    res = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-2000:])

    report = {
        "output": str(out),
        "platform": p.id,
        "duration_sec": round(probe_duration(out), 2),
        "size": f"{p.width}x{p.height}",
        "shots": len(script.shots),
        "tts": sorted(used["tts"]),
        "visual": sorted(used["visual"]),
        "bgm": bool(bgm),
        "srt": str(work / "captions.srt"),
    }
    if not p.min_sec <= report["duration_sec"] <= p.max_sec:
        report["warning"] = f"duration outside {p.label} range {p.min_sec}-{p.max_sec}s"
    (work / "render-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
