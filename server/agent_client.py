"""Claude Agent SDK wrapper for this backend's four agent-backed endpoints.

Every call here is single-shot: build ClaudeAgentOptions, drive query() to
completion, collect the assistant's text (concatenated across however many
turns the run took) and usage off the terminal ResultMessage, return.

Model ID mapping matches the UI's four-option <select id="model-sel">
(sonnet-5/opus-5/opus-4-8/fable-5) onto the real API model strings
confirmed against shared/models.md (see runs/04-implement-server.md for
the verification note) - it is a fixed lookup table, not a guessed
string-format, so an unrecognized modelId can never silently mint a bad
model string.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

DEFAULT_MODEL = "claude-sonnet-5"

MODEL_MAP = {
    "sonnet-5": "claude-sonnet-5",
    "opus-5": "claude-opus-5",
    "opus-4-8": "claude-opus-4-8",
    "fable-5": "claude-fable-5",
}

# Caps on agent turns per endpoint, so a stuck loop can't spiral into a
# runaway bill. /v1/messages is a near-single-turn passthrough; the
# skill-driven endpoints get more room for research/tool calls.
MAX_TURNS_MESSAGES = 8
MAX_TURNS_EVALUATE = 20
MAX_TURNS_GENERATE = 30


def resolve_model(model_id: str | None) -> str:
    if not model_id:
        return DEFAULT_MODEL
    return MODEL_MAP.get(model_id, DEFAULT_MODEL)


@dataclass
class AgentResult:
    text: str
    input_tokens: int
    output_tokens: int


async def run_agent(prompt: str, options: ClaudeAgentOptions) -> AgentResult:
    """Drive one query() to completion; concatenate all assistant TextBlock
    text (in arrival order, across however many turns/tool calls the run
    took) and read usage off the terminal ResultMessage."""
    chunks: list[str] = []
    result: ResultMessage | None = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
        elif isinstance(message, ResultMessage):
            result = message

    usage = (result.usage if result is not None else None) or {}
    # A skill-driven run reads several project files every turn, so most
    # of "input" is served from cache - report cache_creation +
    # cache_read alongside the uncached input_tokens, or the UI's token
    # pill would badly understate what the run actually processed.
    input_tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
    )
    return AgentResult(
        text="".join(chunks),
        input_tokens=input_tokens,
        output_tokens=int(usage.get("output_tokens") or 0),
    )


# --------------------------------------------------------------------------
# JSON extraction for the structured-output endpoints (tailor / cover
# letter). Mirrors the frontend's own callClaudeJSON() salvage logic
# (job-application-assistant.html lines 737-770) so a truncated or
# fence-wrapped response degrades the same way the UI already expects.
# --------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """Best-effort extraction of a single JSON object from model output
    that may be wrapped in ```json fences and/or have leading/trailing prose.
    Raises ValueError if nothing parseable can be salvaged.

    Models often emit a short preamble before the JSON (or a fence-wrapped
    object). The original portal salvage mirrored only fence + trailing-prose
    stripping; leading prose made ``json.loads`` fail at column 0 and left
    /v1/tailor returning HTTP 200 with files=[].

    Hardened (Implement pass 2, P2-4) so a stray `{`/`[` inside the leading
    prose itself (e.g. "I will fill the {placeholder} now.") no longer gets
    mistaken for the JSON start - see the line-start opener scan below.
    Deliberately NOT hardened against the mirror-image case (a stray brace
    in *trailing* prose after the real JSON, e.g. "Note: use {curly}
    carefully."); that was never the production failure and pre-existing
    behavior there is unchanged. See runs/tests/test_extract_json.py.
    """
    clean = re.sub(r"```json\s*", "", text)
    clean = re.sub(r"```\s*", "", clean).strip()

    # Drop trailing prose after the last object/array closer.
    last_brace = clean.rfind("}")
    last_bracket = clean.rfind("]")
    last_delim = max(last_brace, last_bracket)
    if last_delim != -1:
        clean = clean[: last_delim + 1]

    # Drop leading prose before the first object/array opener. A brace or
    # bracket appearing mid-sentence in prose (e.g. "fill the {placeholder}
    # now, then...") would fool a naive first-occurrence scan and get
    # mistaken for the JSON start. Real JSON output almost always opens at
    # the start of a line (immediately after a stripped fence, or as the
    # whole response) - a stray brace in a prose sentence sits after other
    # text on that same line - so prefer the first `{`/`[` that starts its
    # own line. Fall back to the naive scan when no line-start opener
    # exists at all (e.g. a bare single-line object with no prose).
    line_opener = re.search(r"^[ \t]*([{\[])", clean, re.MULTILINE)
    if line_opener:
        clean = clean[line_opener.start(1) :].strip()
    else:
        first_brace = clean.find("{")
        first_bracket = clean.find("[")
        candidates = [i for i in (first_brace, first_bracket) if i != -1]
        if candidates:
            clean = clean[min(candidates) :].strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Salvage: close any structures left open by a truncated response.
    s = re.sub(r",\s*$", "", clean)
    braces = brackets = 0
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            braces += 1
        elif ch == "}":
            braces -= 1
        elif ch == "[":
            brackets += 1
        elif ch == "]":
            brackets -= 1
    s = s + ("]" * max(0, brackets)) + ("}" * max(0, braces))
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse JSON from agent output: {e}") from e
