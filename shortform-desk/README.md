# shortform-desk（创意桌）— render slice

> Unrelated to the Mintlify starter in this repo. It lives here temporarily and should move to its own repo.

Brief → 10 ideas → **human picks one** → script draft → **human edits + sets `"approved": true`** → finished vertical MP4 (1080x1920, burned-in Chinese captions, optional BGM).

No publishing, no scheduling, no platform login. Output is a file a human uploads by hand.

## Setup

Needs `ffmpeg`, Python 3.10+, a Chinese font (`fonts-noto-cjk` or `fonts-wqy-microhei`).

```bash
pip install -r requirements.txt
```

## One command (sample)

```bash
python -m desk render samples/script.json -o out/sample.mp4 --bgm auto
```

Writes `out/sample.mp4` plus `out/sample.work/` (`captions.srt`, stills, `render-report.json`).

## Full human-in-the-loop flow

```bash
python -m desk ideas samples/brief.json -o out/ideas.json   # 10 candidates
python -m desk draft out/ideas.json --pick 2 -o out/script.json
# edit out/script.json, set "approved": true
python -m desk render out/script.json -o out/video.mp4
```

`render` refuses scripts without `"approved": true`.

## Providers (pluggable, auto-picked from env)

| Stage | Keyless default | With `OPENAI_API_KEY` |
|---|---|---|
| Ideas / script | bundled samples | OpenAI chat (`OPENAI_MODEL`, default `gpt-4o-mini`) |
| Voice | edge-tts (`zh-CN-XiaoxiaoNeural`), falls back to silence | OpenAI TTS (`OPENAI_TTS_MODEL`) |
| Visuals | gradient title cards + Ken Burns | OpenAI images (`OPENAI_IMAGE_MODEL`, default `gpt-image-1`) |
| BGM | `--bgm auto` generated pad, or `--bgm file.mp3` | — |

Force a provider with `--tts edge|openai|silent` and `--visual card|openai`. A shot's `visual` field may also be a local image path.

Add a provider: one function in `desk/providers/tts.py` or `desk/providers/visuals.py`, then register it in `PROVIDERS`.

## Platforms

`desk/platforms.py` holds format packs (`neutral` default, `douyin`, `shorts`, `reels`, `channels`, `kuaishou`): size, duration range, caption length/size/safe margin. Set `"platform"` in the script or pass `--platform`. `python -m desk platforms` lists them.

## Script JSON

```json
{
  "title": "…",
  "platform": "neutral",
  "voice": "zh-CN-XiaoxiaoNeural",
  "approved": true,
  "shots": [
    {"vo": "口播", "screen_text": "画面大字", "visual": "画面描述或本地图片路径", "palette": "night", "min_sec": 0}
  ]
}
```

Shot length = voiceover length + small padding (or `min_sec`).
