"""Local web desk: stdlib HTTP server + JSON API over desk.ideation. `python -m desk serve`."""

import json
import mimetypes
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import guidelines as G
from . import ideation as ide
from . import llm_providers as llm
from .util import run

WEB = Path(__file__).resolve().parent / "web"
_renders: dict[str, dict] = {}

SETUP_HINT = (
    "离线演示模式（MOCK）：点子和脚本来自模板，不是 AI。接入真模型，任选其一后重启：\n"
    "  OPENAI_API_KEY=sk-...                     # OpenAI\n"
    "  OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.deepseek.com/v1 OPENAI_MODEL=deepseek-chat  # 兼容接口\n"
    "  ANTHROPIC_API_KEY=...                     # Anthropic"
)


def _render_job(pid: str) -> None:
    from .render import render
    from .script import load_script

    try:
        video = ide.DATA / pid / "video.mp4"
        report = render(load_script(ide.script_path(pid)), video, bgm="auto")
        run(["ffmpeg", "-y", "-ss", str(min(3.0, report["duration_sec"] / 2)), "-i", str(video),
             "-frames:v", "1", "-vf", "scale=540:-1", str(video.with_name("poster.jpg"))])
        _renders[pid] = {"status": "done", "report": report}
    except Exception as e:  # surfaced to the UI
        _renders[pid] = {"status": "error", "error": str(e)[-800:]}


ROUTES = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return deco


@route("GET", "/api/status")
def status(body):
    p = llm.provider()
    return {"llm": p, "mock": p["name"] == "mock", "hint": SETUP_HINT if p["name"] == "mock" else "", "data": str(ide.DATA)}


@route("GET", "/api/guidelines")
def guidelines(body):
    g = G.load()
    return {**G.meta(), "exists": g["exists"], "skeletons": g["skeletons"], "questions": g["questions"],
            "thresholds": g["thresholds"], "director_fields": G.DIRECTOR_FIELDS, "director_required": G.DIRECTOR_REQUIRED,
            "variant_fields": G.VARIANT_FIELDS, "variant_required": G.VARIANT_REQUIRED, "markdown": g["text"]}


@route("GET", "/api/projects")
def projects(body):
    return {"projects": ide.list_projects()}


@route("POST", "/api/projects")
def create(body):
    return ide.create_project(body)


@route("GET", "/api/projects/(\\w+)")
def get(body, pid):
    p = ide.load(pid)
    p["render"] = _renders.get(pid)
    for v in p["story"]["versions"]:
        v["score_summary"] = ide.score_summary(v)
    return p


@route("PUT", "/api/projects/(\\w+)/brief")
def brief(body, pid):
    return ide.update_brief(pid, body)


@route("POST", "/api/projects/(\\w+)/ideas")
def ideas(body, pid):
    return ide.generate_ideas(pid, int(body.get("count", 10)))


@route("POST", "/api/projects/(\\w+)/remix")
def remix(body, pid):
    return ide.remix(pid, body.get("a", ""), body.get("b", ""))


@route("POST", "/api/projects/(\\w+)/ideas/(\\w+)/more")
def more(body, pid, iid):
    return ide.more_like(pid, iid)


@route("POST", "/api/projects/(\\w+)/ideas/(\\w+)/(star|reject|restore|edit|pick)")
def idea_action(body, pid, iid, action):
    return ide.idea_action(pid, iid, action, body)


@route("POST", "/api/projects/(\\w+)/outline")
def outline(body, pid):
    return ide.generate_outline(pid)


@route("POST", "/api/projects/(\\w+)/beats/(\\w+)")
def beat(body, pid, key):
    return ide.regen_beat(pid, key, body.get("note", ""))


@route("POST", "/api/projects/(\\w+)/script")
def script(body, pid):
    return ide.generate_script(pid)


@route("PUT", "/api/projects/(\\w+)/story")
def edit(body, pid):
    return ide.edit_version(pid, body)


@route("POST", "/api/projects/(\\w+)/story/active")
def active(body, pid):
    return ide.set_active(pid, body.get("id", ""))


@route("POST", "/api/projects/(\\w+)/approve")
def approve(body, pid):
    return ide.approve(pid)


@route("POST", "/api/projects/(\\w+)/unapprove")
def unapprove(body, pid):
    _renders.pop(pid, None)
    return ide.unapprove(pid)


@route("POST", "/api/projects/(\\w+)/render")
def render(body, pid):
    p = ide.load(pid)
    if not p["story"]["approved"] or not ide.script_path(pid).exists():
        raise ide.DeskError("先批准脚本才能渲染")
    if _renders.get(pid, {}).get("status") != "running":
        _renders[pid] = {"status": "running"}
        threading.Thread(target=_render_job, args=(pid,), daemon=True).start()
    return {"render": _renders[pid]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, data: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?")[0]
        if method == "GET" and not path.startswith("/api/"):
            return self._static(path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid JSON"})
        for m, rx, fn in ROUTES:
            match = rx.match(path)
            if m == method and match:
                try:
                    return self._json(200, fn(body, *match.groups()))
                except ide.DeskError as e:
                    return self._json(400, {"error": str(e)})
                except Exception as e:
                    traceback.print_exc()
                    return self._json(500, {"error": f"{type(e).__name__}: {e}"[:800]})
        self._json(404, {"error": "not found"})

    def _static(self, path: str) -> None:
        m = re.match(r"^/files/(\w+)/(video\.mp4|poster\.jpg|script\.json)$", path)
        if m:
            f = ide.DATA / m.group(1) / m.group(2)
        else:
            f = (WEB / (path.lstrip("/") or "index.html")).resolve()
            if WEB not in f.parents and f != WEB:
                return self._json(403, {"error": "forbidden"})
            if not f.is_file():
                f = WEB / "index.html"
        if not f.is_file():
            return self._json(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    p = llm.provider()
    print(f"创意桌 running at http://{host}:{port}  (LLM: {p['name']} / {p['model']})")
    if p["name"] == "mock":
        print(SETUP_HINT)
    print(f"data: {ide.DATA}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
