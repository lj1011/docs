# shortform-desk（创意桌）— render slice

> Unrelated to the Mintlify starter in this repo. It lives here temporarily and should move to its own repo.

Brief → 10 ideas → **human picks one** → script draft → **human edits + sets `"approved": true`** → finished vertical MP4 (1080x1920, burned-in Chinese captions, optional BGM).

No publishing, no scheduling, no platform login. Output is a file a human uploads by hand.

## Setup

Needs `ffmpeg`, Python 3.10+, a Chinese font (`fonts-noto-cjk` or `fonts-wqy-microhei`).

```bash
pip install -r requirements.txt
```

## Web desk (ideas → story → approve)

```bash
python -m desk serve            # http://127.0.0.1:8787
```

Four screens, one job each:

1. **简报** — topic (required), audience, tone, taboo, duration, up to 3 reference links/notes.
2. **点子** — 10 candidates (hook / angle / format / why). Pick, star, reject (reason required), edit, 「更多类似」, 混搭两条, 再来 10 条. Stars and rejection reasons are fed into the next round's prompt.
3. **故事** — 4-beat outline (钩子 → 转折 → 兑现 → CTA), edit any beat, rewrite one beat (optional note), expand to script + shot list, edit shots. Every AI rewrite is a new version; compare two versions side by side and switch.
4. **批准** — human approves one version, which writes `data/projects/<id>/script.json` (`"approved": true`). Any later edit clears approval. Then 「现在渲染成片」 or run `desk render` on that file.

Everything (including rejected ideas + reasons, all versions, an event log) is saved in `data/projects/<id>/project.json` (override with `DESK_DATA`).

### 创意准则 (creative guidelines)

`guidelines/创意准则.md` is Keven's iterable creative standard (v0.2: distilled from 23 story-inspiration cards, with Keven's 8 decisions from 2026-10-19 in §七). The desk reads it on every generation (re-read when the file changes, override path with `DESK_GUIDELINES`):

- **Prompts**: `desk/guidelines.py` builds a per-task digest injected as `{{guidelines}}` — ideas get the scoring questions, veto list, skeleton library and anti-patterns; outlines get skeleton beats; scripts get the visual technique library, the director-statement template and the single-variable variant rule.
- **Ideas** carry `skeleton` (e.g. `S07`), `visual_anchor`, and cited `cards`.
- **Story versions** carry `skeleton`, `director` (立意 / 视觉锚点 / 运镜·光色·节奏 / 核心假设 / 借鉴与边界 / 待补推断), `variants` (one variable each + falsifiable hypothesis) and optional `scores` against §1.
- **Project type** (brief `project_type`): `original` 自创故事 (default, no brand) or `brand` 品牌片 (any brand; none is assumed).
- **Approval is blocked** until the director statement's 4 core fields are filled in first person (「我…」, paragraph-level) and ≥1 complete single-variable variant exists (metric defaults to Keven 审美判断（过稿与否）). It is also blocked by a keyword check: brand films may not use dark / thriller / violence-edge wording, and blade-to-throat / slash close-ups are blocked for both types. The approved `script.json` includes them plus the guidelines version/sha.
- **UI**: header link 「创意准则 v0.2」; the brief form has a project-type select and brand field renders the file; idea cards show skeleton tags; the story screen has director / variant / scoring panels.
- CLI: `python -m desk guidelines` (summary) or `--digest ideas|outline|script`.

### LLM provider

Auto-picked from env (force with `DESK_LLM=openai|anthropic|mock`):

| Set | Uses |
|---|---|
| `OPENAI_API_KEY` | OpenAI (`OPENAI_MODEL`, default `gpt-4o-mini`) |
| `OPENAI_API_KEY` + `OPENAI_BASE_URL` | any OpenAI-compatible API, e.g. DeepSeek `https://api.deepseek.com/v1` + `OPENAI_MODEL=deepseek-chat`; Qwen `https://dashscope.aliyuncs.com/compatible-mode/v1`; Moonshot `https://api.moonshot.cn/v1` |
| `ANTHROPIC_API_KEY` | Anthropic (`ANTHROPIC_MODEL`, default `claude-sonnet-4-5`) |
| nothing | **offline MOCK**: template output, labeled with a yellow banner in the UI. Demo only. |

Prompts live in `prompts/*.md` (Chinese output, platform-neutral, `{{var}}` placeholders).

Tests: `python -m unittest discover -s tests -t .`

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
