"""Local HTTP server for the AI Job Assistant browser app.

Implements the exact `/v1/*` contract the shipped frontend
(job-application-assistant.html) already calls at http://127.0.0.1:8787 -
see runs/01-read-frontend.md (line numbers) and runs/03-plan.md for the
envelope shapes this was built against.

Run directly:
    python main.py
or:
    uvicorn main:app --host 127.0.0.1 --port 8787
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

import agent_client
import docx_render
import instances
from claude_agent_sdk import ClaudeAgentOptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jaa-backend")

app = FastAPI(title="AI Job Assistant local backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_body(message: str) -> dict:
    # Matches the shape every frontend call site reads on failure:
    # err.error?.message (job-application-assistant.html, e.g. line 675).
    return {"error": {"message": message}}


# ==========================================================================
# 0. Frontend + non-model endpoints
# ==========================================================================

@app.get("/")
def serve_frontend():
    if not instances.FRONTEND_HTML.is_file():
        return JSONResponse(error_body("Frontend HTML not found"), status_code=404)
    # No-store: this file changes constantly during development, and without
    # an explicit directive here a browser applies heuristic caching to a
    # plain FileResponse (which only carries Last-Modified/ETag) and can
    # serve a stale copy on an ordinary reload without ever asking the
    # server again - silently undoing every edit until a hard refresh.
    return FileResponse(
        instances.FRONTEND_HTML,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/favicon.ico")
def favicon():
    # No icon asset shipped; a bare 204 stops the browser's automatic
    # request from logging a 404 on every page load (P3, cosmetic only).
    return Response(status_code=204)


class UsersRequest(BaseModel):
    name: str


@app.post("/v1/users")
def create_user(body: UsersRequest):
    try:
        instance_id = instances.create_instance(body.name or "")
    except instances.BackendDependencyMissing as e:
        # Turns a would-be silent "empty skill folder, fails weirdly deep
        # inside a later AI call" (or, before this endpoint existed, an
        # unhandled 500 with a raw stack trace) into one clear, actionable
        # error at the earliest possible point - profile creation, before
        # anything else about this instance is even attempted.
        logger.error("v1/users: backend dependency missing: %s", e)
        return JSONResponse(error_body(str(e)), status_code=503)
    return {"id": instance_id}


class ProfileRequest(BaseModel):
    instanceId: str
    name: Optional[str] = None
    outputFormat: Optional[str] = None
    sections: Optional[dict[str, Any]] = None
    rawText: Optional[str] = None


@app.post("/v1/profile")
async def update_profile(body: ProfileRequest):
    lock = instances.get_lock(body.instanceId)
    async with lock:
        try:
            instances.write_profile(
                body.instanceId,
                name=body.name,
                outputFormat=body.outputFormat,
                sections=body.sections,
                rawText=body.rawText,
            )
        except instances.InstanceNotFound:
            return JSONResponse(error_body("Unknown instanceId"), status_code=404)
    return {"ok": True}


@app.delete("/v1/users/{instance_id}")
async def delete_user(instance_id: str):
    # Round 8 Pass 2: the one new backend endpoint this feature needed -
    # Copy/Merge could be built entirely by replaying already-client-side
    # CV Info content through the EXISTING POST /v1/users + POST /v1/profile
    # calls (see the frontend's copyProfile/performMerge), but nothing
    # existing could remove an instance's workspace directory. Reuses the
    # same per-instance lock every other instance-scoped handler uses (so a
    # delete can't race an in-flight evaluate/tailor/cover-letter call
    # against the same instance) and instances.delete_instance's own
    # path-safety discipline - never trust instance_id alone, always
    # re-confirm the resolved path is genuinely inside INSTANCES_DIR before
    # the destructive shutil.rmtree.
    lock = instances.get_lock(instance_id)
    async with lock:
        try:
            instances.delete_instance(instance_id)
        except instances.InstanceNotFound:
            return JSONResponse(error_body("Unknown instanceId"), status_code=404)
        except instances.PathEscapeError:
            return JSONResponse(error_body("Invalid instanceId"), status_code=400)
    return {"ok": True}


@app.get("/v1/files")
def get_file(instanceId: str, path: str):
    try:
        resolved = instances.resolve_output_path(instanceId, path)
    except instances.InstanceNotFound:
        return JSONResponse(error_body("Unknown instanceId"), status_code=404)
    except instances.PathEscapeError:
        return JSONResponse(error_body("Invalid path"), status_code=400)
    except FileNotFoundError:
        return JSONResponse(error_body("File not found"), status_code=404)

    # Real per-extension MIME type, not a generic "application/octet-stream" -
    # the browser's Blob (built from this response in downloadGeneratedFile())
    # inherits this header as its `type`, and a generic binary type is treated
    # with more download/open suspicion by Chrome and Windows than the file's
    # real, recognized document type.
    guessed_type, _ = mimetypes.guess_type(resolved.name)
    return FileResponse(
        resolved,
        filename=resolved.name,
        media_type=guessed_type or "application/octet-stream",
    )


# ==========================================================================
# 1. POST /v1/messages - Agent SDK single-shot passthrough (no skills)
# ==========================================================================

class MessagesRequest(BaseModel):
    modelId: Optional[str] = None
    max_tokens: Optional[int] = 1000
    system: Optional[str] = None
    messages: list[dict[str, Any]]
    tools: Optional[list[dict[str, Any]]] = None


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # Defensive: if content ever arrives as Anthropic-style blocks
            # instead of a plain string, join any text blocks.
            return "\n".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
    return ""


@app.post("/v1/messages")
async def messages_passthrough(body: MessagesRequest):
    model = agent_client.resolve_model(body.modelId)
    prompt = _last_user_text(body.messages)

    wants_web_search = bool(
        body.tools and any(t.get("type") == "web_search_20250305" for t in body.tools)
    )
    allowed_tools = ["WebSearch", "WebFetch"] if wants_web_search else []

    system_prompt = body.system or ""
    if body.max_tokens:
        system_prompt = (
            f"{system_prompt}\n\n(Keep your response concise - aim for well under "
            f"{body.max_tokens} tokens.)"
        ).strip()

    options = ClaudeAgentOptions(
        cwd=str(instances.SERVER_DIR),
        model=model,
        permission_mode="bypassPermissions",
        allowed_tools=allowed_tools,
        disallowed_tools=[],
        max_turns=agent_client.MAX_TURNS_MESSAGES,
        system_prompt=system_prompt,
        setting_sources=None,  # deliberate: a generic call must not load repo skills
        add_dirs=[],
        agents=None,
        skills=None,
        env={},
        betas=[],
        mcp_servers={},
        plugins=[],
    )

    try:
        result = await agent_client.run_agent(prompt, options)
    except Exception as e:
        logger.exception("v1/messages failed")
        return JSONResponse(error_body(str(e)), status_code=502)

    return {
        "content": [{"type": "text", "text": result.text}],
        "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
    }


# ==========================================================================
# 2. POST /v1/evaluate - skill-driven job-fit evaluation
# ==========================================================================

class EvaluateRequest(BaseModel):
    instanceId: str
    modelId: Optional[str] = None
    jobPosting: str


EVALUATE_PROMPT = """\
You are running ONLY Step 1 (job-fit evaluation) of the job-application-assistant \
skill in this project - do not tailor a CV, do not write a cover letter, and do not \
create, edit, or write any files. This is a single, non-interactive run: do not ask \
clarifying questions, make reasonable assumptions and note them in your answer instead.

Read the candidate's profile from \
.claude/skills/job-application-assistant/01-candidate-profile.md (and \
02-behavioral-profile.md for culture/behavioral fit in the same folder). If that \
profile looks thin, also check profile/raw-cv.txt for the candidate's original CV text.

Evaluate the job posting below against that profile using the scoring framework in \
.claude/skills/job-application-assistant/04-job-evaluation.md. You may briefly \
research the company via WebFetch/WebSearch if it would meaningfully improve the \
evaluation (culture fit, recent news) - keep this quick, this is a single request \
with a limited turn budget.

Write your full evaluation using the "Output Format" template from \
04-job-evaluation.md (the "## Job Fit Evaluation: ..." markdown structure with the \
scoring table, verdict, strengths, gaps, recommendation, and company research \
checklist) - no preamble, no meta-commentary about what you're about to do. This \
becomes the "markdown" field in the JSON response described below, verbatim, so it \
must be complete and self-contained.

Then, for the SAME gaps you just listed in that report's "Gaps to Address" section \
(or equivalent), also produce a separate structured "gaps" list: one entry per gap, \
each paired with 2-4 concrete, actionable strategies for how the candidate could \
address or frame that gap - not just a restatement of the problem, but real \
directions the candidate could choose between (e.g. "pursue the certification before \
applying", "reframe adjacent experience X as a transferable equivalent", "address it \
head-on in the cover letter with honest context"). If your evaluation found no real \
gaps worth discussing, "gaps" must be an empty array.

<job_posting>
{job_posting}
</job_posting>

Respond with ONLY a raw JSON object - no markdown code fences, no prose before or \
after. Use exactly this shape ("markdown" is a single string holding the ENTIRE \
report above verbatim, with newlines escaped as "\\n"; "gaps" is an array, empty if \
there are no real gaps; "strategies" has 2-4 short strings per gap):

{{"markdown":"## Job Fit Evaluation: ...(the full report, as one string)...",\
"gaps":[{{"gap":"short description of the gap","strategies":["concrete strategy 1",\
"concrete strategy 2","concrete strategy 3"]}}]}}
"""


@app.post("/v1/evaluate")
async def evaluate(body: EvaluateRequest):
    lock = instances.get_lock(body.instanceId)
    async with lock:
        try:
            instance_dir = instances.instance_path(body.instanceId)
        except instances.InstanceNotFound:
            return JSONResponse(error_body("Unknown instanceId"), status_code=404)

        model = agent_client.resolve_model(body.modelId)
        prompt = EVALUATE_PROMPT.format(job_posting=body.jobPosting or "")

        options = ClaudeAgentOptions(
            cwd=str(instance_dir),
            model=model,
            permission_mode="bypassPermissions",
            allowed_tools=["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Skill", "Bash"],
            disallowed_tools=["Write", "Edit", "NotebookEdit", "AskUserQuestion"],
            max_turns=agent_client.MAX_TURNS_EVALUATE,
            system_prompt={"type": "preset", "preset": "claude_code"},
            setting_sources=["project"],
            add_dirs=[str(instances.CLONE_DIR)],
            agents=None,
            skills=None,
            env={},
            betas=[],
            mcp_servers={},
            plugins=[],
        )

        try:
            result = await agent_client.run_agent(prompt, options)
        except Exception as e:
            logger.exception("v1/evaluate failed")
            return JSONResponse(error_body(str(e)), status_code=502)

        # Same "agent returns JSON, server extracts it" pattern as
        # /v1/tailor and /v1/cover-letter (reusing the already-hardened
        # agent_client.extract_json - no new parsing logic). Must degrade
        # gracefully: if the model didn't comply, or wrapped the JSON
        # oddly, fall back to today's behavior (result.text is the
        # markdown, no gaps) rather than hard-failing the evaluation just
        # because the new gaps extraction didn't parse.
        markdown_text = result.text
        gaps: list[dict] = []
        try:
            data = agent_client.extract_json(result.text)
            markdown_text = data.get("markdown") or result.text
            gaps = data.get("gaps") or []
        except Exception as e:
            logger.warning("v1/evaluate: could not parse structured gaps output: %s", e)

    return {
        "content": [{"type": "text", "text": markdown_text}],
        "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
        "gaps": gaps,
    }


# ==========================================================================
# 3. POST /v1/tailor and POST /v1/cover-letter
#    Agent returns structured JSON only; docx_render renders the file.
#    The agent NEVER writes document code (Write/Edit are disallowed).
# ==========================================================================

class GenerateRequest(BaseModel):
    instanceId: str
    modelId: Optional[str] = None
    jobPosting: str
    company: Optional[str] = None
    role: Optional[str] = None
    outputFormat: Optional[str] = None
    notes: Optional[str] = None


TAILOR_PROMPT = """\
You are running Step 2 (CV tailoring) of the job-application-assistant skill in this \
project, adapted for this backend: you must NEVER write, edit, or create any files, \
and you must NEVER produce LaTeX or any document markup. Instead, respond with \
structured JSON only, which a separate renderer turns into the actual document. \
This is a single, non-interactive run - do not ask clarifying questions; make \
reasonable judgment calls and note any assumptions in the "summary" field instead.

Read the candidate's profile from \
.claude/skills/job-application-assistant/01-candidate-profile.md (and \
profile/raw-cv.txt as a fallback if the structured profile looks thin or \
placeholder-only). Follow the tailoring guidance in \
.claude/skills/job-application-assistant/05-cv-templates.md (profile statement, \
skills reordering, experience bullet emphasis, section order) and the honesty rules \
below - adapt the CONTENT of each region, not a LaTeX template.

HONESTY IS NON-NEGOTIABLE. Three categories of content:
1. Source-verified - directly stated in the candidate's profile. Always safe to include.
2. Plausibly transferable - a reasonable inference from their background. Flag this \
in the "summary" field.
3. Fabricated - no basis in the profile. NEVER include. If the job posting requires \
something the candidate's profile does not support, say so honestly in "summary" \
rather than inventing it.

Company: {company}
Role: {role}
Additional notes from the candidate: {notes}

<job_posting>
{job_posting}
</job_posting>

Respond with ONLY a raw JSON object - no markdown code fences, no prose before or \
after. Use exactly this shape (all values are strings; use "\\n" to separate bullet \
points/lines within a field; leave a field "" if there is truly nothing to put there):

{{"sections":{{"name":"","contact":"","websites":"","availability":"","residency":"",\
"skills":"","summary":"","workHistory":"","education":"","certifications":"",\
"projects":""}},"company":"","role":"","summary":"","transparency":[]}}

The top-level "summary" field (distinct from "sections.summary", which is the CV's \
own profile-statement blurb) is a short, human-readable explanation of what you \
tailored and why, written for the candidate to read - mention any transparency flags \
from rule 2 above and any gaps from rule 3.

Also fill "transparency": a short JSON array of plain strings, one per notable item \
from categories 2 or 3 above, phrased for the candidate to read and double-check \
before they download the file - e.g. "Framed 3 years of freelance data cleanup as \
'data pipeline experience' - a reasonable inference, but be ready to speak to it \
directly in an interview." or "The posting asks for a PMP certification; nothing in \
the profile supports this, so it was left out.". This is the SAME information already \
required in "summary" above, just also broken out as a short list so it can be shown \
to the candidate on its own before they download. If there is nothing notable to \
flag, "transparency" must be an empty array - never invent an entry just to fill it.
"""

COVER_LETTER_PROMPT = """\
You are running Step 3 (cover-letter writing) of the job-application-assistant skill \
in this project, adapted for this backend: you must NEVER write, edit, or create any \
files, and you must NEVER produce LaTeX or any document markup. Instead, respond with \
structured JSON only, which a separate renderer turns into the actual document. This \
is a single, non-interactive run - do not ask clarifying questions.

Read the candidate's profile from \
.claude/skills/job-application-assistant/01-candidate-profile.md (and \
profile/raw-cv.txt as a fallback). Follow the writing-style rules in \
.claude/skills/job-application-assistant/03-writing-style.md (no em-dashes, no \
cliches, forward-looking, every claim backed by a specific example) and the structure \
guidance in .claude/skills/job-application-assistant/06-cover-letter-templates.md \
(salutation rules, ~250-300 word body budget across 3 short paragraphs, one \
paragraph may contain a short bullet list of concrete achievements).

HONESTY IS NON-NEGOTIABLE - never claim an achievement, skill, or experience that is \
not supported by the candidate's profile. If you lean on a plausible-but-not-explicit \
inference from their background to make a point land, flag it in "transparency" below \
rather than stating it as flatly verified fact.

Company: {company}
Role: {role}
Notes from the candidate (may include a "voice reference" - an excerpt from a \
previous cover letter whose STYLE you should match, without copying its content or \
claims): {notes}

<job_posting>
{job_posting}
</job_posting>

Respond with ONLY a raw JSON object - no markdown code fences, no prose before or \
after. Use exactly this shape:

{{"greeting":"Dear ...,","paragraphs":["opening paragraph","body paragraph (may \
include short bullet lines separated by \\n)","closing paragraph"],\
"closing":"Kind regards,","signatureName":"","company":"","role":"",\
"summary":"a short human-readable note on what you emphasized and why",\
"transparency":[]}}

"transparency" is a short JSON array of plain strings, one per notable claim that \
leans on a plausible-but-not-explicit inference rather than something the profile \
states directly - phrased for the candidate to read and double-check before they \
download the file. If there is nothing notable to flag, "transparency" must be an \
empty array - never invent an entry just to fill it.
"""


def _format_note(output_format: str | None) -> str:
    # LaTeX/PDF output is deliberately not implemented in this build (see
    # runs/03-plan.md's explicit decision) - always render .docx, but tell
    # the user honestly rather than silently substituting formats.
    if (output_format or "").lower() == "latex":
        return (
            "\n\n[Note: LaTeX/PDF output isn't implemented in this local backend yet - "
            "a .docx was generated instead.]"
        )
    return ""


def _generate_options(instance_dir: Path, model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(instance_dir),
        model=model,
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Skill"],
        disallowed_tools=["Write", "Edit", "NotebookEdit", "AskUserQuestion", "Bash"],
        max_turns=agent_client.MAX_TURNS_GENERATE,
        system_prompt={"type": "preset", "preset": "claude_code"},
        setting_sources=["project"],
        add_dirs=[str(instances.CLONE_DIR)],
        agents=None,
        skills=None,
        env={},
        betas=[],
        mcp_servers={},
        plugins=[],
    )


@app.post("/v1/tailor")
async def tailor(body: GenerateRequest):
    lock = instances.get_lock(body.instanceId)
    async with lock:
        try:
            instance_dir = instances.instance_path(body.instanceId)
        except instances.InstanceNotFound:
            return JSONResponse(error_body("Unknown instanceId"), status_code=404)

        model = agent_client.resolve_model(body.modelId)
        prompt = TAILOR_PROMPT.format(
            company=body.company or "Unknown",
            role=body.role or "Unknown",
            notes=body.notes or "(none)",
            job_posting=body.jobPosting or "",
        )

        try:
            result = await agent_client.run_agent(prompt, _generate_options(instance_dir, model))
        except Exception as e:
            logger.exception("v1/tailor agent run failed")
            return JSONResponse(error_body(str(e)), status_code=502)

        files: list[str] = []
        summary_text = result.text
        # P1a (Round 7): additive, same pattern as Round 6's "gaps" on
        # /v1/evaluate - the model already classifies content into
        # source-verified / plausibly-transferable / fabricated (see
        # TAILOR_PROMPT's HONESTY rules) and previously only surfaced that
        # informally inside the prose "summary" field. TAILOR_PROMPT now
        # also asks for the same information as a short structured list, so
        # the frontend can render it with the existing (previously unused)
        # .transparency CSS component before the download button. Defaults
        # to [] and degrades gracefully exactly like "summary"/"files" below
        # if extraction or rendering fails - never blocks the existing
        # response shape.
        transparency: list[str] = []

        try:
            data = agent_client.extract_json(result.text)
            sections = {k: (data.get("sections", {}) or {}).get(k, "") for k in docx_render.SECTION_KEYS}
            summary_text = data.get("summary") or "Tailored CV generated."
            # F3 (Round 7 follow-up): guard against a model returning
            # "transparency" as a non-list (e.g. a plain string) - without
            # this, `for t in raw` would iterate individual characters
            # instead of items, producing one bullet per character on the
            # frontend. Same graceful-degradation style as "gaps" (Round 6).
            _raw_transparency = data.get("transparency")
            transparency = [str(t) for t in _raw_transparency if str(t).strip()] if isinstance(_raw_transparency, list) else []
            company = data.get("company") or body.company or ""
            role = data.get("role") or body.role or ""

            filename = f"Resume - {docx_render.safe_filename(company)} - {docx_render.safe_filename(role)}.docx"
            out_path = instances.output_dir(body.instanceId) / filename

            template = docx_render.find_marked_template(instances.templates_dir(body.instanceId))
            if template is not None:
                docx_render.render_templated(template, out_path, sections)
            else:
                docx_render.render_resume_plain(out_path, sections)

            files.append(filename)
            summary_text += _format_note(body.outputFormat)
        except Exception as e:
            logger.warning("v1/tailor: could not parse/render structured output: %s", e)
            summary_text = (
                result.text
                + "\n\n[Note: the backend could not parse a structured document from this "
                "response, so no file was generated. Raw model output shown above.]"
            )

    return {
        "content": [{"type": "text", "text": summary_text}],
        "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
        "files": files,
        "transparency": transparency,
    }


@app.post("/v1/cover-letter")
async def cover_letter(body: GenerateRequest):
    lock = instances.get_lock(body.instanceId)
    async with lock:
        try:
            instance_dir = instances.instance_path(body.instanceId)
        except instances.InstanceNotFound:
            return JSONResponse(error_body("Unknown instanceId"), status_code=404)

        model = agent_client.resolve_model(body.modelId)
        prompt = COVER_LETTER_PROMPT.format(
            company=body.company or "Unknown",
            role=body.role or "Unknown",
            notes=body.notes or "(none)",
            job_posting=body.jobPosting or "",
        )

        try:
            result = await agent_client.run_agent(prompt, _generate_options(instance_dir, model))
        except Exception as e:
            logger.exception("v1/cover-letter agent run failed")
            return JSONResponse(error_body(str(e)), status_code=502)

        files: list[str] = []
        summary_text = result.text
        # P1a (Round 7): same additive "transparency" field as /v1/tailor -
        # see that handler's comment.
        transparency: list[str] = []

        try:
            data = agent_client.extract_json(result.text)
            summary_text = data.get("summary") or "Cover letter generated."
            # F3 (Round 7 follow-up): same non-list guard as /v1/tailor above.
            _raw_transparency = data.get("transparency")
            transparency = [str(t) for t in _raw_transparency if str(t).strip()] if isinstance(_raw_transparency, list) else []
            company = data.get("company") or body.company or ""
            role = data.get("role") or body.role or ""

            filename = f"Cover Letter - {docx_render.safe_filename(company)} - {docx_render.safe_filename(role)}.docx"
            out_path = instances.output_dir(body.instanceId) / filename

            docx_render.render_cover_letter_plain(
                out_path,
                greeting=data.get("greeting") or "",
                paragraphs=data.get("paragraphs") or [],
                closing=data.get("closing") or "",
                signature_name=data.get("signatureName") or "",
            )
            files.append(filename)
            summary_text += _format_note(body.outputFormat)
        except Exception as e:
            logger.warning("v1/cover-letter: could not parse/render structured output: %s", e)
            summary_text = (
                result.text
                + "\n\n[Note: the backend could not parse a structured document from this "
                "response, so no file was generated. Raw model output shown above.]"
            )

    return {
        "content": [{"type": "text", "text": summary_text}],
        "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
        "files": files,
        "transparency": transparency,
    }



# ==========================================================================
# 4. GET /v1/claude-status - genuine Claude Code auth/reachability check
#    (Round 9 - AI-connection-status/gate work). Deliberately separate from
#    "is this Python server up" (the frontend's pre-existing
#    probeBackend()/backendFetch): that only proves this FastAPI process is
#    listening, not that the Claude Agent SDK it calls into can actually
#    reach an authenticated Claude Code session. The `claude` CLI can be
#    logged out, expired, or never set up at all while this server runs
#    fine regardless.
# ==========================================================================
#
# Approach chosen, and why: a real minimal Agent SDK call, not a credential-
# file check. Before deciding, the local `claude` CLI's credential store
# (~/.claude/.credentials.json) was actually inspected: it holds a short-
# lived OAuth accessToken (observed ~1 hour validity from last refresh)
# plus a longer-lived refreshToken, and the CLI/SDK transparently rotates
# the access token using the refresh token as needed. That means the file
# merely existing - or even its recorded expiry being in the future - does
# not reliably prove a call would succeed right now: the interesting
# failure modes (refresh token itself expired/revoked, account logged out,
# CLI never configured, a corrupted store) all require actually exercising
# the refresh/auth path to observe, which is precisely what a real call
# does and a file stat cannot. So this endpoint pays a small, real,
# deliberately minimized cost instead: max_turns=1, no tools at all, the
# shortest reasonable prompt, the fast/cheap default model (not whatever
# the user has picked in the top bar), and a hard timeout so a hung CLI
# can't leave the request hanging forever.
#
# `tools=[]` (not just `allowed_tools=[]`) is what actually disables every
# built-in tool - confirmed by reading claude_agent_sdk's own
# ClaudeAgentOptions docstring and by measurement: leaving `tools` unset
# (its default) cost ~22.9k input tokens per call even with
# allowed_tools=[]/disallowed_tools=[] set (the CLI still loads full tool
# definitions into context, it just doesn't let the model use them);
# adding tools=[] cut that to ~7.4k. Both runs took ~15-17s wall-clock
# regardless - that appears to be fixed claude-CLI-subprocess/round-trip
# latency, not something prompt size controls, hence the generous timeout
# below.
#
# UPDATE (Round 9 follow-up, runs\27-implement-round9-followup.md): the
# Round 9 review measured real successful latency of 18.9-26.9s across 8
# live calls, and the original 35s budget actually misfired during that
# review - a real "Couldn't reach Claude Code" false negative on a fully-
# authenticated, working machine (server log:
# "v1/claude-status: timed out after 35s"), leaving only ~8s of headroom
# above the observed tail. Raised to 60s for comfortable margin; the
# follow-up pass's own fresh live measurements (see the report) confirmed
# no timeout under the new budget.
CLAUDE_STATUS_PROMPT = "Reply with exactly one word: OK"
CLAUDE_STATUS_TIMEOUT_SECONDS = 60


@app.get("/v1/claude-status")
async def claude_status():
    # Not instance-scoped (no instanceId), so no per-instance lock is
    # needed - this never touches an instance workspace or any user data.
    options = ClaudeAgentOptions(
        cwd=str(instances.SERVER_DIR),
        model=agent_client.DEFAULT_MODEL,
        permission_mode="bypassPermissions",
        tools=[],
        allowed_tools=[],
        disallowed_tools=[],
        max_turns=1,
        system_prompt="",
        setting_sources=None,  # deliberate: must not load repo skills for a bare ping
        add_dirs=[],
        agents=None,
        skills=None,
        env={},
        betas=[],
        mcp_servers={},
        plugins=[],
    )

    try:
        await asyncio.wait_for(
            agent_client.run_agent(CLAUDE_STATUS_PROMPT, options),
            timeout=CLAUDE_STATUS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("v1/claude-status: timed out after %ss", CLAUDE_STATUS_TIMEOUT_SECONDS)
        return {
            "connected": False,
            "detail": f"Timed out waiting {CLAUDE_STATUS_TIMEOUT_SECONDS}s for the local Claude "
            "Code CLI to respond.",
        }
    except Exception as e:
        # Broad on purpose: this endpoint's entire job is to turn "was the
        # call able to complete at all" into an honest yes/no for the UI,
        # regardless of which of the SDK's several exception types a given
        # failure (not logged in, CLI missing, process error, ...) raises.
        logger.warning("v1/claude-status: agent call failed: %s", e)
        return {"connected": False, "detail": str(e) or e.__class__.__name__}

    return {
        "connected": True,
        "detail": f"Reached Claude Code via the Agent SDK (model {options.model}).",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
