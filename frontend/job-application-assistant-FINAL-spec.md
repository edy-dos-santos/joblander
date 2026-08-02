# Job Application Assistant — Final Build Spec

Consolidated, decision-locked. Supersedes the architecture blueprint, prompt pack, and UX flow doc — those remain as deeper references (the prompt pack holds the verbatim task schemas). Build from this.

**What it is:** a single-file HTML app, running as a **Claude.ai artifact**, that tailors resumes and cover letters to job postings using the `job-application-tailorer` workflow (embedded as prompts, not invoked as a skill) and the in-artifact Anthropic API.

---

## 1. Locked decisions

| Fork | Resolved |
|---|---|
| Runtime | Claude.ai HTML artifact. No standalone/PWA build. |
| Framework | Vanilla JS, single HTML file, central `AppState` + pub/sub, `render*()` functions. CDN libs: `mammoth`, `PizZip`. |
| Auth | None visible. App manages its own users; Claude hands over no identity (see §9). |
| AI calls | `fetch` → `/v1/messages`, auto-authenticated, no key. |
| Skill | SKILL.md text embedded as `SKILL_SYSTEM_PROMPT`. App reproduces, never invokes. |
| CV → template | **Option 2:** user uploads any CV; a one-time `MAP_CV_TASK` labels its chunks onto the template regions. User does nothing but upload. |
| Master CV stored | **Structured** (per region), not raw — tailoring reuses it without re-parsing. Saves tokens. |
| docx output | PizZip XML surgery: swap `«MARKER»` regions in the user's template. |
| Resume vs letter | Separate call chains, separate list lines, separate token readouts. |
| max_tokens | Assume platform-fixed at 1000 → per-section tailoring loop is **mandatory**. Verify in the phase-0 spike. |
| Persistence | `window.storage` for metadata + small base64; large .docx session-only; **Export/Import JSON** for portability + backup. |
| Cover letter | Inline `COVER_LETTER_TASK` (default). Promote to its own skill later only if letter style needs heavy iteration. |
| Model | Global header selector; default `claude-sonnet-4-6`. |

---

## 2. Tech stack & coding structures

- **State:** one `AppState` object + `subscribe`/`emit` pub/sub; any mutation triggers the relevant `render*()`.
- **Views:** `AppState.view` string drives a screen router; transitions are `setView(...)`. No URLs.
- **Events:** delegated `onClick`/`onChange` on containers, reading `data-*` for the target user/application.
- **File in:** `FileReader.readAsArrayBuffer` → `mammoth` (.docx → text) for the model; raw bytes kept for the template.
- **File out:** `PizZip` to edit the .docx zip; `Blob` + `URL.createObjectURL` for downloads.
- **AI:** `async callClaude({system, messages, tools})` wrapping `fetch`; filter response blocks by `type`; strip ```` ```json ```` fences; try/catch.
- **Concurrency (optional batch):** `Promise.allSettled` + a size-3 semaphore.
- **Persistence:** debounced `saveState()` / `loadState()` over `window.storage`.

---

## 3. Data model (final)

```
AppState = {
  settings: { model: "claude-sonnet-4-6", maxConcurrent: 3 },
  users: [ User ],
  view, wizardStep, activeUserId, activeApplicationId,
}

User = {
  id, name,
  masterCvB64,            // uploaded CV bytes — also the .docx template skeleton
  masterCvText,           // mammoth extract (transient input to MAP_CV_TASK)
  masterSections: {       // STRUCTURED master content, keyed by template region:
    name, contact, websites, availability, residency, skills,
    summary, workHistory, education, certifications, projects   // each = string
  },
  coverLetterTemplateB64, // optional
  library: { resumes: [FileRef], coverLetters: [FileRef] },
  createdAt,
}

Application = {
  id, userId,
  jdUrl, pastedJD, jdText, positionName, company,
  baseCv: "master" | <override B64>,
  notes, mode: "questions" | "straight",
  conversation: [ {role, content} ],   // ISOLATED — only this app's history is ever sent
  resume:      { status, progress, tokensUsed, sections, transparencyNote, blobUrl },
  coverLetter: { status, progress, tokensUsed, greeting, body, closing, blobUrl },
}
```

The eleven region keys are shared across `masterSections`, `MAP_CV_TASK`, and `TAILOR_TASK` — one vocabulary end to end.

---

## 4. Screens

```
HOME  [Choose your user] [New user]
  ├─ CHOOSE USER → list → select → USER HOME
  └─ NEW USER → name → upload CV → [Upload cover-letter tmpl][Not now]
                                   → (runs MAP_CV_TASK silently) → USER HOME

USER HOME (active user)  [Check applications] [New application] [Library]
  ├─ CHECK APPLICATIONS → list; each app = two lines (resume + cover letter),
  │                       each with status, progress bar, token readout
  ├─ NEW APPLICATION → wizard (§5)
  └─ LIBRARY → Resume box / Cover-letter box: drag-drop add,
              tickbox delete, double-click download
```

---

## 5. New-application wizard

| Step | Screen | Fires |
|---|---|---|
| A | JD source: `[Link]` (one-line) / `[Paste JD]` (textarea) | — |
| B | Which resume: `[Current one]` (master) / `[New one]` (upload override) | — |
| C | Notes textarea + `[Run]` | starts pipeline |
| D | Run: resolve JD, then analyse | `JD_EXTRACT_TASK` → `GAP_ANALYSIS_TASK` |
| D′ | Questions (only if `clarifyingQuestions` non-empty + Questions mode): chat → `[Continue]` | answers folded into gap analysis |
| E | Resume preview (styled HTML mimicking the .docx); `[Download]` `[Re-tailor]` | `TAILOR_TASK` (per-section loop) |
| E′ | Re-tailor: chat for concerns → regenerate | `TAILOR_TASK` + concerns |
| F | Download builds .docx; then cover letter: `[Create new]` `[Tailor current]` `[Not now]` | `COVER_LETTER_TASK` |

- **Step B** "current one" = master CV (content source *and* template). "New one" overrides content for this app, keeps the template styling.
- **Step C** notes append verbatim to `TAILOR_TASK` as extra instructions — steer tone, never the honesty contract.
- **Step E** preview is an *approximation*; the downloaded .docx is the source of truth.

---

## 6. The skill port — tasks

Full verbatim system prompt + schemas live in the prompt-pack doc. The chain:

1. **`MAP_CV_TASK`** *(new — created by the option-2 decision)* — run once at user creation. Input: `masterCvText`. Output: the eleven region keys, each filled with that user's content, verbatim. Stored as `masterSections`.
   ```
   { "name": "...", "contact": "...", "skills": "...", "summary": "...",
     "workHistory": "...", ... }   // all eleven keys, content lifted as-is
   ```
2. **`JD_EXTRACT_TASK`** — normalise link/paste → `positionName`, `company`, `jdText`, `thinJd`.
3. **`GAP_ANALYSIS_TASK`** — three-column analysis + `clarifyingQuestions`. The Questions-mode gate.
4. **`TAILOR_TASK`** — per section: full text, changed only where the approved gap analysis warrants, + `changes[]` audit trail → transparency note. **Loop the eleven keys, one call each** (max_tokens).
5. **`COVER_LETTER_TASK`** — under the same honesty contract; "tailor current" uses the user's letter template as base, "create new" from scratch.

All calls send `system = SKILL_SYSTEM_PROMPT`; the dialog window appends turns to the application's own `conversation[]`.

---

## 7. docx build (PizZip)

1. `new PizZip(templateBytes)` — the user's master CV bytes.
2. Read `word/document.xml`.
3. Swap each `«MARKER»` region for the tailored `sections[key].text`, converting line breaks into the template's existing paragraph/bullet style.
4. `zip.generate({type:"blob"})` → download link.

**Prerequisite:** a marked copy of the double-column template with the eleven `«MARKER»` tags placed in the right table cells. Nothing in §6–7 runs without it — build it first.

---

## 8. Persistence & portability

- `saveState()` (debounced) → `window.storage`: `settings`, users *metadata* + `masterSections` (small, structured), applications *minus binaries*.
- `window.storage` is ~5 MB/key, text/JSON. Base64 small .docx; keep large templates/library files **session-only** with re-upload.
- **Export/Import:** "Back up" bundles all users + applications + .docx bytes (base64) into one JSON download; "Import" restores it. This is the real portability + backup mechanism — covers the session-only gap and moves everything to a new device in one file.

---

## 9. Auth reality (build implication)

The app never sees who you are. No login, no handshake — opening it lands on HOME. The Claude connection is invisible: it exists only when an API call fires, and the platform silently authenticates it against your session and quota. So **the app must own its user list** — "which user is this?" is a question the app asks *you* (the front door), never one Claude answers. Storage is account-scoped, so users/data follow you across devices when logged into Claude (large session-only files excepted — that's what Export/Import is for).

---

## 10. Build order

0. **Spike:** confirm `max_tokens` is fixed and which model strings the in-artifact API honours. Decides §6 loop + §1 selector.
1. **Marked template** — prepare the `«MARKER»` .docx (the one prerequisite).
2. Scaffold: HTML, view router, `AppState`, pub/sub, empty renders.
3. New-user flow: upload → mammoth → `MAP_CV_TASK` → store `masterSections`.
4. `callClaude` wrapper; get a clean round-trip.
5. Wizard A–C (inputs) + the application list with two lines per app.
6. Pipeline: `JD_EXTRACT` → `GAP_ANALYSIS` → Questions branch.
7. `TAILOR_TASK` per-section loop → HTML preview.
8. docx build (PizZip) + download.
9. Cover-letter branch (`COVER_LETTER_TASK`).
10. Re-tailor chat + dialog component.
11. Library view (drag-drop, delete, double-click download).
12. Persistence + Export/Import.
13. Model selector, polish, mobile layout, error/empty states.

---

## 11. Token economy (since it's the point)

Where this design keeps Pro-quota use sane: the **structured master CV** means tailoring never re-parses raw resume text; **per-application isolation** keeps every call's context small (one app's history, never the pile); **per-section calls** are individually tiny; the **default is Sonnet 4.6**, not Opus. Build it on whatever model you like — run it on Sonnet.

---

## 12. To verify in-build

- `max_tokens` ceiling (phase 0) — mandatory before §6.
- Which model strings the selector can actually pass.
- JD-from-URL reliability via `web_search` — keep paste-JD as the always-available fallback.
- 5 MB storage behaviour with real .docx sizes — tunes the session-only cutoff.
