"""Standalone, manually-run helper to save a logged-in browser session for
JobLander's server-side job-posting fetcher (server/browser_research.py).

This is NOT part of the always-on FastAPI server and nothing else in this
app ever runs it automatically - you run it yourself, once per site, only
when you want JobLander's job-posting fetch to be able to see pages behind
that site's login wall (LinkedIn, Seek).

Usage (from the JobLander app folder, using its own Python environment so
Playwright is available):

    .venv\\Scripts\\python.exe scripts\\save-login-session.py linkedin
    .venv\\Scripts\\python.exe scripts\\save-login-session.py seek

(On macOS/Linux, or if you're not using the bundled .venv: any Python that
has `playwright` installed and has already run `playwright install
chromium` works the same way - e.g. `python3 scripts/save-login-session.py
linkedin`.)

What it does, step by step:
  1. Launches a HEADED (visible, on-screen) Chromium window via Playwright
     and navigates it to that site's login page.
  2. Waits for YOU to log in yourself, by hand, in that window - typing
     your own username, password, 2FA code, "remember this device", or
     whatever else that site's login flow asks for. This script NEVER
     touches a username or password field itself. That is a hard rule, not
     a suggestion: no credential is ever read, typed, filled, or even seen
     by this code - it only ever looks at cookies/storage AFTER you tell it
     you're done.
  3. Once you've finished logging in, come back to THIS terminal window and
     press Enter - the script is waiting for that signal, not guessing.
  4. Saves Playwright's `storage_state()` (the resulting cookies + local
     storage for that browser context) to browser-sessions/<site>.json.

That saved file is then picked up automatically by
server/browser_research.py the next time you evaluate/tailor/write a cover
letter against a job posting URL on that domain (it prefers a saved session
for known gated domains - see GATED_DOMAINS there - and falls back to a
fresh, logged-out fetch otherwise).

ToS reality, plainly: LinkedIn's and Seek's Terms of Service generally
prohibit automated scraping and browser automation, including by the
account owner and including reusing your own login session with automated
tooling. Running this script, and later reusing the session it saves, is a
deliberate, scoped, personal-use risk this app's owner accepts - the same
posture already taken by piggybacking on a locally logged-in Claude Code
CLI session instead of a paid API key. Nobody's password is ever seen or
stored by this script; only the session cookies YOU produce by logging in
yourself are saved, and only for this single user's own single-user use.

browser-sessions/*.json holds real, working login cookies for your own
accounts - treat those files like passwords. They are already excluded via
.gitignore; never commit or share them.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent
SESSIONS_DIR = APP_ROOT / "browser-sessions"

# Site name -> URL to open first. Keep these as plain landing/login pages,
# not deep links - the user does their own navigating and logging in from
# here, this script doesn't drive anything past the initial goto().
SITES = {
    "linkedin": "https://www.linkedin.com/login",
    "seek": "https://www.seek.com.au/",
}


async def run(site: str) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(
            "Playwright isn't installed in this Python environment.\n"
            "Run: pip install playwright && playwright install chromium"
        )
        return 1

    start_url = SITES[site]
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SESSIONS_DIR / f"{site}.json"

    print(f"Opening a visible Chromium window at:\n  {start_url}")
    print("")
    print("Log in yourself in that window - this script will never touch the login form for you.")
    print("Take as long as you need (password, 2FA, 'remember this device', etc.).")
    print("")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(start_url)

        # Blocking input() on purpose: this is a synchronous, human-paced
        # wait for an explicit "I'm done" signal, run off the event loop
        # via run_in_executor so it doesn't need to poll or guess. Nothing
        # else here needs the event loop free in the meantime - the visible
        # Chromium window is a separate OS process and keeps rendering/
        # responding on its own regardless of what this Python script's
        # single thread is doing.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, input, "\nPress Enter here once you're fully logged in... "
        )

        await context.storage_state(path=str(out_path))
        await browser.close()

    print(f"\nSaved session to: {out_path}")
    print("This file holds real login cookies for your account - never commit or share it.")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SITES:
        print("Usage: python scripts/save-login-session.py <site>")
        print(f"  <site> is one of: {', '.join(sorted(SITES))}")
        return 1
    return asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
