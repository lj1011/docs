"""Loads guidelines/创意准则.md and turns it into prompt digests + structured data for the UI.

The markdown is the source of truth and is edited by humans, so parsing is tolerant: missing parts
degrade to empty lists instead of failing. Conventions relied on:
  ## 零、 / ## 一、 ... section headings
  ### Sxx · 名称            skeletons, with "- **核心机制**：" / "- **戏剧节拍**：" / "- **卡片**：" bullets
  | N1 | 问题 | ... |       scoring questions (N = 叙事/策略, V = 视觉)
  叙事 ≥ 7/12 / 视觉 ≥ 8/14 / 合计 ≥ 16/26   pass lines
"""

import hashlib
import os
import re
from pathlib import Path

PATH = Path(os.environ.get("DESK_GUIDELINES", Path(__file__).resolve().parent.parent / "guidelines" / "创意准则.md"))
SECTION_KEYS = ["零", "一", "二", "三", "四", "五", "六", "七"]
DIRECTOR_FIELDS = [
    ("intent", "立意"),
    ("anchor", "视觉锚点"),
    ("camera_light_rhythm", "运镜·光色·节奏"),
    ("hypothesis", "核心假设"),
    ("borrowed", "借鉴与边界"),
    ("unknowns", "待补／推断"),
]
DIRECTOR_REQUIRED = ["intent", "anchor", "camera_light_rhythm", "hypothesis"]
VARIANT_FIELDS = [
    ("variable", "变量（只改一个）"),
    ("change", "改法：A → B"),
    ("hypothesis", "假设"),
    ("falsify", "证伪条件"),
    ("metric", "指标"),
]
VARIANT_REQUIRED = ["variable", "change", "hypothesis", "falsify"]
DEFAULT_METRIC = "Keven 审美判断（过稿与否）"

# Keven 2026-10-19: no default brand; every project is either a brand film or an original story.
PROJECT_TYPES = {"original": "自创故事", "brand": "品牌片"}
# Banned in both project types (创意准则 A2 / 1.3).
VIOLENCE_CLOSEUP_TERMS = ["刀刃抵喉", "刀抵喉", "割喉", "斩击特写", "斩首", "砍头"]
# Banned only in brand films (创意准则 A14 / 1.3): dark, horror, violence-adjacent tone.
# Keyword matching is a coarse safety net; the human reviewer still decides.
DARK_TONE_TERMS = ["惊悚", "恐怖", "惊吓", "血腥", "鲜血", "流血", "喷血", "血迹", "尸体", "杀人", "谋杀", "凶杀",
                   "开颅", "黑色幽默", "暗黑", "打斗", "厮杀", "斩杀", "暴力", "虐待", "自残", "鬼魂", "诅咒"]

_cache: dict = {}


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## ", text, flags=re.M)
    out = {}
    for p in parts[1:]:
        key = p[:1]
        if key in SECTION_KEYS:
            out[key] = "## " + p.strip()
    return out


def _bullet(block: str, label: str) -> str:
    m = re.search(rf"^- \*\*{label}\*\*：(.+)$", block, re.M)
    return m.group(1).strip() if m else ""


def _skeletons(sec: str) -> list[dict]:
    out = []
    for m in re.finditer(r"^### (S\d+) · (.+?)\n(.*?)(?=^### |\Z)", sec, re.M | re.S):
        sid, name, body = m.group(1), m.group(2).strip(), m.group(3)
        cards_line = _bullet(body, "卡片")
        out.append({
            "id": sid,
            "name": name,
            "mechanism": _bullet(body, "核心机制"),
            "beats": _bullet(body, "戏剧节拍"),
            "fits": _bullet(body, "适用场景"),
            "cards": sorted(set(re.findall(r"#(\d\d)", cards_line))),
            "cards_text": cards_line,
        })
    return out


def _questions(sec: str) -> list[dict]:
    out = []
    for line in sec.splitlines():
        m = re.match(r"^\| ([NV]\d+) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$", line)
        if m:
            qid = m.group(1)
            out.append({"id": qid, "dim": "narrative" if qid[0] == "N" else "visual", "text": m.group(2),
                        "levels": [m.group(3), m.group(4), m.group(5)], "cards": sorted(set(re.findall(r"#(\d\d)", m.group(6))))})
    return out


def _thresholds(sec: str) -> dict:
    def grab(label):
        m = re.search(rf"{label}\s*≥\s*(\d+)\s*/\s*(\d+)", sec)
        return [int(m.group(1)), int(m.group(2))] if m else None

    return {"narrative": grab("叙事"), "visual": grab("视觉"), "total": grab("合计")}


def load() -> dict:
    mtime = PATH.stat().st_mtime if PATH.exists() else None
    if _cache.get("mtime") == mtime and "data" in _cache:
        return _cache["data"]
    if mtime is None:
        data = {"path": str(PATH), "exists": False, "version": "missing", "sha": "", "text": "", "sections": {},
                "skeletons": [], "questions": [], "thresholds": {}}
    else:
        text = PATH.read_text(encoding="utf-8")
        secs = _sections(text)
        vm = re.search(r"v\d+\.\d+", text.splitlines()[0] if text else "")
        data = {
            "path": str(PATH),
            "exists": True,
            "version": vm.group(0) if vm else "unversioned",
            "sha": hashlib.sha1(text.encode()).hexdigest()[:10],
            "text": text,
            "sections": secs,
            "skeletons": _skeletons(secs.get("二", "")),
            "questions": _questions(secs.get("一", "")),
            "thresholds": _thresholds(secs.get("一", "")),
        }
    _cache.update(mtime=mtime, data=data)
    return data


def meta() -> dict:
    g = load()
    return {"path": g["path"], "version": g["version"], "sha": g["sha"]}


def skeleton(sid: str) -> dict | None:
    return next((s for s in load()["skeletons"] if s["id"] == (sid or "").strip().upper()), None)


def _strip_cards(s: str) -> str:
    return re.sub(r"[（(][^（）()]*#\d\d[^（）()]*[）)]", "", s)


def _subsection(sec: str, title_prefix: str) -> str:
    m = re.search(rf"^### {re.escape(title_prefix)}.*?(?=^### |\Z)", sec, re.M | re.S)
    return m.group(0).strip() if m else ""


def digest(task: str, ptype: str | None = None, limit: int = 6500) -> str:
    """Compact, task-specific excerpt of the guidelines for prompt injection."""
    g = load()
    if not g["exists"]:
        return "（未找到《创意准则》，按通用短视频常识创作，并在输出里注明“准则缺失”。）"
    head = f"《创意准则》{g['version']}（草稿，人会继续修改）。不知道的写「待补」，推断的写「推断」，没有卡片证据的写「待验证假设」。"
    sk = g["skeletons"]
    qs = g["questions"]
    secs = g["sections"]
    parts = [head, stance(task, ptype)]
    if task in ("ideas", "outline"):
        parts.append("【判断标准：每题 0/1/2 分】\n" + "\n".join(f"{q['id']} {q['text']}" for q in qs))
        veto = _subsection(secs.get("一", ""), "1.3")
        if veto:
            parts.append("【一票否决】\n" + "\n".join(l for l in veto.splitlines() if l.startswith("- ")))
    if task == "ideas":
        parts.append("【故事骨架库：点子要标骨架编号】\n" + "\n".join(f"{s['id']} {s['name']}：{_strip_cards(s['mechanism'])}" for s in sk))
        anti = [l for l in secs.get("五", "").splitlines() if re.match(r"^\| A\d+ \|", l)]
        parts.append("【反模式：不要出】\n" + "\n".join(re.sub(r"^\| (A\d+) \| \*\*(.+?)\*\* \|.*$", r"\1 \2", l) for l in anti))
    if task == "outline":
        parts.append("【故事骨架库：大纲要沿用所选骨架的节拍】\n" + "\n".join(f"{s['id']} {s['name']}：{s['beats']}" for s in sk))
    if task == "script":
        vis = secs.get("三", "")
        lines = [l if l.startswith("###") else _strip_cards(l) for l in vis.splitlines() if l.startswith("### ") or l.startswith("- **")]
        parts.append("【视觉手法库】\n" + "\n".join(lines))
        meth = secs.get("四", "")
        parts.append("【单变量变体规则】每个变体只改一个变量，并附可证伪假设（变量／改法／假设／证伪条件／指标）。")
        tpl = re.search(r"```\n(【导演阐述】.*?)```", meth, re.S)
        if tpl:
            parts.append("【导演阐述模板：每次故事交付必附】\n" + tpl.group(1).strip())
    out = "\n\n".join(parts)
    return out if len(out) <= limit else out[:limit] + "\n…（已截断）"


def director_missing(d: dict | None) -> list[str]:
    d = d or {}
    return [label for key, label in DIRECTOR_FIELDS if key in DIRECTOR_REQUIRED and not str(d.get(key, "")).strip()]


def director_problems(d: dict | None) -> list[str]:
    """Required fields present and written in first person (Keven 2026-10-19: paragraph-level, 「我……」)."""
    d = d or {}
    missing = director_missing(d)
    probs = [f"导演阐述缺：{'、'.join(missing)}"] if missing else []
    not_first = [label for key, label in DIRECTOR_FIELDS
                 if key in DIRECTOR_REQUIRED and str(d.get(key, "")).strip() and "我" not in str(d.get(key, ""))]
    if not_first:
        probs.append(f"导演阐述要用第一人称导演口吻（“我……”）：{'、'.join(not_first)}")
    return probs


def project_type(brief: dict | None) -> str:
    t = (brief or {}).get("project_type")
    return t if t in PROJECT_TYPES else "original"


def tone_problems(text: str, ptype: str) -> list[str]:
    probs = []
    hits = [t for t in VIOLENCE_CLOSEUP_TERMS if t in text]
    if hits:
        probs.append(f"出现禁用的暴力特写（A2，两类项目都禁用）：{'、'.join(hits)}")
    if ptype == "brand":
        hits = [t for t in DARK_TONE_TERMS if t in text]
        if hits:
            probs.append(f"品牌片不能用暗黑／惊悚／暴力边缘调性（A14，一票否决）：{'、'.join(hits)}")
    return probs


def stance(task: str, ptype: str | None) -> str:
    lines = ["【Keven 已拍板】"]
    if ptype == "brand":
        lines.append("本项目是品牌片：禁止暗黑、惊悚、暴力边缘调性（一票否决）；刀刃抵喉、斩击特写禁用。")
    elif ptype == "original":
        lines.append("本项目是自创故事（无品牌）：可以用暗黑、惊悚、黑色幽默，但刀刃抵喉、斩击特写仍禁用。")
    else:
        lines.append("品牌片禁止暗黑、惊悚、暴力边缘调性；自创故事可以用；刀刃抵喉、斩击特写两类都禁用。")
    lines.append("不预设具体品牌；情绪基调和 AI 质感都不设限，服务于故事需求。")
    lines.append(f"现阶段成功标准是 Keven 的审美判断（过稿与否），变体假设的指标默认写「{DEFAULT_METRIC}」。")
    if task == "script":
        lines.append("导演阐述写到段落级，用第一人称导演口吻（“我想……”“我选择……”），不要写逐镜焦段参数表。")
    return "\n".join(lines)


def variants_problems(vs: list | None) -> list[str]:
    if not vs:
        return ["至少要有 1 个单变量变体"]
    probs = []
    for i, v in enumerate(vs, 1):
        miss = [label for key, label in VARIANT_FIELDS if key in VARIANT_REQUIRED and not str(v.get(key, "")).strip()]
        if miss:
            probs.append(f"变体 {i} 缺：{'、'.join(miss)}")
        if re.search(r"[，,、+＋/／]|以及|同时", str(v.get("variable", ""))):
            probs.append(f"变体 {i} 看起来改了不止一个变量")
    return probs
