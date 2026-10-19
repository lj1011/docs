"""desk CLI: ideas -> (human picks) -> draft -> (human edits + approves) -> render."""

import argparse
import json
from pathlib import Path

from .platforms import PLATFORMS


def _dump(data: dict, out: str) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="desk")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ideas", help="brief.json -> 10 idea candidates")
    a.add_argument("brief")
    a.add_argument("-o", "--out", default="out/ideas.json")

    d = sub.add_parser("draft", help="ideas.json + your pick -> script draft (approved=false)")
    d.add_argument("ideas")
    d.add_argument("--pick", type=int, required=True, help="1-based idea number you chose")
    d.add_argument("-o", "--out", default="out/script.json")

    r = sub.add_parser("render", help="approved script.json -> vertical mp4")
    r.add_argument("script")
    r.add_argument("-o", "--out", default="out/video.mp4")
    r.add_argument("--platform", choices=list(PLATFORMS), help="overrides script.platform")
    r.add_argument("--tts", default="auto", choices=["auto", "edge", "openai", "silent"])
    r.add_argument("--visual", default="auto", choices=["auto", "card", "openai"])
    r.add_argument("--bgm", help="audio file, or 'auto' for a generated placeholder pad")

    sub.add_parser("platforms", help="list format packs")

    s = sub.add_parser("serve", help="local web desk: brief -> ideas -> story -> approve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)

    args = ap.parse_args(argv)
    if args.cmd == "ideas":
        from .llm import generate_ideas

        brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
        if not str(brief.get("brief", "")).strip():
            raise SystemExit("brief.json needs a non-empty 'brief' field")
        data = generate_ideas(brief)
        _dump(data, args.out)
        for i, idea in enumerate(data["ideas"], 1):
            print(f"{i:2d}. [{idea.get('format', '')}] {idea['hook']}")
        print(f"\nPick one: python -m desk draft {args.out} --pick N")
    elif args.cmd == "draft":
        from .llm import draft_script

        ideas = json.loads(Path(args.ideas).read_text(encoding="utf-8"))
        _dump(draft_script(ideas, args.pick), args.out)
        print(f'Review/edit {args.out}, set "approved": true, then: python -m desk render {args.out}')
    elif args.cmd == "render":
        from .render import render
        from .script import load_script

        script = load_script(Path(args.script))
        if not script.approved:
            raise SystemExit(f'{args.script} is not approved. A human must review it and set "approved": true.')
        report = render(script, Path(args.out), platform_id=args.platform, tts_name=args.tts,
                        visual_name=args.visual, bgm=args.bgm)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.cmd == "serve":
        from .server import serve

        serve(args.host, args.port)
    elif args.cmd == "platforms":
        for p in PLATFORMS.values():
            print(f"{p.id:9s} {p.label:18s} {p.width}x{p.height} {p.min_sec:g}-{p.max_sec:g}s  caption<={p.max_caption_chars}")


if __name__ == "__main__":
    main()
