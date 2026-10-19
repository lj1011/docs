"""CLI ideas + script drafting via the pluggable provider; bundled samples when no key. The web desk uses ideation.py."""

import json
from pathlib import Path

from .llm_providers import chat_json as _chat_json
from .llm_providers import provider
from .guidelines import digest
from .platforms import get_platform

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def generate_ideas(brief: dict) -> dict:
    if provider()["name"] == "mock":
        print("! no LLM key (mock): returning bundled sample ideas")
        return json.loads((SAMPLES / "ideas.json").read_text(encoding="utf-8"))
    p = get_platform(brief.get("platform"))
    system = (
        "你是短视频创意编导。输出 JSON：{\"ideas\":[{\"hook\",\"angle\",\"format\",\"why\"}]}，恰好 10 条。"
        "format 取值：口播/对比/清单/反转/演示。hook 是前 3 秒的一句话。"
        f"目标时长 {p.min_sec}-{p.max_sec} 秒，竖屏。避开 brief 里的禁区。"
        "每条加 skeleton（故事骨架编号）和 visual_anchor（唯一视觉锚点）。\n\n" + digest("ideas", brief.get("project_type"))
    )
    data = _chat_json(system, json.dumps(brief, ensure_ascii=False))
    data["brief"] = brief
    return data


def draft_script(ideas: dict, pick: int) -> dict:
    items = ideas.get("ideas") or []
    if not 1 <= pick <= len(items):
        raise SystemExit(f"--pick must be 1..{len(items)}")
    chosen = items[pick - 1]
    if provider()["name"] == "mock":
        print("! no LLM key (mock): returning bundled sample script (edit it before approving)")
        script = json.loads((SAMPLES / "script.json").read_text(encoding="utf-8"))
    else:
        brief = ideas.get("brief", {})
        p = get_platform(brief.get("platform"))
        system = (
            "你是短视频脚本作者。输出 JSON：{\"title\",\"shots\":[{\"vo\",\"screen_text\",\"visual\"}]}。"
            f"总口播约 {int(p.min_sec * 4.5)}-{int(p.max_sec * 4.5)} 字，5-8 个镜头。"
            "vo 是可朗读的口播；screen_text 是画面大字，不超过 10 字；visual 描述画面（用于生成图片）。"
            "第一镜是钩子，最后一镜是 CTA。"
            "另附 director（intent/anchor/camera_light_rhythm/hypothesis/borrowed/unknowns）"
            "和 variants（每个只改一个变量：variable/change/hypothesis/falsify/metric）。"
            "director 用第一人称导演口吻、段落级。\n\n" + digest("script", (brief or {}).get("project_type"))
        )
        script = _chat_json(system, json.dumps({"brief": brief, "idea": chosen}, ensure_ascii=False))
        script["platform"] = brief.get("platform")
    script["idea"] = chosen
    script["approved"] = False
    return script
