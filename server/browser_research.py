"""Server-side, single-URL page-render fetch for job-posting research.

Why this exists: `/v1/evaluate` (and optionally `/v1/tailor` /
`/v1/cover-letter`) used to rely entirely on the Agent SDK's own
`WebFetch`/`WebSearch` tools for company/job research - a plain server-side
HTTP GET with no session, no cookies, and no JS execution. Sites like
LinkedIn and Seek detect exactly that and serve a login wall, a bot
challenge, or a JS-only shell instead of the real posting. This module
launches a real (headless) Chromium browser via Playwright instead, so the
page actually renders before its text is read back.

Deliberately NOT exposed to the model as a tool it can call itself. This
module is invoked by `server/main.py` as a plain pre-fetch step before the
agent ever runs: fetch once, splice the resulting text into the prompt as
context, then proceed exactly as before. That keeps the behavior
deterministic and auditable (one fetch, one URL, triggered by one explicit
user action) instead of letting the model decide when/what to browse.

ToS reality, plainly: LinkedIn's and Seek's Terms of Service generally
prohibit automated scraping and browser automation - including by the
account owner, and including reusing your own login session for automated
tooling. This module (and `scripts/save-login-session.py`, which produces
the optional saved session it can load) accept that as a deliberate,
scoped, personal-use risk - the same posture this app already takes by
piggybacking on a locally logged-in Claude Code CLI session instead of a
paid API key, rather than anything resold or aimed at anyone else's data.
In service of staying inside that scope: this is a single on-demand fetch
of one URL per explicit evaluate/tailor/cover-letter click - no crawling,
no following links, no pagination, no background/scheduled scraping, and no
attempt to defeat a CAPTCHA or bot-challenge if one appears (see the
timeout/failure handling below - it fails cleanly with a clear message
instead).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("jaa-backend.browser_research")

SERVER_DIR = Path(__file__).resolve().parent
APP_ROOT = SERVER_DIR.parent

# Sibling to instances/, NOT inside it: a saved login session is tied to the
# user's own LinkedIn/Seek account, shared across every candidate profile -
# it is not per-profile data, so it does not belong under instances/<id>/.
SESSIONS_DIR = APP_ROOT / "browser-sessions"

# Domains known to gate plain fetches behind a login wall or bot challenge.
# Job postings on these are worth trying with a saved login session (if one
# exists - see scripts/save-login-session.py) rather than a fresh,
# cookie-less browser context, which on these specific sites often still
# hits a device-verification checkpoint even when freshly rendered.
GATED_DOMAINS = ("linkedin.com", "seek.com.au")

DEFAULT_TIMEOUT_S = 20

# Roughly a few thousand words - enough for a full job posting plus some
# surrounding company-page context, without letting an unexpectedly huge
# page (or a scraped nav/footer-heavy shell) blow up prompt context.
MAX_CHARS = 20_000

_BARE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def is_bare_url(text: str) -> bool:
    """True if `text`, once stripped, is nothing BUT a single http(s) URL -
    e.g. what a user pasted into a "job posting" box instead of the actual
    description text - not prose that merely mentions a URL somewhere
    inside it. Mirrors the intent of the frontend's own existing
    `isUrl`/`fetchJdFromUrl` check (job-application-assistant.html), but is
    intentionally stricter (whole-string match, not just a leading
    `https?://`) since here the entire field is re-purposed as the actual
    fetch target rather than one input among several.
    """
    return bool(_BARE_URL_RE.match((text or "").strip()))


def should_use_saved_session(url: str) -> bool:
    """True if `url`'s domain is one of GATED_DOMAINS - callers should pass
    `use_saved_session=True` to `fetch_rendered_text` for these, so a saved
    login session (if one has been set up via
    scripts/save-login-session.py) gets used instead of a fresh, logged-out
    browser context."""
    lowered = (url or "").lower()
    return any(domain in lowered for domain in GATED_DOMAINS)


def _session_file_for(url: str) -> Path | None:
    """Map `url`'s domain to a saved-session JSON file under
    browser-sessions/, if one exists on disk. Returns None if no matching
    session file is present - callers should proceed with a fresh,
    logged-out context rather than fail."""
    lowered = (url or "").lower()
    for domain in GATED_DOMAINS:
        if domain in lowered:
            site_name = domain.split(".")[0]  # "linkedin.com" -> "linkedin"
            candidate = SESSIONS_DIR / f"{site_name}.json"
            if candidate.is_file():
                return candidate
    return None


async def fetch_rendered_text(
    url: str,
    use_saved_session: bool = False,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Launch headless Chromium, navigate to `url`, let the page settle,
    and return its visible body text, truncated to MAX_CHARS.

    Single on-demand fetch of exactly one URL - no crawling, no following
    links, no retries beyond Playwright's own navigation, no pagination.
    Uses Playwright's default Chromium User-Agent (a normal desktop
    browser's) unmodified - nothing here spoofs or disguises the request.

    Never raises past this function: a missing Playwright install, a
    navigation timeout, a blocked/challenged page, or any other failure all
    come back as a short human-readable string starting with
    "[browser-research error]" rather than an exception, so callers can
    splice the return value straight into a prompt without their own
    try/except. If a bot-challenge or CAPTCHA appears, this deliberately
    does not attempt to detect or defeat it - it just reads back whatever
    text the page actually shows (which will typically make the challenge
    obvious in the returned text) or times out cleanly.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return (
            "[browser-research error] Playwright isn't installed in this environment. "
            "Re-run the installer, or run: pip install playwright && playwright install chromium"
        )

    session_file = _session_file_for(url) if use_saved_session else None
    timeout_ms = max(1, int(timeout_s)) * 1000
    text = ""

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context_kwargs: dict = {}
                if session_file is not None:
                    context_kwargs["storage_state"] = str(session_file)
                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Bounded settle time for client-rendered pages (React/Vue
                # job boards typically paint their real content shortly
                # after the bare DOM event fires) - a fixed short wait, not
                # a poll loop or a wait for network idle that could hang on
                # background requests, keeping this a single deterministic
                # fetch rather than anything crawl-like.
                await page.wait_for_timeout(2000)
                text = (await page.inner_text("body")).strip()
            finally:
                await browser.close()
    except PlaywrightTimeoutError:
        logger.warning("browser_research: timed out loading %s", url)
        return (
            f"[browser-research error] Timed out loading {url} after {timeout_s}s "
            "(the site may be slow, or may be blocking automated access)."
        )
    except Exception as e:
        logger.warning("browser_research: failed to fetch %s: %s", url, e)
        return f"[browser-research error] Could not fetch {url}: {e}"

    if not text:
        return (
            f"[browser-research error] Page at {url} loaded but returned no visible text "
            "(possibly a bot-challenge, login wall, or JS-only shell that never rendered)."
        )

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[...content truncated...]"
    return text
