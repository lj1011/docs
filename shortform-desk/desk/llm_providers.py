"""Pluggable LLM providers returning JSON. Pick with DESK_LLM, else the first key found in env.

  openai     OPENAI_API_KEY   [OPENAI_BASE_URL for DeepSeek/Qwen/Moonshot/...]  [OPENAI_MODEL]
  anthropic  ANTHROPIC_API_KEY                                                   [ANTHROPIC_MODEL]
  mock       no key: deterministic offline templates (demo only)
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def provider() -> dict:
    name = os.environ.get("DESK_LLM")
    if not name:
        if os.environ.get("OPENAI_API_KEY"):
            name = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            name = "anthropic"
        else:
            name = "mock"
    if name == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        return {"name": "openai", "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "base_url": base}
    if name == "anthropic":
        return {"name": "anthropic", "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")}
    return {"name": "mock", "model": "offline-templates"}


def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from e


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def chat_json(system: str, user: str) -> dict:
    p = provider()
    if p["name"] == "openai":
        body = {
            "model": p["model"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
        try:
            data = _post(f"{p['base_url']}/chat/completions", body, headers)
        except RuntimeError as e:
            if "response_format" not in str(e):
                raise
            body.pop("response_format")
            data = _post(f"{p['base_url']}/chat/completions", body, headers)
        return _parse_json(data["choices"][0]["message"]["content"])
    if p["name"] == "anthropic":
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"model": p["model"], "max_tokens": 4096, "system": system, "messages": [{"role": "user", "content": user}]},
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        )
        return _parse_json("".join(b.get("text", "") for b in data["content"]))
    raise RuntimeError("mock provider has no chat endpoint")


def run_prompt(task: str, variables: dict) -> dict:
    """Fill prompts/<task>.md with {{var}} values and ask the active provider for JSON."""
    system = (PROMPTS / "system.md").read_text(encoding="utf-8")
    tpl = (PROMPTS / f"{task}.md").read_text(encoding="utf-8")
    for k, v in variables.items():
        tpl = tpl.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
    return chat_json(system, tpl)
