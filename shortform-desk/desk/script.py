"""Script JSON schema + validation. The human edits this file and sets "approved": true."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Shot:
    vo: str
    screen_text: str = ""
    visual: str = ""
    palette: str = ""
    min_sec: float = 0.0


@dataclass
class Script:
    title: str
    shots: list[Shot]
    approved: bool = False
    platform: str | None = None
    voice: str | None = None
    meta: dict = field(default_factory=dict)


def load_script(path: Path) -> Script:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    shots_raw = raw.get("shots") or []
    if not raw.get("title") or not shots_raw:
        raise SystemExit(f"{path}: script needs 'title' and a non-empty 'shots' list")
    shots = []
    for i, s in enumerate(shots_raw, 1):
        if not str(s.get("vo", "")).strip():
            raise SystemExit(f"{path}: shot {i} has empty 'vo'")
        shots.append(
            Shot(
                vo=s["vo"].strip(),
                screen_text=s.get("screen_text", "").strip(),
                visual=s.get("visual", "").strip(),
                palette=s.get("palette", ""),
                min_sec=float(s.get("min_sec", 0)),
            )
        )
    return Script(
        title=raw["title"],
        shots=shots,
        approved=bool(raw.get("approved", False)),
        platform=raw.get("platform"),
        voice=raw.get("voice"),
        meta={k: v for k, v in raw.items() if k not in {"title", "shots", "approved", "platform", "voice"}},
    )
