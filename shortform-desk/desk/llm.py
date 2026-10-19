"""Ideas + script drafting. Uses OpenAI if OPENAI_API_KEY is set, else returns the bundled samples."""

import json
import os
import urllib.request
from pathlib import Path

from .platforms import get_platform

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _chat_json(system: str, user: str) -> dict:
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(json.loads(r.read())["choices"][0]["message"]["content"])


def generate_ideas(brief: dict) -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        print("! no OPENAI_API_KEY: returning bundled sample ideas")
        return json.loads((SAMPLES / "ideas.json").read_text(encoding="utf-8"))
    p = get_platform(brief.get("platform"))
    system = (
        "你是短视频创意编导。输出 JSON：{\"ideas\":[{\"hook\",\"angle\",\"format\",\"why\"}]}，恰好 10 条。"
        "format 取值：口播/对比/清单/反转/演示。hook 是前 3 秒的一句话。"
        f"目标时长 {p.min_sec}-{p.max_sec} 秒，竖屏。避开 brief 里的禁区。"
    )
    data = _chat_json(system, json.dumps(brief, ensure_ascii=False))
    data["brief"] = brief
    return data


def draft_script(ideas: dict, pick: int) -> dict:
    items = ideas.get("ideas") or []
    if not 1 <= pick <= len(items):
        raise SystemExit(f"--pick must be 1..{len(items)}")
    chosen = items[pick - 1]
    if not os.environ.get("OPENAI_API_KEY"):
        print("! no OPENAI_API_KEY: returning bundled sample script (edit it before approving)")
        script = json.loads((SAMPLES / "script.json").read_text(encoding="utf-8"))
    else:
        brief = ideas.get("brief", {})
        p = get_platform(brief.get("platform"))
        system = (
            "你是短视频脚本作者。输出 JSON：{\"title\",\"shots\":[{\"vo\",\"screen_text\",\"visual\"}]}。"
            f"总口播约 {int(p.min_sec * 4.5)}-{int(p.max_sec * 4.5)} 字，5-8 个镜头。"
            "vo 是可朗读的口播；screen_text 是画面大字，不超过 10 字；visual 描述画面（用于生成图片）。"
            "第一镜是钩子，最后一镜是 CTA。"
        )
        script = _chat_json(system, json.dumps({"brief": brief, "idea": chosen}, ensure_ascii=False))
        script["platform"] = brief.get("platform")
    script["idea"] = chosen
    script["approved"] = False
    return script
