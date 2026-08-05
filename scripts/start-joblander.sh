#!/usr/bin/env bash
#
# Launches JobLander: starts the local server from its dedicated Python
# environment, waits for it to come up (polling, not a blind sleep), then
# opens your browser. POSIX port of scripts/start-joblander.ps1 - see that
# file for the Windows equivalent; the "why" behind each step is the same,
# only the mechanics differ.
#
# Run this directly: bash scripts/start-joblander.sh
# (or: chmod +x scripts/start-joblander.sh && ./scripts/start-joblander.sh)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
SERVER_DIR="$ROOT_DIR/server"
URL="http://127.0.0.1:8787/"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "JobLander hasn't been set up yet."
    echo "Please run scripts/install.sh first."
    exit 1
fi

echo "Starting JobLander..."
echo "Leave this window open while you use the app - closing it stops the server."
echo ""

# Same invocation start-joblander.ps1 uses ($VenvPython main.py with
# WorkingDirectory = server\) - `exec` inside the subshell replaces the
# subshell with the python process itself, so SERVER_PID below refers to
# the real server process, not a short-lived wrapper around it.
(cd "$SERVER_DIR" && exec "$VENV_PYTHON" main.py) &
SERVER_PID=$!

# Mirrors "closing this window stops the server": if this script exits for
# any reason (normal exit, Ctrl+C, the terminal closing), make sure the
# server child goes down with it instead of being orphaned.
cleanup() {
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM HUP

# Prefer curl (present on virtually every modern macOS/Linux install); fall
# back to wget if curl isn't available. If neither is present, skip the
# readiness poll entirely rather than failing outright over a missing tool
# this script doesn't strictly need - the browser will just be opened
# without first confirming the server answered.
PROBE_CMD=""
if command -v curl >/dev/null 2>&1; then
    PROBE_CMD="curl"
elif command -v wget >/dev/null 2>&1; then
    PROBE_CMD="wget"
fi

probe_server_up() {
    case "$PROBE_CMD" in
        curl) curl --silent --show-error --max-time 2 --output /dev/null "$URL" ;;
        wget) wget --quiet --timeout=2 --tries=1 --output-document=/dev/null "$URL" ;;
        *) return 1 ;;
    esac
}

# Real wall-clock elapsed time (via `date +%s`), not a hand-accumulated
# counter - matches start-joblander.ps1's own Stopwatch-based wait, which
# was written specifically because a failed request to a closed port can
# itself take a couple of seconds to time out; tracking only the sleep
# duration would let the real wait run well past the intended cap.
MAX_WAIT_SECONDS=30
UP=0
START_TS=$(date +%s)

while true; do
    elapsed=$(( $(date +%s) - START_TS ))
    if [ "$elapsed" -ge "$MAX_WAIT_SECONDS" ]; then
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "The server process exited unexpectedly before it came up."
        break
    fi
    if [ -n "$PROBE_CMD" ] && probe_server_up; then
        UP=1
        break
    fi
    # 1-second poll interval, not start-joblander.ps1's 500ms: BSD `sleep`
    # (macOS's default, non-GNU-coreutils implementation) has historically
    # only guaranteed whole-second resolution, so a fractional interval
    # here would be relying on behavior this environment can't verify
    # across every target Mac. A 1s interval against a 30s cap is still
    # plenty responsive.
    sleep 1
done

open_browser() {
    local url="$1"
    if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 &
        return 0
    fi
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
        return 0
    fi
    return 1
}

if [ "$UP" -eq 1 ]; then
    echo "JobLander is up - opening your browser..."
    if ! open_browser "$URL"; then
        echo "Could not find a way to open your browser automatically (no 'open' or 'xdg-open' found)."
        echo "Open this address yourself: $URL"
    fi
elif kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "The server didn't respond within ${MAX_WAIT_SECONDS} seconds."
    echo "It may still be starting - try opening $URL yourself in a moment, or check for errors above."
fi

echo ""
echo "Server is running. Close this window (or press Ctrl+C) to stop JobLander."
wait "$SERVER_PID"
