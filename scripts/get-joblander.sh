#!/usr/bin/env bash
#
# JobLander bootstrap script (macOS / Linux) - downloads the app itself,
# then hands off to the app's own installer.
#
# POSIX port of scripts/get-joblander.ps1. This is meant to be fetched fresh
# every time (e.g. via `curl -fsSL <raw-url>/scripts/get-joblander.sh | bash`
# - see README.md), so - unlike install.sh - it must not assume anything
# about this machine except that bash and an internet connection exist. It
# never assumes install.sh, server/, or any other project file is sitting
# next to it: that is the entire point of this script's existence, exactly
# per get-joblander.ps1's own header comment.
#
# What this script does, in order (mirrors get-joblander.ps1 exactly):
#
#   1. Explain what is about to happen, in plain language, before doing
#      anything.
#   2. Work out where to put the app and, if something is already there,
#      ask what to do instead of silently overwriting it - especially if it
#      looks like a previous install with real saved profiles in it.
#   3. Download the app as a tarball straight from GitHub (no git required)
#      and extract it into that location.
#   4. Hand off to the app's own install.sh so the rest of setup - Claude
#      Code check, Python, the app's dependencies, Playwright - runs
#      completely unchanged. This script does not re-implement any of that.
#   5. Clean up the downloaded tarball and any scratch files; keep only the
#      extracted app.
#
# Every function here is self-contained (no dot-sourcing of install.sh's
# helpers) for the same reason get-joblander.ps1 duplicates its own
# Write-Banner/Step/Info/Ok/Warn/Err instead of dot-sourcing install.ps1's:
# install.sh does not exist on disk yet when this script runs - that is
# exactly the problem this script exists to solve.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_OWNER="edy-dos-santos"
REPO_NAME="joblander"
BRANCH="main"
TARBALL_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.tar.gz"
REPO_PAGE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"

# ---------------------------------------------------------------------------
# Small console-output helpers - deliberately the same shape as install.sh's
# (banner/step/info/ok/warn/err), duplicated rather than sourced (see the
# header comment above for why).
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

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

bail() {
    echo ""
    warn "Setup stopped - see the message above for what to do next."
    exit 1
}

on_unexpected_error() {
    local exit_code=$?
    echo ""
    err "Setup hit an unexpected problem (exit code ${exit_code})."
    exit 1
}
trap on_unexpected_error ERR

# ---------------------------------------------------------------------------
# Where to put the app, and what to do if something is already there.
# ---------------------------------------------------------------------------
# get-joblander.ps1 defaults to Desktop\JobLander via
# [Environment]::GetFolderPath('Desktop'), which correctly resolves a
# redirected/localized Desktop folder on Windows. macOS reliably has
# ~/Desktop the same way. Linux is the platform difference worth flagging:
# there is no universal "Desktop" folder - many minimal/server/WM setups
# have none at all, and where one exists its location is only reliably
# known via the XDG user-dirs mechanism (`xdg-user-dir`, from the
# `xdg-user-dirs` package - common on desktop distros, absent on minimal
# ones). This checks xdg-user-dir first, falls back to a literal ~/Desktop
# if that exists, and finally falls back to ~/JobLander directly (never
# assumes a Desktop folder exists just because it does on Windows/macOS).
get_default_install_dir() {
    local desktop=""
    if command -v xdg-user-dir >/dev/null 2>&1; then
        desktop="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    fi
    if [ -z "$desktop" ] || [ ! -d "$desktop" ]; then
        if [ -d "$HOME/Desktop" ]; then
            desktop="$HOME/Desktop"
        fi
    fi
    if [ -n "$desktop" ] && [ -d "$desktop" ]; then
        echo "${desktop}/JobLander"
    else
        echo "${HOME}/JobLander"
    fi
}

get_next_available_dir() {
    local base_dir="$1"
    local parent name i candidate
    parent="$(dirname "$base_dir")"
    name="$(basename "$base_dir")"
    i=2
    while true; do
        candidate="${parent}/${name} (${i})"
        if [ ! -e "$candidate" ]; then
            echo "$candidate"
            return
        fi
        i=$((i + 1))
    done
}

# Looks for signs that $1 is a previous real JobLander install, and
# specifically whether it has actual saved profile data in it - that is the
# case this script must never silently clobber. Sets globals HAS_PROFILE_DATA
# (0/1) since bash functions can't return structured values.
HAS_PROFILE_DATA=0
looks_like_previous_install() {
    local dir="$1"
    HAS_PROFILE_DATA=0
    local instances_dir="${dir}/instances"
    if [ -d "$instances_dir" ]; then
        # No `-quit` (a GNU findutils extension not available in the BSD
        # find macOS ships by default) - just check whether anything at all
        # comes back.
        local sub
        sub="$(find "$instances_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)"
        if [ -n "$sub" ]; then
            HAS_PROFILE_DATA=1
        fi
    fi
}

# Decides the final install path and mode ('Fresh', 'Update', or 'Cancel'),
# asking the user when the default location already has something in it.
# Sets globals RESOLVED_PATH / RESOLVED_MODE.
RESOLVED_PATH=""
RESOLVED_MODE=""
resolve_install_target() {
    local target
    target="$(get_default_install_dir)"

    if [ ! -e "$target" ]; then
        RESOLVED_PATH="$target"; RESOLVED_MODE="Fresh"; return
    fi

    if [ -d "$target" ] && [ -z "$(ls -A "$target" 2>/dev/null)" ]; then
        # Exists but empty - nothing to protect, safe to use directly.
        RESOLVED_PATH="$target"; RESOLVED_MODE="Fresh"; return
    fi

    looks_like_previous_install "$target"

    if [ "$HAS_PROFILE_DATA" -eq 1 ]; then
        warn "A JobLander folder already exists at:"
        warn "  $target"
        info "It looks like it has your existing profile data in it (a saved 'instances' folder)."
        info "Whatever you choose below, your existing profiles will NOT be deleted or overwritten."
        echo ""
        echo "  [U] Update the app files here, keep my existing profiles/data  (recommended)"
        echo "  [N] Install fresh into a new, separate folder instead - leave this one exactly as it is"
        echo "  [C] Cancel - do nothing"
        while true; do
            local answer a
            read -r -p "Choice [U/n/c] " answer || answer=""
            a="$(trim "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')")"
            case "$a" in
                ""|u) RESOLVED_PATH="$target"; RESOLVED_MODE="Update"; return ;;
                n) RESOLVED_PATH="$(get_next_available_dir "$target")"; RESOLVED_MODE="Fresh"; return ;;
                c) RESOLVED_PATH=""; RESOLVED_MODE="Cancel"; return ;;
                *) warn "Please type U, N, or C." ;;
            esac
        done
    else
        warn "A folder already exists at:"
        warn "  $target"
        info "It doesn't look like it has any saved JobLander profiles in it, but it isn't empty either."
        echo ""
        echo "  [O] Use this folder anyway - JobLander's files will be added/overwritten here  (recommended if this is an old or incomplete JobLander download)"
        echo "  [N] Install fresh into a new, separate folder instead"
        echo "  [C] Cancel - do nothing"
        while true; do
            local answer a
            read -r -p "Choice [O/n/c] " answer || answer=""
            a="$(trim "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')")"
            case "$a" in
                ""|o) RESOLVED_PATH="$target"; RESOLVED_MODE="Update"; return ;;
                n) RESOLVED_PATH="$(get_next_available_dir "$target")"; RESOLVED_MODE="Fresh"; return ;;
                c) RESOLVED_PATH=""; RESOLVED_MODE="Cancel"; return ;;
                *) warn "Please type O, N, or C." ;;
            esac
        done
    fi
}

# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------
# GitHub's branch tarball (not .zip - `tar`/`gzip` are essentially
# guaranteed present on macOS/Linux, whereas `unzip` is not always
# preinstalled on minimal Linux distros; tar.gz is the more POSIX-idiomatic
# choice here, unlike get-joblander.ps1 which uses .zip because
# Expand-Archive/.zip is the native Windows-idiomatic choice there).
download_joblander_tarball() {
    local dest="$1"
    info "Downloading JobLander from GitHub:"
    info "  $TARBALL_URL"
    if command -v curl >/dev/null 2>&1; then
        if ! curl --fail --silent --show-error --location --output "$dest" "$TARBALL_URL"; then
            err "Could not download JobLander from GitHub."
            info "Check your internet connection and try again. If you're on a work/school network, a firewall may be blocking github.com."
            bail
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget --quiet --output-document="$dest" "$TARBALL_URL"; then
            err "Could not download JobLander from GitHub."
            info "Check your internet connection and try again. If you're on a work/school network, a firewall may be blocking github.com."
            bail
        fi
    else
        err "Neither 'curl' nor 'wget' is available on this system - can't download JobLander."
        info "Install curl (on Debian/Ubuntu: sudo apt install curl) and try again."
        bail
    fi
    if [ ! -s "$dest" ]; then
        err "The download appears to have produced an empty file."
        bail
    fi
    ok "Download complete."
}

# GitHub's branch tarballs always nest everything one level deep inside a
# single top-level folder (e.g. joblander-main/) - this finds that folder
# rather than assuming its exact name, so a future branch rename can't
# break it. Sets global EXTRACTED_APP_DIR.
EXTRACTED_APP_DIR=""
expand_joblander_tarball() {
    local tar_path="$1" extract_dir="$2"
    info "Extracting..."
    rm -rf "$extract_dir"
    mkdir -p "$extract_dir"
    if ! tar -xzf "$tar_path" -C "$extract_dir"; then
        err "Could not extract the downloaded archive."
        bail
    fi
    local nested count
    nested="$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d)"
    count="$(printf '%s\n' "$nested" | grep -c . || true)"
    if [ "$count" -ne 1 ]; then
        err "The downloaded archive didn't look the way it should (expected exactly one top-level folder, found $count)."
        bail
    fi
    EXTRACTED_APP_DIR="$nested"
}

# Copies the extracted app's files into the final target folder.
#
# get-joblander.ps1 uses `robocopy ... /E` (no /MIR or /PURGE) specifically
# because it merges a source's *contents* into an existing destination,
# adding/overwriting only what the source actually contains, and never
# deletes anything already in the destination that isn't part of the
# source - critical so a previous install's instances/ (real saved
# profiles) and .venv/ (Python environment) are never touched, since
# neither is ever part of the downloaded source tree.
#
# `cp -R source/. target/` gives the exact same merge semantics on both
# GNU and BSD cp (the trailing "/." copies the directory's *contents*, not
# the directory itself) without needing rsync (not guaranteed present on
# minimal installs) or reimplementing robocopy's own logic.
copy_joblander_files() {
    local source_dir="$1" target_dir="$2"
    mkdir -p "$target_dir"
    info "Copying app files into:"
    info "  $target_dir"
    if ! cp -R "${source_dir}/." "${target_dir}/"; then
        err "Copying the app's files failed."
        bail
    fi
}

# ---------------------------------------------------------------------------
# Hand off to the app's own, already-tested installer. Deliberately invokes
# install.sh directly rather than re-implementing any of its logic - Claude
# Code check, Python/venv, dependencies, Playwright all stay exactly as
# they are.
# ---------------------------------------------------------------------------
invoke_real_installer() {
    local target_dir="$1"
    local install_sh="${target_dir}/scripts/install.sh"
    if [ ! -f "$install_sh" ]; then
        err "Could not find scripts/install.sh inside the downloaded app at:"
        err "  $target_dir"
        info "The download may be incomplete, or the app's layout changed. Try running this bootstrap script again, or download the app manually from $REPO_PAGE_URL."
        bail
    fi
    chmod +x "$install_sh" 2>/dev/null || true
    step "[Step 3 of 3] Handing off to the JobLander installer"
    info "Running install.sh - this checks Claude Code and Python, and installs the app's own dependencies."
    info "(From here on this is the exact same installer JobLander has always used - nothing new is happening.)"
    echo ""
    local exit_code=0
    ( cd "$target_dir" && bash scripts/install.sh ) || exit_code=$?
    return "$exit_code"
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
main() {
    banner "JobLander Setup"
    echo "This is going to:"
    echo "  1. Download JobLander from GitHub (${REPO_PAGE_URL}) as an archive"
    echo "  2. Unpack it onto this computer, into a folder you'll see below"
    echo "  3. Run JobLander's own installer, which checks for Claude Code and Python"
    echo "     and sets up everything else JobLander needs"
    echo ""
    echo "Nothing outside that one folder is touched, other than the small, clearly-"
    echo "explained system checks the installer itself already does in step 3 (like"
    echo "checking whether Python is installed)."
    echo ""
    read -r -p "Press Enter to continue (or Ctrl+C to cancel) " _ || true

    resolve_install_target
    if [ "$RESOLVED_MODE" = "Cancel" ]; then
        warn "Cancelled - nothing was downloaded and nothing changed."
        return 0
    fi
    local target_dir="$RESOLVED_PATH"

    step "[Step 1 of 3] Where JobLander will go"
    info "$target_dir"

    step "[Step 2 of 3] Downloading and unpacking JobLander"
    local stage_root="${TMPDIR:-/tmp}/joblander-bootstrap-$$"
    local tar_path="${stage_root}/joblander.tar.gz"
    local extract_dir="${stage_root}/extract"
    mkdir -p "$stage_root"
    # Clean up the scratch download/extract area regardless of outcome -
    # only the extracted app inside $target_dir is meant to survive.
    trap 'rm -rf "$stage_root"' EXIT

    download_joblander_tarball "$tar_path"
    expand_joblander_tarball "$tar_path" "$extract_dir"
    copy_joblander_files "$EXTRACTED_APP_DIR" "$target_dir"
    ok "JobLander's files are ready."
    rm -rf "$stage_root"
    trap - EXIT

    local exit_code=0
    invoke_real_installer "$target_dir" || exit_code=$?
    echo ""
    if [ "$exit_code" -eq 0 ]; then
        banner "All done!"
        echo "${C_GREEN}JobLander is installed at:${C_RESET}"
        echo "${C_GREEN}  $target_dir${C_RESET}"
        echo "${C_GREEN}From now on, just run ./scripts/start-joblander.sh inside that folder to open it.${C_RESET}"
    else
        warn "The JobLander installer reported a problem (exit code $exit_code) - see the messages above for what to do next."
        info "Your JobLander files are already in place at:"
        info "  $target_dir"
        info "so once it's fixed you can just re-run scripts/install.sh inside that folder - no need to download again."
    fi
}

main "$@"
