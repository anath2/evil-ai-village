"""Action parsing for the text JSON protocol."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .prompts import ACTION_CLOSE, ACTION_OPEN

_ARG_KEYS = {"command", "text", "path", "note", "summary", "limit", "message", "file", "cmd"}

KNOWN_TOOLS = {
    "bash",
    "read_board",
    "post_message",
    "submit_poc",
    "consolidate_memory",
    "recall",
    "reflect",
    "finish",
}


@dataclass
class Action:
    tool: str
    input: dict = field(default_factory=dict)
    raw: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.tool)


_THINK_RE = re.compile(
    r"<(thinking|reasoning|scratchpad|analysis)>.*?</\1>", re.S | re.I
)


def _strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text or "")


def _find_action_object(text: str) -> dict | None:
    """Return the last balanced JSON object that carries a tool indicator."""
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in reversed(starts):
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict) and any(
                        k in obj for k in ("tool", "name", "action")
                    ):
                        return obj
                    break
    return None


def _tagged_tool(text: str) -> Action | None:
    """Handle <bash>{...}</bash> / <tool>...</tool> style wrappers.

    Some strong models (seen with deepseek-v3.2) ignore the requested format and
    emit an XML-ish tool wrapper around the JSON args instead of a `tool` key.
    """
    m = re.search(r"<([a-z_]+)>\s*(\{.*?\})\s*</\1>", text, re.S)
    if m and m.group(1) in KNOWN_TOOLS:
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            return None
        if not isinstance(args, dict):
            return None
        return Action(tool=m.group(1), input=args, raw=text)
    return None


def _extract_json(text: str) -> dict | None:
    m = re.search(re.escape(ACTION_OPEN) + r"\s*(.*?)\s*" + re.escape(ACTION_CLOSE), text, re.S)
    if m:
        candidate = m.group(1)
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        inner = _find_action_object(candidate)
        if inner is not None:
            return inner
    return _find_action_object(text)


def parse_action(text: str) -> Action:
    text = text or ""
    cleaned = _strip_thinking(text)
    tagged = _tagged_tool(cleaned)
    if tagged is not None:
        return tagged
    obj = _extract_json(cleaned)
    if not isinstance(obj, dict):
        return Action(tool="", raw=text or "")
    tool = obj.get("tool") or obj.get("name") or obj.get("action") or ""
    tool = str(tool).strip().lower()
    inp = obj.get("input") or obj.get("args") or obj.get("arguments") or obj.get("parameters")
    if not isinstance(inp, dict):
        inp = {}
    if not inp:
        # Tolerate {"tool":"bash","command":"..."}.
        inp = {k: v for k, v in obj.items() if k in _ARG_KEYS}
    # Normalize common aliases.
    if tool == "bash" and "command" not in inp and "cmd" in inp:
        inp["command"] = inp["cmd"]
    if tool == "post_message" and "text" not in inp and "message" in inp:
        inp["text"] = inp["message"]
    if tool == "submit_poc" and "path" not in inp and "file" in inp:
        inp["path"] = inp["file"]
    return Action(tool=tool, input=inp, raw=text or "")


def action_format_error(text: str) -> str:
    """Explain a format failure without repairing or executing guessed content."""
    cleaned=_strip_thinking(text or "").strip()
    match=re.search(re.escape(ACTION_OPEN)+r"\s*(.*?)\s*"+re.escape(ACTION_CLOSE),cleaned,re.S)
    candidate=match.group(1) if match else cleaned
    try:
        json.loads(candidate)
    except json.JSONDecodeError as exc:
        return (f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
                "Close both the input object and the outer action object, and use valid JSON string escaping.")
    return "The action object must include a tool name and an input object."
