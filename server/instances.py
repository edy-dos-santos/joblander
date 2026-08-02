"""Instance-workspace management for the AI Job Assistant local backend.

An "instance" is a per-user working directory under `instances/<id>/`,
seeded by copying the pristine `backend/` clone's `.claude/` folder so the
job-application-assistant skill (and its sibling skills) load unmodified.
The user's own profile is written into that copy's
`01-candidate-profile.md` - the file the skill actually reads for
candidate data (CLAUDE.md itself is stale placeholders in the clone).

No model calls happen anywhere in this module - just filesystem setup,
profile-markdown rendering, and the security-critical path resolution
used by GET /v1/files.

    instances/<id>/
    |- .claude/                                    <- copied from the clone
    |  \\- skills/job-application-assistant/01-candidate-profile.md  <- overwritten per user
    |- profile/raw-cv.txt
    |- templates/         <- .docx templates (no upload endpoint exists yet - see 04-implement-server.md)
    |- output/             <- generated files; the only thing GET /v1/files may serve
    \\- instance.json       <- {id, name, outputFormat}
"""
from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent
APP_FILES_DIR = SERVER_DIR.parent
CLONE_DIR = APP_FILES_DIR / "backend"
INSTANCES_DIR = APP_FILES_DIR / "instances"
FRONTEND_HTML = APP_FILES_DIR / "frontend" / "job-application-assistant.html"

INSTANCES_DIR.mkdir(parents=True, exist_ok=True)

SECTION_KEYS = [
    "name", "contact", "websites", "availability", "residency",
    "skills", "summary", "workHistory", "education", "certifications",
    "projects",
]

SECTION_LABELS = {
    "name": "Name",
    "contact": "Contact",
    "websites": "Websites / Portfolios / Profiles",
    "availability": "Availability",
    "residency": "Residency",
    "skills": "Skills",
    "summary": "Summary",
    "workHistory": "Work History",
    "education": "Education",
    "certifications": "Certifications",
    "projects": "Projects",
}


class InstanceNotFound(Exception):
    """Raised when an instanceId doesn't correspond to a real workspace."""


class PathEscapeError(Exception):
    """Raised when a requested file path would resolve outside the
    instance's output/ directory."""


def _instance_dir(instance_id: str) -> Path:
    # instanceId is server-generated (uuid4 hex) but arrives on every
    # request as a client-supplied string - validate defensively before
    # ever joining it onto a filesystem path.
    if not instance_id or not all(c.isalnum() for c in instance_id):
        raise InstanceNotFound(instance_id)
    d = INSTANCES_DIR / instance_id
    if not d.is_dir():
        raise InstanceNotFound(instance_id)
    return d


def _render_profile_markdown(
    name: str | None,
    sections: dict[str, Any] | None,
    rawText: str | None,
) -> str:
    lines = [
        "# Candidate Profile",
        "",
        "<!-- Written by the local backend from the UI's profile step (POST /v1/profile). -->",
        "",
    ]
    if sections:
        for key in SECTION_KEYS:
            value = (sections.get(key) or "").strip() if isinstance(sections, dict) else ""
            lines.append(f"## {SECTION_LABELS[key]}")
            lines.append(value if value else "_(not provided)_")
            lines.append("")
    elif name:
        lines.append("## Name")
        lines.append(name)
        lines.append("")

    if rawText and rawText.strip():
        lines.append("## Raw CV Text (fallback - use this if the structured sections above look thin or placeholder-only)")
        lines.append("")
        lines.append(rawText.strip())
        lines.append("")

    if not sections and not (rawText and rawText.strip()):
        lines.append("_No CV content has been provided yet for this profile. Ask the user to upload or paste their CV before evaluating or tailoring against it._")
        lines.append("")

    return "\n".join(lines)


def _write_profile_file(
    d: Path,
    *,
    name: str | None,
    sections: dict[str, Any] | None,
    rawText: str | None,
) -> None:
    profile_md = _render_profile_markdown(name, sections, rawText)
    skill_dir = d / ".claude" / "skills" / "job-application-assistant"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "01-candidate-profile.md").write_text(profile_md, encoding="utf-8")


def create_instance(name: str) -> str:
    """Provision a fresh instance workspace and return its id. No model
    call - plain filesystem setup only."""
    instance_id = uuid.uuid4().hex
    d = INSTANCES_DIR / instance_id
    d.mkdir(parents=True, exist_ok=False)

    claude_src = CLONE_DIR / ".claude"
    if claude_src.is_dir():
        shutil.copytree(claude_src, d / ".claude")
    else:
        (d / ".claude").mkdir(parents=True, exist_ok=True)

    (d / "profile").mkdir(exist_ok=True)
    (d / "templates").mkdir(exist_ok=True)
    (d / "output").mkdir(exist_ok=True)

    meta = {"id": instance_id, "name": name, "outputFormat": "docx"}
    (d / "instance.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Seed a minimal profile immediately - the UI's ensureInstance() posts
    # /v1/profile right after /v1/users, but that second call can fail
    # independently (see the frontend's own comments on this), so no
    # downstream endpoint should ever find a missing profile file.
    _write_profile_file(d, name=name, sections=None, rawText=None)
    (d / "profile" / "raw-cv.txt").write_text("", encoding="utf-8")

    return instance_id


def write_profile(
    instance_id: str,
    *,
    name: str | None,
    outputFormat: str | None,
    sections: dict[str, Any] | None,
    rawText: str | None,
) -> None:
    d = _instance_dir(instance_id)
    _write_profile_file(d, name=name, sections=sections, rawText=rawText)
    if rawText is not None:
        (d / "profile" / "raw-cv.txt").write_text(rawText or "", encoding="utf-8")

    meta_path = d / "instance.json"
    meta: dict[str, Any] = {"id": instance_id}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if name:
        meta["name"] = name
    if outputFormat:
        meta["outputFormat"] = outputFormat
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def instance_path(instance_id: str) -> Path:
    """Public accessor for the instance's root dir (used by the agent
    endpoints to set cwd). Raises InstanceNotFound if it doesn't exist."""
    return _instance_dir(instance_id)


def output_dir(instance_id: str) -> Path:
    d = _instance_dir(instance_id)
    out = d / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def templates_dir(instance_id: str) -> Path:
    d = _instance_dir(instance_id)
    t = d / "templates"
    t.mkdir(parents=True, exist_ok=True)
    return t


def resolve_output_path(instance_id: str, rel_path: str) -> Path:
    """Resolve `rel_path` against THIS instance's output/ dir ONLY.

    Raises InstanceNotFound if the instance doesn't exist, PathEscapeError
    if the resolved path would land outside output/ (covers `../`
    traversal, absolute-path overrides, and symlink shenanigans), and
    FileNotFoundError if the (safely-resolved) path isn't a real file.
    """
    d = _instance_dir(instance_id)
    out_dir = (d / "output").resolve()
    if not rel_path:
        raise PathEscapeError(rel_path)

    candidate = (out_dir / rel_path).resolve()
    try:
        candidate.relative_to(out_dir)
    except ValueError:
        raise PathEscapeError(rel_path)

    if not candidate.is_file():
        raise FileNotFoundError(rel_path)
    return candidate


def delete_instance(instance_id: str) -> None:
    """Permanently delete an instance's entire workspace directory.

    Used by DELETE /v1/users/{instanceId} (Round 8 Pass 2 - standalone
    profile delete, and the source side of a profile merge). Reuses
    _instance_dir's existing validation (instance_id must be alnum-only
    and must already exist on disk - raises InstanceNotFound otherwise,
    same as every other instance-scoped function in this module) and then,
    exactly like resolve_output_path's discipline for GET /v1/files above,
    never trusts that validation alone: the resolved path is independently
    re-confirmed to be a direct child of INSTANCES_DIR before shutil.rmtree
    ever runs. Raises PathEscapeError (not InstanceNotFound) if that second
    check somehow fails - it should be unreachable given _instance_dir's
    alnum guard, but a destructive whole-directory delete gets the same
    belt-and-suspenders treatment as the read-only file-serving path.
    """
    d = _instance_dir(instance_id)
    instances_root = INSTANCES_DIR.resolve()
    resolved = d.resolve()
    if resolved == instances_root or resolved.parent != instances_root:
        raise PathEscapeError(instance_id)
    shutil.rmtree(resolved)
    _locks.pop(instance_id, None)


# --------------------------------------------------------------------------
# Per-instance async locks - serializes concurrent requests against the
# same instance (e.g. a profile sync landing mid-evaluate, or a user
# double-clicking "tailor").
# --------------------------------------------------------------------------
_locks: dict[str, asyncio.Lock] = {}


def get_lock(instance_id: str) -> asyncio.Lock:
    lock = _locks.get(instance_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[instance_id] = lock
    return lock
