"""Human-in-the-loop idea + story module. One JSON file per project under $DESK_DATA (default ./data/projects).

Flow: brief -> ideas (pick/star/reject/edit/more-like/remix) -> beats -> script versions -> human approves -> script.json for `desk render`.
Every prompt carries a digest of guidelines/创意准则.md; approval requires a director statement + single-variable variants.
"""

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from . import guidelines as G
from . import llm_providers as llm
from . import mock

DATA = Path(os.environ.get("DESK_DATA", Path(__file__).resolve().parent.parent / "data" / "projects"))
BEATS = [("hook", "钩子"), ("turn", "转折"), ("payoff", "兑现"), ("cta", "收尾 CTA")]
BEAT_LABEL = dict(BEATS)
IDEA_FIELDS = ("hook", "angle", "format", "why", "skeleton", "visual_anchor")
_lock = threading.RLock()


class DeskError(Exception):
    pass


def _now() -> float:
    return round(time.time(), 3)


def _id() -> str:
    return uuid.uuid4().hex[:8]


def _path(pid: str) -> Path:
    if not pid.isalnum():
        raise DeskError("bad project id")
    return DATA / pid / "project.json"


def save(p: dict) -> dict:
    p["updated"] = _now()
    path = _path(p["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return p


def load(pid: str) -> dict:
    path = _path(pid)
    if not path.exists():
        raise DeskError("project not found")
    return json.loads(path.read_text(encoding="utf-8"))


def list_projects() -> list[dict]:
    if not DATA.exists():
        return []
    out = []
    for f in DATA.glob("*/project.json"):
        p = json.loads(f.read_text(encoding="utf-8"))
        out.append({"id": p["id"], "topic": p["brief"].get("topic", ""), "step": p["step"], "updated": p["updated"]})
    return sorted(out, key=lambda x: -x["updated"])


# ---------- brief ----------

def clean_brief(b: dict) -> dict:
    topic = str(b.get("topic", "")).strip()
    if not topic:
        raise DeskError("「产品/主题」不能为空")
    refs = [str(r).strip() for r in (b.get("refs") or []) if str(r).strip()][:3]
    try:
        duration = int(b.get("duration_sec") or 30)
    except ValueError:
        duration = 30
    return {
        "topic": topic,
        "audience": str(b.get("audience", "")).strip(),
        "tone": str(b.get("tone", "")).strip(),
        "taboo": str(b.get("taboo", "")).strip(),
        "duration_sec": max(10, min(90, duration)),
        "refs": refs,
        "platform": "neutral",
    }


def create_project(brief: dict) -> dict:
    p = {
        "id": _id(), "created": _now(), "updated": _now(), "step": "ideas",
        "brief": clean_brief(brief), "ideas": [], "rounds": 0, "picked": None,
        "story": {"versions": [], "active": None, "approved": None}, "log": [],
        "guidelines": G.meta(),
    }
    with _lock:
        return save(p)


def update_brief(pid: str, brief: dict) -> dict:
    with _lock:
        p = load(pid)
        p["brief"] = clean_brief(brief)
        return save(p)


# ---------- ideas ----------

def _feedback(p: dict) -> dict:
    ideas = p["ideas"]
    return {
        "starred": [i["hook"] for i in ideas if i.get("starred")] or "无",
        "rejected": [{"hook": i["hook"], "reason": i.get("reject_reason") or "未写原因"} for i in ideas if i["status"] == "rejected"] or "无",
        "existing": [i["hook"] for i in ideas if i["status"] != "rejected"] or "无",
    }


def _brief_text(p: dict) -> dict:
    b = dict(p["brief"])
    b.pop("platform", None)
    return b


def _add_ideas(p: dict, raw: list[dict], origin: str) -> list[dict]:
    p["rounds"] += 1
    added = []
    for r in raw:
        idea = {k: str(r.get(k, "")).strip() for k in IDEA_FIELDS}
        if not idea["hook"]:
            continue
        idea["skeleton"] = idea["skeleton"].upper()
        idea["cards"] = _cards(r.get("cards"))
        idea.update(id=_id(), round=p["rounds"], origin=origin, status="new", starred=False,
                    reject_reason="", edited=False, created=_now())
        p["ideas"].append(idea)
        added.append(idea)
    p["log"].append({"t": _now(), "event": "ideas", "origin": origin, "count": len(added), "llm": llm.provider()["name"]})
    return added


def _idea(p: dict, iid: str) -> dict:
    for i in p["ideas"]:
        if i["id"] == iid:
            return i
    raise DeskError("idea not found")


def _cards(raw) -> list[str]:
    if isinstance(raw, str):
        raw = re.findall(r"#?\d{1,2}", raw)
    out = []
    for c in raw or []:
        n = re.sub(r"\D", "", str(c))
        if n and f"#{int(n):02d}" not in out:
            out.append(f"#{int(n):02d}")
    return out


def _public(i: dict) -> dict:
    return {**{k: i.get(k, "") for k in IDEA_FIELDS}, "cards": i.get("cards", [])}


def generate_ideas(pid: str, count: int = 10) -> dict:
    with _lock:
        p = load(pid)
    fb = _feedback(p)
    if llm.provider()["name"] == "mock":
        existing = {i["hook"] for i in p["ideas"]}
        raw = mock.ideas(p["brief"], count, existing, seed=p["rounds"] + len(p["ideas"]))
    else:
        raw = llm.run_prompt("ideas", {"brief": _brief_text(p), "count": str(count), "duration": str(p["brief"]["duration_sec"]),
                                       "guidelines": G.digest("ideas"), **fb})["ideas"]
    with _lock:
        p = load(pid)
        _add_ideas(p, raw, "fresh")
        p["step"] = "ideas"
        return save(p)


def more_like(pid: str, iid: str, count: int = 3) -> dict:
    with _lock:
        p = load(pid)
        src = _idea(p, iid)
    fb = _feedback(p)
    if llm.provider()["name"] == "mock":
        raw = mock.more_like(src, count, seed=len(p["ideas"]))
    else:
        raw = llm.run_prompt("more_like", {"idea": _public(src), "brief": _brief_text(p), "count": str(count), "guidelines": G.digest("ideas"),
                                           "rejected": fb["rejected"], "existing": fb["existing"]})["ideas"]
    with _lock:
        p = load(pid)
        _idea(p, iid)["starred"] = True
        _add_ideas(p, raw, f"more_like:{iid}")
        return save(p)


def remix(pid: str, a: str, b: str, count: int = 2) -> dict:
    if a == b:
        raise DeskError("请选两条不同的点子")
    with _lock:
        p = load(pid)
        ia, ib = _idea(p, a), _idea(p, b)
    if llm.provider()["name"] == "mock":
        raw = mock.remix(ia, ib, count)
    else:
        raw = llm.run_prompt("remix", {"a": _public(ia), "b": _public(ib), "brief": _brief_text(p), "count": str(count), "guidelines": G.digest("ideas"),
                                       "rejected": _feedback(p)["rejected"]})["ideas"]
    with _lock:
        p = load(pid)
        _add_ideas(p, raw, f"remix:{a}+{b}")
        return save(p)


def idea_action(pid: str, iid: str, action: str, payload: dict) -> dict:
    with _lock:
        p = load(pid)
        i = _idea(p, iid)
        if action == "star":
            i["starred"] = not i["starred"]
        elif action == "reject":
            reason = str(payload.get("reason", "")).strip()
            if not reason:
                raise DeskError("拒绝时请写一句原因，它会影响下一轮")
            i.update(status="rejected", reject_reason=reason, starred=False)
            if p["picked"] == iid:
                p["picked"] = None
        elif action == "restore":
            i.update(status="new", reject_reason="")
        elif action == "edit":
            for k in IDEA_FIELDS:
                if k in payload:
                    i[k] = str(payload[k]).strip()
            i["edited"] = True
        elif action == "pick":
            if i["status"] == "rejected":
                raise DeskError("已拒绝的点子不能选，先恢复")
            for other in p["ideas"]:
                if other["status"] == "picked":
                    other["status"] = "new"
            i["status"] = "picked"
            p["picked"] = iid
            p["step"] = "story"
        else:
            raise DeskError(f"unknown action {action}")
        p["log"].append({"t": _now(), "event": action, "idea": iid})
        return save(p)


# ---------- story ----------

def _picked(p: dict) -> dict:
    if not p["picked"]:
        raise DeskError("先在点子页选中 1 条点子")
    return _idea(p, p["picked"])


def _active(p: dict) -> dict:
    st = p["story"]
    for v in st["versions"]:
        if v["id"] == st["active"]:
            return v
    raise DeskError("还没有大纲，先生成大纲")


def _new_version(p: dict, beats: dict, script: dict | None, label: str, base: dict | None = None,
                 skeleton: str = "", director: dict | None = None, variants: list | None = None) -> dict:
    st = p["story"]
    v = {"id": _id(), "n": len(st["versions"]) + 1, "idea": p["picked"], "label": label, "created": _now(),
         "beats": beats, "script": script, "llm": llm.provider()["name"], "parent": base["id"] if base else None,
         "skeleton": skeleton or (base or {}).get("skeleton", ""), "director": director, "variants": variants,
         "scores": {}, "guidelines": G.meta()}
    st["versions"].append(v)
    st["active"] = v["id"]
    st["approved"] = None
    p["step"] = "story"
    return v


def generate_outline(pid: str) -> dict:
    with _lock:
        p = load(pid)
        idea = _picked(p)
    skeleton = idea.get("skeleton", "")
    if llm.provider()["name"] == "mock":
        beats = mock.outline(idea, p["brief"], variant=len(p["story"]["versions"]))
    else:
        res = llm.run_prompt("outline", {"idea": _public(idea), "brief": _brief_text(p), "guidelines": G.digest("outline"),
                                         "duration": str(p["brief"]["duration_sec"])})
        beats, skeleton = res["beats"], str(res.get("skeleton") or skeleton).upper()
    beats = {k: str(beats.get(k, "")).strip() for k, _ in BEATS}
    with _lock:
        p = load(pid)
        _new_version(p, beats, None, "新大纲", skeleton=skeleton)
        return save(p)


def regen_beat(pid: str, key: str, note: str = "") -> dict:
    if key not in BEAT_LABEL:
        raise DeskError("unknown beat")
    with _lock:
        p = load(pid)
        base = _active(p)
        idea = _picked(p)
    if llm.provider()["name"] == "mock":
        variant = 1 + sum(1 for v in p["story"]["versions"] if v["label"].startswith(f"重写{BEAT_LABEL[key]}"))
        text = mock.beat(key, idea, p["brief"], variant)
    else:
        text = llm.run_prompt("beat", {"beat_label": BEAT_LABEL[key], "beats": base["beats"], "current": base["beats"][key],
                                       "skeleton": base.get("skeleton") or "未指定",
                                       "note": note or "无", "brief": _brief_text(p)})["text"]
    with _lock:
        p = load(pid)
        base = _active(p)
        beats = dict(base["beats"], **{key: str(text).strip()})
        _new_version(p, beats, None, f"重写{BEAT_LABEL[key]}", base)
        return save(p)


def generate_script(pid: str) -> dict:
    with _lock:
        p = load(pid)
        base = _active(p)
        idea = _picked(p)
    if any(not base["beats"].get(k) for k, _ in BEATS):
        raise DeskError("四拍都要有内容才能写脚本")
    dur = p["brief"]["duration_sec"]
    if llm.provider()["name"] == "mock":
        script = mock.script(base["beats"], idea, p["brief"], G.skeleton(base.get("skeleton", "")))
    else:
        script = llm.run_prompt("script", {"beats": base["beats"], "idea": _public(idea), "brief": _brief_text(p),
                                           "guidelines": G.digest("script"), "duration": str(dur), "chars": str(int(dur * 4.5))})
    director = _clean_director(script.get("director"))
    variants = _clean_variants(script.get("variants"))
    shots = [{"beat": s.get("beat", ""), "vo": str(s.get("vo", "")).strip(), "screen_text": str(s.get("screen_text", "")).strip(),
              "visual": str(s.get("visual", "")).strip()} for s in script.get("shots", []) if str(s.get("vo", "")).strip()]
    if not shots:
        raise DeskError("模型没有返回镜头，请重试")
    with _lock:
        p = load(pid)
        base = _active(p)
        if base["script"] is None:
            base["script"] = {"title": script.get("title") or idea["hook"], "shots": shots}
            base.update(director=director, variants=variants)
            base["label"] += " + 脚本"
            p["story"]["approved"] = None
        else:
            _new_version(p, dict(base["beats"]), {"title": script.get("title") or idea["hook"], "shots": shots}, "重写脚本", base,
                         director=director, variants=variants)
        return save(p)


def edit_version(pid: str, payload: dict) -> dict:
    """Human edits to the active version (beats and/or script). Any edit clears approval."""
    with _lock:
        p = load(pid)
        v = _active(p)
        if "beats" in payload:
            for k, _ in BEATS:
                if k in payload["beats"]:
                    v["beats"][k] = str(payload["beats"][k]).strip()
        if "script" in payload and v["script"] is not None:
            s = payload["script"]
            if "title" in s:
                v["script"]["title"] = str(s["title"]).strip()
            if "shots" in s:
                v["script"]["shots"] = [{"beat": x.get("beat", ""), "vo": str(x.get("vo", "")).strip(),
                                         "screen_text": str(x.get("screen_text", "")).strip(),
                                         "visual": str(x.get("visual", "")).strip()} for x in s["shots"] if str(x.get("vo", "")).strip()]
        if "director" in payload:
            v["director"] = _clean_director(payload["director"])
        if "variants" in payload:
            v["variants"] = _clean_variants(payload["variants"])
        if "skeleton" in payload:
            v["skeleton"] = str(payload["skeleton"]).strip().upper()
        if "scores" in payload:
            v["scores"] = {k: max(0, min(2, int(x))) for k, x in payload["scores"].items()
                           if re.fullmatch(r"[NV]\d+", k) and str(x).lstrip("-").isdigit()}
        v["edited"] = True
        p["story"]["approved"] = None
        return save(p)


def set_active(pid: str, vid: str) -> dict:
    with _lock:
        p = load(pid)
        if not any(v["id"] == vid for v in p["story"]["versions"]):
            raise DeskError("version not found")
        p["story"]["active"] = vid
        p["story"]["approved"] = None
        return save(p)


def approve(pid: str) -> dict:
    with _lock:
        p = load(pid)
        v = _active(p)
        if not v["script"] or not v["script"]["shots"]:
            raise DeskError("这个版本还没有脚本，不能批准")
        missing = G.director_missing(v.get("director"))
        if missing:
            raise DeskError(f"《创意准则》要求每次故事交付附导演阐述，缺：{'、'.join(missing)}")
        problems = G.variants_problems(v.get("variants"))
        if problems:
            raise DeskError("单变量变体不完整：" + "；".join(problems))
        p["story"]["approved"] = v["id"]
        p["step"] = "approve"
        out = {"title": v["script"]["title"], "platform": "neutral", "approved": True,
               "source": {"project": pid, "version": v["n"], "idea": _public(_picked(p)), "skeleton": v.get("skeleton", "")},
               "director_statement": v["director"], "variants": v["variants"], "scores": v.get("scores", {}),
               "guidelines": G.meta(),
               "shots": [{"vo": s["vo"], "screen_text": s["screen_text"], "visual": s["visual"]} for s in v["script"]["shots"]]}
        (DATA / pid / "script.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        p["log"].append({"t": _now(), "event": "approve", "version": v["n"]})
        return save(p)


def unapprove(pid: str) -> dict:
    with _lock:
        p = load(pid)
        p["story"]["approved"] = None
        p["step"] = "story"
        (DATA / pid / "script.json").unlink(missing_ok=True)
        return save(p)


def _clean_director(d) -> dict:
    d = d if isinstance(d, dict) else {}
    return {k: str(d.get(k, "")).strip() for k, _ in G.DIRECTOR_FIELDS}


def _clean_variants(vs) -> list[dict]:
    out = []
    for v in vs if isinstance(vs, list) else []:
        if isinstance(v, dict):
            row = {k: str(v.get(k, "")).strip() for k, _ in G.VARIANT_FIELDS}
            if any(row.values()):
                out.append(row)
    return out


def score_summary(v: dict) -> dict:
    """Totals vs the pass lines in 创意准则 §1.4 (proposal; weights pending Keven)."""
    g = G.load()
    scores = v.get("scores") or {}
    qs = g["questions"]
    n = sum(scores.get(q["id"], 0) for q in qs if q["dim"] == "narrative")
    vis = sum(scores.get(q["id"], 0) for q in qs if q["dim"] == "visual")
    th = g["thresholds"]
    answered = sum(1 for q in qs if q["id"] in scores)

    def ok(val, key):
        return th.get(key) is None or val >= th[key][0]

    passed = ok(n, "narrative") and ok(vis, "visual") and ok(n + vis, "total") and scores.get("N1", 0) >= 1 and scores.get("V1", 0) >= 1
    return {"narrative": n, "visual": vis, "total": n + vis, "answered": answered, "questions": len(qs), "passed": passed, "thresholds": th}


def script_path(pid: str) -> Path:
    return DATA / pid / "script.json"
