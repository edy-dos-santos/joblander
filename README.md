# JobLander — AI Job Hunter

A local, single-user tool that tailors a resume and cover letter to a specific job posting.
You give it your CV and a job description; it evaluates how well you actually fit the role,
discusses how to close the gaps it finds, and drafts a tailored resume and cover letter you
download as a real `.docx` file — no copy-pasting model output, no manual formatting.

Everything runs on your own machine. Nothing is uploaded anywhere except the AI calls
themselves, which go through your existing Claude Code login.

---

## Get started (Windows)

**The easiest way to install JobLander: download one file and run it. No git, no cloning,
nothing else to download first.**

1. Download **[`Get-JobLander.bat`](https://raw.githubusercontent.com/edy-dos-santos/joblander/main/Get-JobLander.bat)**
   (right-click the link and choose "Save link as…", or just click it and let your browser save
   the file — don't open it *in* the browser).
2. Double-click the file you just downloaded.

That's the whole first step. It explains on screen exactly what it's about to do, downloads
JobLander from this repository onto your computer (your Desktop by default — it'll ask first
if a JobLander folder is already there, and it never overwrites saved profiles without asking),
and then automatically runs the same installer described under "Easy install (Windows)" below to
get Claude Code, Python, and everything else set up. Nothing to install first, no terminal
required.

### Other ways to get it

If you already use git, or you'd rather have the full repository on disk for some other reason:

- **Clone it**: `git clone https://github.com/edy-dos-santos/joblander.git`, then double-click
  `Install-JobLander.bat` inside the cloned folder (same installer either way — see "Easy install
  (Windows)" below).
- **Download the ZIP by hand**: use GitHub's own green "Code → Download ZIP" button on the
  [repo page](https://github.com/edy-dos-santos/joblander), extract it, then double-click
  `Install-JobLander.bat` inside the extracted folder.

---

## Get started (macOS / Linux)

**The easiest way to install JobLander: run one command in a terminal. No git, no cloning,
nothing else to download first.**

```
curl -fsSL https://raw.githubusercontent.com/edy-dos-santos/joblander/main/scripts/get-joblander.sh | bash
```

That's the whole first step. It explains on screen exactly what it's about to do, downloads
JobLander from this repository onto your computer (your Desktop by default on macOS, or
`~/JobLander` on Linux if no Desktop folder exists — it'll ask first if a JobLander folder is
already there, and it never overwrites saved profiles without asking), and then automatically
runs the same installer described under "Easy install (macOS / Linux)" below to get Python and
everything else set up. Nothing to install first — just a terminal, which every Mac and Linux
machine already has.

### Other ways to get it

If you already use git, or you'd rather have the full repository on disk for some other reason:

- **Clone it**: `git clone https://github.com/edy-dos-santos/joblander.git`, then run
  `./scripts/install.sh` (or `bash scripts/install.sh`) inside the cloned folder (same installer
  either way — see "Easy install (macOS / Linux)" below).
- **Download the archive by hand**: use GitHub's own green "Code → Download ZIP" button on the
  [repo page](https://github.com/edy-dos-santos/joblander), extract it, then run
  `./scripts/install.sh` inside the extracted folder.

---

## Where the AI logic comes from

The actual job-fit scoring, gap analysis, resume tailoring, and cover-letter writing are not
built from scratch here. They're powered by the **`job-application-assistant` skill**, which
originates from **[ai-job-search](https://github.com/MadsLorentzen/ai-job-search)**, a project
by **Mads Lorentzen** — all credit for the underlying scoring framework, candidate-profile
format, and writing-style rules belongs there.

**This is already set up for you — there's nothing to install or clone separately.** This repo
ships the specific skill files JobLander's server actually reads, directly under
[`backend/.claude/skills/job-application-assistant/`](backend/.claude/skills/job-application-assistant/):
the candidate-profile and behavioral-profile format, the job-fit scoring framework, the
CV-tailoring and cover-letter-writing guidance, and the skill's own definition file. See that
folder's `NOTICE.md` for the exact attribution. Everything else from Mads Lorentzen's project —
his job-search/scraping CLIs, LaTeX/PDF document generation, and interview-prep feature — is
**not** included, because JobLander doesn't use any of it: JobLander runs its own evaluate/
tailor/cover-letter prompts against just those files and renders `.docx` output with its own
pipeline (see below), never his LaTeX toolchain.

If `backend/.claude/skills/job-application-assistant/` is ever missing or incomplete (an
incomplete download, or files deleted by hand), profile creation will fail with a clear error
telling you so — the fix is just to re-clone or re-download the repo; see
[Troubleshooting](#troubleshooting) below.

What's original to *this* app on top of all that: the entire browser UI, the FastAPI bridge
server that drives the skill through the Claude Agent SDK on a per-profile basis, and the
deterministic `.docx` rendering pipeline (`python-docx`) that turns the model's structured
output into an actual downloadable Word document — none of that existed in any form before this.

---

## Before you start

**The easiest way to get set up is the one-command/one-file install in "Get started (Windows)"
or "Get started (macOS / Linux)" above** — it (and the installer described below, which it runs
automatically) handles everything in this list for you, with nothing to install by hand.

If you'd rather do it yourself (any OS, or you're troubleshooting), you need:

- **Claude Code must already be installed and logged in** on this machine (`claude` CLI). This
  app doesn't have its own sign-in screen — it uses whatever Claude Code session is already
  authenticated. If you've never run `claude` before, set that up first.
- **Python 3.11+** with `fastapi`, `uvicorn`, `python-docx`, `jinja2`, `httpx`, `pydantic`,
  `claude-agent-sdk`, and `playwright` installed (plus its Chromium browser — `playwright install
  chromium`), for the browser-automation research features.
- A modern browser (Chrome, Edge, Firefox).

## Easy install (Windows)

*(If you used `Get-JobLander.bat` above, this already ran for you automatically — this section
is here for reference, or for anyone who cloned/downloaded the repo directly instead.)*

Two double-click scripts live at the root of this app folder — no terminal, no manual `pip
install`:

- **`Install-JobLander.bat`** — run this once. It checks that Claude Code is installed and logged
  in (and walks you through signing in if not), finds a working Python 3.11+ on your machine or
  offers to install one via Windows' built-in `winget` (asking first, and only after explaining
  what it's about to do), creates a private `.venv` folder just for JobLander so nothing is
  installed into your system-wide Python, and installs the app's own dependencies into it —
  automatically working around a known Avast/pip certificate conflict if Avast is present on your
  machine. Every step prints what it's doing and why *before* it does anything outside this app's
  own folder (like installing Python or signing in to Claude Code), and it never changes anything
  system-wide without asking first.
- **`Start-JobLander.bat`** — created automatically by the installer once setup finishes. Double-
  click it any time after that to start the app and open your browser automatically.

Both are plain `.bat` files: double-click them from File Explorer like any other program. Each
opens a console window that narrates what it's doing and pauses at the end so you can read the
result before the window closes. (Each `.bat` is a thin wrapper around a same-named PowerShell
script under `scripts\` — Windows won't run `.ps1` files by double-click, so the `.bat` files are
what you're meant to click; you shouldn't need to open `scripts\` yourself.)

## Easy install (macOS / Linux)

*(If you used the one-line `curl` command above, this already ran for you automatically — this
section is here for reference, or for anyone who cloned/downloaded the repo directly instead.)*

Two scripts live under `scripts/` in this app folder — no manual `pip install`:

- **`scripts/install.sh`** — run this once. It checks that Claude Code is installed and logged in
  (and walks you through signing in if not), finds a working `python3` 3.11+ on your machine
  (printing the right `brew`/`apt`/`dnf`/`pacman` command to run yourself if none is found — this
  script doesn't install Python for you), creates a private `.venv` folder just for JobLander so
  nothing is installed into your system-wide Python, and installs the app's own dependencies into
  it (including Playwright's Chromium browser, for the research features). Every step prints what
  it's doing and why *before* it does anything outside this app's own folder (like signing in to
  Claude Code), and it never changes anything system-wide without asking first.
- **`scripts/start-joblander.sh`** — run this any time after setup finishes to start the app and
  open your browser automatically.

Run them from a terminal, from this app's root folder:

```
chmod +x scripts/install.sh scripts/start-joblander.sh   # first time only
./scripts/install.sh
./scripts/start-joblander.sh
```

Each prints what it's doing as it goes, the same way the Windows `.bat` console windows do.
There's no macOS/Linux equivalent of the root-level `.bat` wrappers — unlike a `.ps1` file, a
`.sh` file with its executable bit set runs directly from a terminal, so there's no
double-click-association problem to work around, and adding a redundant top-level wrapper file
wouldn't do anything a normal `scripts/install.sh` invocation doesn't already do.

## Starting the app (manual)

If you'd rather run things by hand instead of using the installer/launcher scripts above (any
OS):

```
cd server
python main.py
```

(On macOS/Linux, if you installed dependencies into `.venv` yourself, use
`../.venv/bin/python main.py`, or activate the environment first with `source
../.venv/bin/activate`.)

Then open **http://127.0.0.1:8787/** in your browser. Leave the terminal window (or, if you used
`Start-JobLander.bat` / `scripts/start-joblander.sh`, that console window) open — closing it stops
the server, and the app won't work without it. You'll know it's not running if you see a banner
across the top of the page telling you the local backend isn't reachable.

If you already have the app open in a browser tab from a previous session, **do a hard refresh**
(Ctrl+Shift+R / Ctrl+F5) before using it, especially after an update — browsers can hang on to an
old copy of the page otherwise.

---

## The landing screen

The first thing you see is the JobLander title screen. Click **Start Here** and the app runs a
real check that it can actually reach Claude Code before letting you in:

- **Connected** — a brief green confirmation, then you're through to your list of profiles
  (automatically, or click Continue).
- **Not connected** — a clear message telling you Claude Code couldn't be reached, with the
  actual fix (open a terminal, run `claude login`, then click Retry). This isn't a login screen
  for *this app* — there isn't one — it's just an honest check of your existing Claude Code
  session, since nothing else here will work without it.

## The sidebar

Click the icon rail on the left edge to expand it. It has five destinations:

- **Home** — brings you back to the JobLander title screen (and the connection check above).
- **Profiles** — your list of candidate profiles (see below).
- **AI provider connections** — a real green/red status light for whether Claude Code is
  currently reachable, with a **Recheck** button to test it again on demand. There's no
  provider-switching here yet — today it's Claude only. Checking status makes a small real call
  to Claude Code, even if you've paused AI calls below.
  - **Disconnect** pauses AI calls *within this app only* — it does not sign you out of Claude
    Code itself, so nothing else on your machine is affected. While paused, every AI-backed
    action (evaluate, tailor, cover letter, etc.) shows a clear "paused" message instead of
    running. Click **Reconnect** to resume — it re-checks the real connection first.
- **About** — a short description of what the app does.
- **GitHub repo** — not active. This project isn't published anywhere; the link is a
  placeholder for later.

## Profiles: who you're applying as

A **profile** is one candidate identity — your name, your CV, and the applications you run
under it. You might want more than one if you're applying under different personas (e.g. a
technical track vs. a general-management track) or helping someone else use the tool.

### Creating a profile

From the Profiles list, start a new profile and give it a name. Then add your CV info, in
whichever of these three ways suits you:

1. **Paste it** — paste your CV text straight into a box.
2. **Upload a file** — hand it a `.docx`/`.pdf`/text file.
3. **Guided Q&A** — answer a short series of questions (name, title, a summary of yourself,
   skills, work history, education, and so on) if you'd rather not paste a whole document.
   Every question is skippable, and you can finish early with whatever you've answered so far.

You can also optionally add a **CV template** — a `.docx` you want your tailored resume's
layout to follow. This is optional; if you skip it, the app builds a clean resume from scratch
instead of following a template's layout.

Once your CV Info is set, later applications default to reusing it — the CV-selection screen
just shows a one-line summary ("Using *[your CV]*" with a **Change** link) instead of asking
you to re-pick it every time.

### Managing existing profiles

Each profile card in the Profiles list has a 3-dot menu:

- **Edit** — takes you to that profile's CV Info tab to update it.
- **Copy** — makes a genuinely independent duplicate: its own separate profile with the same CV
  Info and library, that you can then edit freely without touching the original.
- **Merge with…** — combines the current profile and another one you pick into a **brand-new
  third profile**. This is non-destructive: it does not delete, edit, or move anything out of
  either original — both stay exactly as they were, with their own history untouched. You'll see
  a preview of exactly what the combined profile will contain (CV Info from both, labeled by
  source) before anything is created, and you can rename it before confirming.
- **Delete** — permanently removes a profile and everything under it (CV Info, library,
  application history). You have to type the profile's exact name to confirm — there's no undo,
  so double-check before typing.

---

## Running a job application

From inside a profile, start a new application. The steps:

### 1. Job posting
Paste the job posting text, or give it a URL to fetch it from. If the URL points at a site that
blocks plain automated fetches (LinkedIn, Seek), the backend falls back to rendering the page in
a real (headless) Chromium browser before reading its text — this still won't get past a site's
own login wall or bot-challenge on its own. For LinkedIn/Seek specifically, you can optionally set
up a saved login session once via `scripts/save-login-session.py` (you log in yourself, by hand,
in a visible browser window it opens — it never touches your password) so future fetches from
those sites use it. This is a personal-use convenience, not a bypass: both sites' Terms of Service
generally prohibit automated scraping even by the account owner, and this app treats that as an
accepted risk the same way it already piggybacks on your own Claude Code login instead of a paid
API key.

### 2. CV info / template
Confirm (or change) which CV Info and template this specific application should use.

### 3. Notes
Anything you want the AI to keep in mind while tailoring — a skill to emphasize, a tone to
match, background it should know about. Optional.

### 4. Fit evaluation
The app scores how well your profile actually matches the posting — strengths, real gaps, an
overall verdict — and shows you the full write-up before you commit to anything further. This
takes anywhere from 30 seconds to a couple of minutes; you'll see a running timer and a
changing status line while it works, and a **Cancel** button if you want to back out.

### 5. Closing the gaps (only if real gaps were found)
If the evaluation found genuine gaps between your profile and the role, you'll go through them
one at a time: each gap comes with a few concrete ways you could address it (pick one, or write
your own), plus the option to skip a gap or skip this whole step entirely. Whatever you choose
here feeds directly into how the resume gets tailored.

### 6. Tailoring
The AI writes your tailored resume. Same wait-with-cancel pattern as evaluation. When it's done,
you'll see:
- A summary of what changed and why.
- A **transparency note** — an honest list of what in the resume is directly from your CV versus
  what the AI reasonably inferred. Read this before you send anything to an employer.
- A **Download** button for the actual `.docx` file.

You can also **re-tailor with feedback** from this screen if the first draft isn't right — your
notes box here shows exactly what's already been sent to the model, so you're never guessing
what it already knows.

### 7. Cover letter
Same pattern again: optional extra notes, an AI-written draft, and a download link for the
`.docx`.

---

## Downloading files

Every generated document downloads straight to your browser's normal Downloads folder, same as
any other file download — there's nothing special to configure.

## Tips

- The AI calls (evaluation, tailoring, cover letter) are the slow part of every application —
  each one is a real model call, not instant. Cancel is always available if you don't want to
  wait.
- Nothing you type is lost if you cancel or go back — your notes, gap decisions, and CV info
  stay attached to the profile/application.
- If a download doesn't look right, check that you did a hard refresh after the last time this
  app was updated (see "Starting the app" above).

## Troubleshooting

| Problem | What to check |
|---|---|
| `Get-JobLander.bat` / the `curl \| bash` command says it couldn't download the setup script | Check your internet connection, then run it again. On a work/school network, a firewall may be blocking `github.com`/`raw.githubusercontent.com` — try the "Other ways to get it" options in "Get started (Windows)" / "Get started (macOS / Linux)" instead. |
| "Local backend not reachable" banner | Is `python main.py` (or the `Start-JobLander.bat` / `scripts/start-joblander.sh` window) still running? Restart it if not. |
| `Install-JobLander.bat` / `scripts/install.sh` fails partway through | Read the message it printed — it explains what went wrong and what to do next. It's always safe to just run it again. |
| `scripts/install.sh` can't find Python 3.11+ | Install it yourself (macOS: `brew install python3`; Linux: your distro's package manager, e.g. `sudo apt install python3 python3-venv python3-pip` on Debian/Ubuntu), then run the installer again. |
| `pip` fails to build `lxml` on Linux | Usually only happens if pip falls back to building from source instead of using a prebuilt wheel. Try `sudo apt install libxml2-dev libxslt-dev python3-dev` (Debian/Ubuntu) or your distro's equivalent, then re-run the installer. |
| Red "Couldn't reach Claude Code" on the connection check | Open a terminal and run `claude login`, then click Retry. This means the *server* is fine but your Claude Code session isn't — different from the banner above. |
| AI actions show a "paused" message | You (or someone) clicked Disconnect on the AI provider connections screen. Click Reconnect there to resume. |
| Downloads land with a strange name or won't open | Hard-refresh the page (Ctrl+Shift+R) — you may be running an old cached copy of the app. |
| An AI step fails immediately | Confirm you're logged into Claude Code (`claude` CLI) on this machine. |
| Creating a profile fails with a message about AI skill files being missing/incomplete | Your checkout of `backend/.claude/skills/job-application-assistant/` (see "Where the AI logic comes from" above) is incomplete or was deleted. Re-clone or re-download the repo — nothing else to configure. |
| Nothing happens when you click something | Check the browser console for errors, then try a fresh tab. |
| Job posting URL fetch fails, or comes back empty/garbled (LinkedIn/Seek especially) | Paste the job description text directly instead — the easiest fix. Otherwise, set up a saved login session with `scripts/save-login-session.py` (see "1. Job posting" above), or confirm Chromium installed correctly during setup (`.venv\Scripts\python.exe -m playwright install chromium`). Some pages will still refuse automated access outright (a CAPTCHA/bot-challenge) — this app doesn't try to defeat those. |
