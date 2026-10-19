"""Offline mock generators so the desk is demoable without any LLM key. Output is template-based, not creative."""

import random

IDEA_TEMPLATES = [
    ("口播", "关于{t}，90%的人第一步就错了", "纠正一个普遍误区", "替观众指出错误，自带停留", "S16"),
    ("清单", "3个{t}的小动作，今天就能用", "可立即照做的清单", "实用、易收藏", "S08"),
    ("反转", "我试了7天{t}，结果和想的完全相反", "个人实验 + 反转结论", "结果悬念拉完播", "S02"),
    ("对比", "{a}做{t}：新手 vs 老手，差在哪", "前后/高低对比", "对比结构一眼看懂", "S11"),
    ("演示", "30秒演示：{t}到底怎么做", "手把手演示", "看完就会，信任感强", "S13"),
    ("故事", "那天我差点放弃{t}，直到……", "一个小故事带出方法", "情绪带入，完播高", "S04"),
    ("口播", "别再这样{t}了，真的很亏", "反常识的禁止句", "强指令开头抓人", "S09"),
    ("清单", "{a}必看：{t}避坑清单", "避坑角度", "怕踩坑是刚需", "S16"),
    ("反转", "所有人都说{t}要这样，其实不用", "挑战常识", "反直觉引发评论", "S09"),
    ("对比", "花1块钱和花100块钱{t}，差别大吗", "价格/成本对比", "好奇心 + 讨论度", "S15"),
    ("演示", "一镜到底，带你看{t}的全过程", "完整过程展示", "沉浸感，适合循环看", "S02"),
    ("故事", "我朋友用这个办法搞定了{t}", "第三人称案例", "可信又不说教", "S03"),
    ("口播", "{t}这件事，只需要记住一句话", "极简结论", "短、狠、好转发", "S01"),
    ("清单", "{t}从0到1的5个步骤", "步骤拆解", "结构清楚，适合收藏", "S08"),
    ("反转", "我以为{t}很难，直到看到这个", "认知翻转", "惊喜感驱动转发", "S15"),
    ("对比", "一周前 vs 一周后：坚持{t}的变化", "时间对比", "结果可视化", "S02"),
]
VARIANT_PREFIX = ["换个场景：", "换个例子：", "更狠一点：", "更温柔一点：", "反着说："]


ANCHORS = [
    ("一个红色{obj}在每个场景里都出现", "#01"),
    ("全片只用一种主色：{color}，人物衣服和道具都跟着走", "#07"),
    ("主角从头到尾穿同一件高辨识外套", "#13"),
    ("三种颜色的小物件定下色板，结尾汇成一处", "#05"),
]
OBJS = ["闹钟", "杯子", "便签", "钥匙扣"]
COLORS = ["暖橙", "薄荷绿", "雾蓝", "樱桃红"]
SKELETON_CARDS = {"S01": "#01", "S02": "#03", "S03": "#04", "S04": "#05", "S08": "#09", "S09": "#10",
                  "S11": "#12", "S13": "#14", "S15": "#17", "S16": "#18"}


def _idea(hook, angle, fmt, why, sk, t, i) -> dict:
    anchor, card = ANCHORS[i % len(ANCHORS)]
    return {"hook": hook, "angle": angle, "format": fmt, "why": why, "skeleton": sk,
            "visual_anchor": anchor.format(obj=OBJS[i % 4], color=COLORS[i % 4]) + "（推断）",
            "cards": sorted({SKELETON_CARDS.get(sk, "#01"), card})}


def _topic(brief: dict) -> tuple[str, str]:
    return (brief.get("topic") or "这件事").strip(), (brief.get("audience") or "普通人").strip()


def ideas(brief: dict, count: int, existing_hooks: set[str], seed: int) -> list[dict]:
    t, a = _topic(brief)
    rng = random.Random(seed)
    pool = IDEA_TEMPLATES[:]
    rng.shuffle(pool)
    out = []
    for fmt, hook, angle, why, sk in pool:
        h = hook.format(t=t, a=a)
        if h in existing_hooks:
            continue
        out.append(_idea(h, angle, fmt, why, sk, t, len(out)))
        if len(out) == count:
            break
    i = 0
    while len(out) < count:
        fmt, hook, angle, why, sk = pool[i % len(pool)]
        out.append(_idea(f"{VARIANT_PREFIX[i % 5]}{hook.format(t=t, a=a)}", angle, fmt, why, sk, t, i))
        i += 1
    return out


def more_like(idea: dict, count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    prefixes = VARIANT_PREFIX[:]
    rng.shuffle(prefixes)
    return [
        {"hook": f"{prefixes[i % 5]}{idea['hook']}", "angle": idea["angle"], "format": idea["format"],
         "why": f"延续「{idea['hook'][:10]}…」的路子；{idea['why']}", "skeleton": idea.get("skeleton", ""),
         "visual_anchor": idea.get("visual_anchor", ""), "cards": idea.get("cards", [])}
        for i in range(count)
    ]


def remix(a: dict, b: dict, count: int) -> list[dict]:
    cards = sorted(set(a.get("cards", [])) | set(b.get("cards", [])))
    out = [{"hook": a["hook"], "angle": f"{b['angle']}（借 B 的角度）", "format": b["format"],
            "why": f"A 的钩子 + B 的结构：{a['why']}；{b['why']}", "skeleton": b.get("skeleton", ""),
            "visual_anchor": a.get("visual_anchor", ""), "cards": cards},
           {"hook": b["hook"], "angle": f"{a['angle']}（借 A 的角度）", "format": a["format"],
            "why": f"B 的钩子 + A 的结构：{b['why']}；{a['why']}", "skeleton": a.get("skeleton", ""),
            "visual_anchor": b.get("visual_anchor", ""), "cards": cards}]
    return out[:count]


BEAT_ALTS = {
    "hook": ["{h}", "先问你一个问题：{h}？", "如果你也{t}失败过，听我说完这30秒。"],
    "turn": ["但真正的问题不在努力，而在{angle}。", "很多人以为要靠坚持，其实关键是{angle}。", "直到我换了个思路：{angle}。"],
    "payoff": ["记住三点：第一，从最小的一步开始；第二，把它放进固定的时间；第三，做完给自己一个小奖励。",
               "具体做法很简单：先只做五分钟，做到了就打个勾，连续三天再加量。",
               "我的结果是：一周之后，{t}从负担变成了习惯。"],
    "cta": ["你在{t}上踩过什么坑？评论区说说。", "觉得有用就收藏，明天照着做。", "关注我，下一条讲进阶版。"],
}


def beat(key: str, idea: dict, brief: dict, variant: int) -> str:
    t, _ = _topic(brief)
    alts = BEAT_ALTS[key]
    return alts[variant % len(alts)].format(h=idea["hook"].rstrip("？?"), t=t, angle=idea["angle"])


def outline(idea: dict, brief: dict, variant: int = 0) -> dict:
    return {k: beat(k, idea, brief, variant) for k in ("hook", "turn", "payoff", "cta")}


def script(beats: dict, idea: dict, brief: dict, skeleton: dict | None = None) -> dict:
    t, _ = _topic(brief)
    shots = [{"beat": "hook", "vo": beats["hook"], "screen_text": idea["hook"][:10], "visual": f"特写：和{t}相关的日常场景，人物略显困扰"},
             {"beat": "turn", "vo": beats["turn"], "screen_text": "问题不在努力", "visual": "人物停下动作，若有所思，光线变化"}]
    parts = [p for p in beats["payoff"].replace("；", "。").split("。") if p.strip()]
    for i, p in enumerate(parts[:4]):
        shots.append({"beat": "payoff", "vo": p.strip() + "。", "screen_text": p.strip().split("，")[-1][:10],
                      "visual": f"演示镜头 {i + 1}：具体动作的近景"})
    shots.append({"beat": "cta", "vo": beats["cta"], "screen_text": "你怎么看？", "visual": "人物看向镜头微笑，温暖色调"})
    anchor = idea.get("visual_anchor") or "待补"
    sk = f"{skeleton['id']} {skeleton['name']}" if skeleton else "未指定骨架"
    cards = "、".join(idea.get("cards") or []) or "待补"
    director = {
        "intent": f"让观众相信：{idea['angle']}。规则一句话：{idea['hook']}（推断，离线模板生成）",
        "anchor": f"{anchor}；在第 1、{len(shots) // 2 + 1}、{len(shots)} 镜出现。",
        "camera_light_rhythm": "开场近景压迫，转折处机位不动只换环境；色板限 3 色；兑现段每镜一个动作，CTA 前停格 1 秒（推断）。",
        "hypothesis": f"骨架 {sk} 能让 {brief.get('duration_sec', 30)} 秒内完成「问题→反转→兑现」；如果盲评觉得转折不成立，先改转折这一拍。",
        "borrowed": f"借 {cards} 的机制，只借结构；不借原片音乐、HUD、画面。",
        "unknowns": "品牌信息、配乐、表现数据：待补。本阐述由离线模板生成，接入模型后会更具体。",
    }
    variants = [
        {"variable": "停格有无", "change": "从「CTA 前停格 1 秒」改成「不停格」",
         "hypothesis": "去掉停格后完播率不变或下降", "falsify": "若去掉停格后完播率明显上升，则「停格有用」不成立", "metric": "完播率（待 Keven 确认）"},
        {"variable": "钩子位置", "change": "从「顺叙」改成「结果前置到前 3 秒」",
         "hypothesis": "结果前置后 3 秒留存上升", "falsify": "若 3 秒留存没有上升，则假设不成立", "metric": "3 秒留存（待补）"},
    ]
    return {"title": idea["hook"], "shots": shots, "director": director, "variants": variants}
