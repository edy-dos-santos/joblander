#!/usr/bin/env bash
#
# JobLander installer (macOS / Linux).
#
# POSIX port of scripts/install.ps1 (the Windows installer) - same order of
# operations and the same underlying intent, adapted to bash/pip/venv
# idioms instead of PowerShell ones. Read install.ps1's own header comment
# for the full "why" behind each step; this file follows the same
# four-step shape:
#
#   1. Claude Code   - confirm the `claude` CLI is installed, then (once
#                       Python/venv is ready, since the real check needs a
#                       working claude-agent-sdk import) verify it's
#                       actually logged in using the same minimal Claude
#                       Agent SDK call server/main.py's own
#                       GET /v1/claude-status endpoint uses. If not logged
#                       in, run the sign-in flow for the user and re-check.
#   2. Python 3.11+  - find a working `python3` on PATH; if none, print
#                       clear install guidance. Unlike install.ps1, this
#                       script does NOT try to auto-install Python itself
#                       (install.ps1 offers to run winget) - there's no
#                       single cross-distro equivalent of winget to shell
#                       out to, and silently invoking `brew`/`apt`/`dnf`/
#                       `pacman` on someone's machine without them typing
#                       the command themselves is a bigger deal on a
#                       Mac/Linux dev machine than on a fresh Windows
#                       install. Printing the right one-liner and letting
#                       the user run it themselves is the safer default.
#   3. Dependencies  - pip-install this app's required packages into a
#                       dedicated .venv, with the same retry-on-transient-
#                       error spirit as install.ps1's
#                       Install-PipPackagesWithRetry (the Avast-specific
#                       certificate workaround is intentionally NOT ported
#                       - see the NOTE below), then
#                       `playwright install chromium` for the
#                       browser-automation research feature.
#   4. Finish        - make sure the scripts/*.sh files are executable and
#                       tell the user how to launch the app.
#
# Run this directly: bash scripts/install.sh
# (or: chmod +x scripts/install.sh && ./scripts/install.sh)
# Safe to re-run any time - every step is idempotent.
#
# NOTE on the Avast cert workaround: install.ps1 builds a combined
# certificate bundle (the public CAs plus Avast's own intercepting root
# certificate, if present) because Avast's Web/Mail Shield HTTPS
# interception is a Windows-only antivirus behavior with no macOS/Linux
# equivalent - there is nothing to work around here, so that logic is
# intentionally not ported. If pip ever reports a certificate-verify
# failure on this platform, it points at something else (a corporate
# proxy/VPN, other local security software doing its own interception, or
# a stale CA bundle) - the retry/troubleshooting guidance below still
# applies to that.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# This file lives in scripts/ - ROOT_DIR is the app's actual root folder
# (server/, .venv/, scripts/start-joblander.sh all live there, one level up).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQUIRED_PACKAGES=(fastapi uvicorn python-docx jinja2 httpx pydantic claude-agent-sdk playwright)
APP_URL="http://127.0.0.1:8787/"

# ---------------------------------------------------------------------------
# Small console-output helpers (mirrors install.ps1's Write-Banner/Step/
# Info/Ok/Warn/Err). Colors are skipped automatically when stdout isn't a
# terminal or NO_COLOR is set, so redirected/logged output stays readable.
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_CYAN=$'\033[36m'; C_WHITE=$'\033[37m'; C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_RESET=$'\033[0m'
else
    C_CYAN=""; C_WHITE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_RESET=""
fi

banner() {
    local text="$1"
    local width=$(( ${#text} + 4 ))
    [ "$width" -lt 40 ] && width=40
    local line
    line="$(printf '%*s' "$width" '' | tr ' ' '=')"
    echo ""
    echo "${C_CYAN}${line}${C_RESET}"
    echo "${C_WHITE} ${text}${C_RESET}"
    echo "${C_CYAN}${line}${C_RESET}"
}
step() { echo ""; echo "${C_CYAN}$1${C_RESET}"; }
info() { echo "  $1"; }
ok()   { echo "${C_GREEN}  $1${C_RESET}"; }
warn() { echo "${C_YELLOW}  $1${C_RESET}"; }
err()  { echo "${C_RED}  $1${C_RESET}"; }

# Trims leading/trailing whitespace without shelling out (portable across
# the ancient bash 3.2 macOS ships by default and any modern bash/Linux).
trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

# ---------------------------------------------------------------------------
# Known-stop-reason handling.
#
# install.ps1 distinguishes "we already explained this on screen" stops
# (throw of a known sentinel string) from a genuinely unexpected failure, so
# the top-level catch block doesn't repeat a raw exception message the user
# already saw explained. Bash has no exception objects to sentinel-match, so
# the same distinction is made structurally instead: every expected failure
# path prints its own explanation and then calls `bail` directly; a generic
# ERR trap only ever fires for a failure none of our explicit checks caught.
# ---------------------------------------------------------------------------
bail() {
    echo ""
    warn "Setup stopped - see the message above for what to do next."
    exit 1
}

on_unexpected_error() {
    local exit_code=$?
    echo ""
    err "Setup hit an unexpected problem (exit code ${exit_code})."
    warn "Nothing beyond what was shown above should have changed. You can safely run scripts/install.sh again."
    exit 1
}
trap on_unexpected_error ERR

# ---------------------------------------------------------------------------
# Portable timeout helper.
#
# install.ps1 guards every external-process probe with a hard timeout
# because on Windows, `python`/`py` on PATH can resolve to a 0-byte "app
# execution alias" stub that pops open the Microsoft Store instead of
# returning a version string - a real, live-confirmed failure mode with no
# macOS/Linux equivalent (there is no comparable stub-executable/store-
# redirect mechanism here). So the stakes of an unbounded call are much
# lower on this platform. Still, a hung `claude` process shouldn't be able
# to freeze this installer forever, so probes below still go through this
# wrapper: it uses GNU coreutils' `timeout` (present on virtually every
# Linux distro) or Homebrew's `gtimeout` (macOS, if the user has installed
# `coreutils`) when available, and simply runs the command directly with no
# hard timeout when neither exists (stock macOS) rather than reimplementing
# job-control timeout logic that can't be tested on a real Mac in this
# environment.
# ---------------------------------------------------------------------------
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN="gtimeout"
fi

with_timeout() {
    local secs="$1"; shift
    if [ -n "$TIMEOUT_BIN" ]; then
        "$TIMEOUT_BIN" "$secs" "$@"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# Step 1: is the `claude` CLI installed at all?
# ---------------------------------------------------------------------------
FOUND_CLAUDE_PATH=""
FOUND_CLAUDE_VERSION=""

# Fast, non-authoritative heads-up only - `claude auth status` reads local
# CLI state, not a live call. The real yes/no this installer acts on is
# always test_claude_login_real (the Agent SDK check) below, mirroring
# install.ps1's Get-ClaudeAuthHint / Test-ClaudeLoginReal split.
print_claude_auth_hint() {
    local claude_path="$1"
    local raw
    if ! raw="$(with_timeout 10 "$claude_path" auth status --json 2>/dev/null)"; then
        return
    fi
    [ -n "$raw" ] || return
    if printf '%s' "$raw" | grep -Eq '"loggedIn"[[:space:]]*:[[:space:]]*true'; then
        info "Quick heads-up from the claude CLI itself: it reports you're logged in."
    else
        info "Quick heads-up from the claude CLI itself: it reports you're NOT logged in yet."
    fi
}

ensure_claude_cli_present() {
    step "[Step 1 of 4] Claude Code"
    info "Checking for the Claude Code CLI ('claude')..."
    if ! command -v claude >/dev/null 2>&1; then
        err "Claude Code (the 'claude' command) isn't installed on this computer."
        info "JobLander needs it - every AI feature runs through your own Claude Code login, JobLander has no AI account of its own."
        info "Install Claude Code first from: https://claude.com/claude-code"
        info "Then run this installer again."
        bail
    fi
    FOUND_CLAUDE_PATH="$(command -v claude)"

    local probe_out
    if ! probe_out="$(with_timeout 10 "$FOUND_CLAUDE_PATH" --version 2>&1)"; then
        err "Found the 'claude' command, but it didn't respond to --version."
        info "Try running 'claude --version' yourself in a terminal to see what's wrong."
        bail
    fi
    FOUND_CLAUDE_VERSION="$(printf '%s' "$probe_out" | head -n 1)"
    ok "Found: $FOUND_CLAUDE_VERSION"

    print_claude_auth_hint "$FOUND_CLAUDE_PATH"
    info "We'll fully verify this for real the same way the app itself does, right after Python is set up (next step)."
}

# ---------------------------------------------------------------------------
# Step 2: Python 3.11+
# ---------------------------------------------------------------------------
FOUND_PYTHON_BIN=""
FOUND_PYTHON_VERSION=""

find_working_python3() {
    if ! command -v python3 >/dev/null 2>&1; then
        return 1
    fi
    local candidate out
    candidate="$(command -v python3)"
    if ! out="$(with_timeout 5 "$candidate" --version 2>&1)"; then
        return 1
    fi
    if [[ "$out" =~ Python[[:space:]]([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
        local major="${BASH_REMATCH[1]}" minor="${BASH_REMATCH[2]}"
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            FOUND_PYTHON_BIN="$candidate"
            FOUND_PYTHON_VERSION="${major}.${minor}.${BASH_REMATCH[3]}"
            return 0
        fi
    fi
    return 1
}

remove_venv_dir() {
    if ! rm -rf "$VENV_DIR" 2>/dev/null || [ -e "$VENV_DIR" ]; then
        err "Could not remove the old JobLander Python environment at:"
        err "  $VENV_DIR"
        info "Please close any programs that might be using it and delete that folder yourself, then run this installer again."
        bail
    fi
}

confirm_venv() {
    if [ -x "$VENV_PYTHON" ]; then
        local out
        if out="$("$VENV_PYTHON" --version 2>&1)" && [[ "$out" =~ Python[[:space:]]3\.(1[1-9]|[2-9][0-9]) ]]; then
            ok "A JobLander Python environment already exists - reusing it."
            return
        fi
        warn "An existing JobLander Python environment looks outdated or broken - recreating it."
        remove_venv_dir
    fi
    info "Creating a dedicated Python environment just for JobLander at:"
    info "  $VENV_DIR"
    info "(This keeps JobLander's packages separate from anything else on your computer - nothing is installed into your system/global Python.)"
    if ! "$FOUND_PYTHON_BIN" -m venv "$VENV_DIR"; then
        err "Failed to create the Python virtual environment."
        info "On Debian/Ubuntu, this often means the 'python3-venv' package isn't installed:"
        info "  sudo apt install python3-venv python3-pip"
        bail
    fi
    if [ ! -x "$VENV_PYTHON" ]; then
        err "Virtual environment creation appeared to succeed, but $VENV_PYTHON is missing."
        bail
    fi
    ok "Environment created."
}

ensure_python_and_venv() {
    step "[Step 2 of 4] Python 3.11 or newer"
    info "Checking for a working python3 3.11+..."
    if ! find_working_python3; then
        err "Couldn't find a working Python 3.11+ (checked for 'python3' on PATH)."
        info "JobLander needs Python 3.11 or newer to run its local backend server. Install it, then run this installer again:"
        info "  macOS:  brew install python3   (Homebrew - see https://brew.sh if you don't have it)"
        info "          or the official installer from https://www.python.org/downloads/"
        info "  Linux:  use your distro's package manager, e.g.:"
        info "            Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip"
        info "            Fedora:         sudo dnf install python3"
        info "            Arch:           sudo pacman -S python"
        bail
    fi
    ok "Found Python $FOUND_PYTHON_VERSION"
    confirm_venv
}

# ---------------------------------------------------------------------------
# pip install with retry (mirrors install.ps1's Install-PipPackagesWithRetry,
# minus the Avast certificate bundle argument - see the file header NOTE).
# ---------------------------------------------------------------------------
install_pip_packages_with_retry() {
    # SSL/connection errors here have been observed (on the Windows side, and
    # plausibly here too) to be transient - a flaky network blip, a proxy or
    # VPN re-negotiating, etc. A few retries after a short, increasing pause
    # cost little and have a real chance of clearing a one-off failure
    # rather than stopping the whole install over something that would have
    # worked a few seconds later. Same 5-attempt/5s-step schedule as
    # install.ps1 (5s/10s/15s/20s pauses).
    local max_attempts=5
    local attempt=1
    while [ "$attempt" -le "$max_attempts" ]; do
        if [ "$attempt" -gt 1 ]; then
            local pause=$(( 5 * (attempt - 1) ))
            warn "Retrying in ${pause} seconds (attempt $attempt of $max_attempts)..."
            sleep "$pause"
        fi
        info "Running: python -m pip install $*"
        if "$VENV_PYTHON" -m pip install "$@"; then
            return 0
        fi
        attempt=$((attempt + 1))
    done

    err "pip failed to install $* after $max_attempts attempt(s)."
    info "If the error above mentions 'certificate verify failed' or 'unable to get local"
    info "issuer certificate', that usually means a corporate proxy, VPN, or other local"
    info "security software is intercepting HTTPS - check your network/proxy setup, or"
    info "try again on a different network."
    info "If it mentions failing to build 'lxml' (a python-docx dependency) from source:"
    info "  Debian/Ubuntu:  sudo apt install libxml2-dev libxslt-dev python3-dev"
    info "  macOS:          xcode-select --install   (installs Xcode Command Line Tools;"
    info "                  a prebuilt wheel usually covers this without it, but this is"
    info "                  the fix if pip ever falls back to a source build)"
    info "You can also try the exact command yourself in a terminal to see the full error:"
    info "  \"$VENV_PYTHON\" -m pip install $*"
    return 1
}

# ---------------------------------------------------------------------------
# Real Claude Code login check - mirrors server/main.py's GET
# /v1/claude-status endpoint (model, max_turns=1, tools=[], timeout), same
# as install.ps1's Test-ClaudeLoginReal. Written to a temp .py file inside
# the app folder (never outside it) and deleted again immediately after.
# ---------------------------------------------------------------------------
CLAUDE_LOGIN_CONNECTED="false"
CLAUDE_LOGIN_DETAIL=""

test_claude_login_real() {
    local check_script="$ROOT_DIR/_joblander_claude_check.tmp.py"
    cat >"$check_script" <<'PYEOF'
import asyncio
import json

from claude_agent_sdk import ClaudeAgentOptions, query

PROMPT = "Reply with exactly one word: OK"
TIMEOUT_SECONDS = 60
MODEL = "claude-sonnet-5"


async def run_check():
    # Same shape as server/main.py's GET /v1/claude-status: no tools, one
    # turn, no project settings loaded - the cheapest real call that still
    # genuinely proves the local Claude Code session can respond. cwd is
    # irrelevant here since tools=[] means nothing ever touches the
    # filesystem through the SDK call itself.
    options = ClaudeAgentOptions(
        model=MODEL,
        permission_mode="bypassPermissions",
        tools=[],
        allowed_tools=[],
        disallowed_tools=[],
        max_turns=1,
        system_prompt="",
        setting_sources=None,
        add_dirs=[],
        agents=None,
        skills=None,
        env={},
        betas=[],
        mcp_servers={},
        plugins=[],
    )

    async def drive():
        async for _message in query(prompt=PROMPT, options=options):
            pass

    try:
        await asyncio.wait_for(drive(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(json.dumps({
            "connected": False,
            "detail": f"Timed out waiting {TIMEOUT_SECONDS}s for the local Claude Code CLI to respond.",
        }))
        return
    except Exception as e:
        print(json.dumps({"connected": False, "detail": str(e) or e.__class__.__name__}))
        return

    print(json.dumps({
        "connected": True,
        "detail": f"Reached Claude Code via the Agent SDK (model {MODEL}).",
    }))


if __name__ == "__main__":
    asyncio.run(run_check())
PYEOF

    local raw
    raw="$("$VENV_PYTHON" "$check_script" 2>/dev/null || true)"
    rm -f "$check_script"

    local json_line
    json_line="$(printf '%s\n' "$raw" | tail -n 1)"

    CLAUDE_LOGIN_CONNECTED="false"
    CLAUDE_LOGIN_DETAIL="Could not run the login check."
    if [ -n "$json_line" ]; then
        # Parse the single JSON line with the venv's own Python (it just
        # produced this JSON, so it's guaranteed to be present) rather than
        # a fragile shell regex.
        local parsed
        if parsed="$("$VENV_PYTHON" -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
    print("true" if d.get("connected") else "false")
    print(d.get("detail", ""))
except Exception:
    print("false")
    print("Could not run the login check.")
' "$json_line" 2>/dev/null)"; then
            CLAUDE_LOGIN_CONNECTED="$(printf '%s\n' "$parsed" | sed -n '1p')"
            CLAUDE_LOGIN_DETAIL="$(printf '%s\n' "$parsed" | sed -n '2p')"
        fi
    fi
}

invoke_claude_login_flow() {
    local claude_path="$1"
    while true; do
        warn "Claude Code isn't logged in (or the session isn't working right now)."
        info "I'm going to run 'claude auth login' for you - it opens your browser so you can sign in."
        info "A browser tab should open in a few seconds. Complete the sign-in there, then come back to this terminal."
        read -r -p "  Press Enter to start sign-in " _ || true
        "$claude_path" auth login || true
        info "Re-checking your Claude Code login..."
        test_claude_login_real
        if [ "$CLAUDE_LOGIN_CONNECTED" = "true" ]; then
            ok "Connected - $CLAUDE_LOGIN_DETAIL"
            return 0
        fi
        err "Still couldn't reach Claude Code: $CLAUDE_LOGIN_DETAIL"
        local answer
        read -r -p "  Try signing in again? [Y/n] " answer || answer=""
        answer="$(trim "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')")"
        if [ "$answer" = "n" ] || [ "$answer" = "no" ]; then
            warn "OK - stopping here. Run this installer again once you've signed in to Claude Code."
            return 1
        fi
    done
}

step_verify_claude_login() {
    local claude_path="$1"
    info "Installing a small helper package (claude-agent-sdk) needed to verify your Claude Code login..."
    if ! install_pip_packages_with_retry claude-agent-sdk; then
        bail
    fi

    step "Verifying your Claude Code login"
    info "This makes one small, real request to Claude Code - it usually takes 15-30 seconds."
    test_claude_login_real
    if [ "$CLAUDE_LOGIN_CONNECTED" = "true" ]; then
        ok "Connected - $CLAUDE_LOGIN_DETAIL"
        return
    fi
    warn "Could not reach Claude Code: $CLAUDE_LOGIN_DETAIL"
    if ! invoke_claude_login_flow "$claude_path"; then
        bail
    fi
}

# ---------------------------------------------------------------------------
# Step 3: remaining dependencies + Playwright's Chromium
# ---------------------------------------------------------------------------
step_install_dependencies() {
    step "[Step 3 of 4] Installing dependencies"
    info "Installing: ${REQUIRED_PACKAGES[*]}"
    if ! install_pip_packages_with_retry "${REQUIRED_PACKAGES[@]}"; then
        bail
    fi
    ok "All dependencies installed."

    step "Installing Playwright's Chromium browser"
    info "JobLander's browser-automation research features use Playwright - this downloads a"
    info "bundled Chromium build that Playwright manages itself (separate from any browser"
    info "you already have installed)."
    if "$VENV_PYTHON" -m playwright install chromium; then
        ok "Playwright's Chromium browser is ready."
    else
        # Deliberately non-fatal: this is a large, separate binary download
        # for a research feature, not the core CV-tailoring functionality
        # this app is built around. Stopping the entire install over a
        # flaky download of an optional browser binary would be a worse
        # experience than finishing setup and letting the user retry this
        # one command later.
        warn "Failed to install Playwright's Chromium browser."
        info "The rest of JobLander will still work. You can try this again later with:"
        info "  \"$VENV_PYTHON\" -m playwright install chromium"
    fi
}

# ---------------------------------------------------------------------------
# Step 4: finish up
# ---------------------------------------------------------------------------
step_finish() {
    step "[Step 4 of 4] Finishing up"
    info "Making sure the launch scripts are executable..."
    chmod +x "$ROOT_DIR/scripts/start-joblander.sh" 2>/dev/null || true
    chmod +x "$ROOT_DIR/scripts/get-joblander.sh" 2>/dev/null || true
    chmod +x "$ROOT_DIR/scripts/install.sh" 2>/dev/null || true
    ok "Done."

    banner "You're all set!"
    echo "${C_GREEN}Run ./scripts/start-joblander.sh any time to open JobLander.${C_RESET}"
    echo "${C_GREEN}It starts the app and opens your browser automatically.${C_RESET}"
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
main() {
    banner "JobLander Setup"
    ensure_claude_cli_present
    ensure_python_and_venv
    step_verify_claude_login "$FOUND_CLAUDE_PATH"
    step_install_dependencies
    step_finish
}

main "$@"
