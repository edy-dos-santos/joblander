<#
    JobLander installer.

    Run via Install-JobLander.bat (double-click it - don't run this file
    directly unless you know what you're doing with PowerShell execution
    policy).

    Order of operations (see runs\30-implement-installer.md for the full
    writeup of why, and what was live-tested vs. reasoned-through):

      1. Claude Code   - confirm the `claude` CLI is installed at all, then
                          (after Python is ready, since the real check needs
                          it - see below) verify it's actually logged in
                          using the same kind of minimal Claude Agent SDK
                          call server\main.py's own GET /v1/claude-status
                          endpoint uses. If not logged in, run the sign-in
                          flow for the user and re-check.
      2. Python 3.11+   - find a working install, or offer to install one via
                          winget; create a dedicated virtual environment
                          inside this app's own folder (never touches the
                          system/global Python).
      3. Dependencies   - install this app's Python packages into that venv,
                          working around the Avast/pip SSL issue this
                          project already hit once, if Avast is present.
      4. Finish         - write Start-JobLander.bat so the app can be
                          launched normally from now on.

    Every step prints what it's doing and why *before* doing anything that
    reaches outside this app's own folder (installing Python system-wide,
    signing in to Claude Code) - nothing here should ever surprise someone
    who isn't a programmer.
#>

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
$Root = $PSScriptRoot
$ServerDir = Join-Path $Root 'server'
$VenvDir = Join-Path $Root '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$RequiredPackages = @('fastapi', 'uvicorn', 'python-docx', 'jinja2', 'httpx', 'pydantic', 'claude-agent-sdk')
$AvastCertPath = 'C:\ProgramData\Avast Software\Avast\wscert.pem'
$AppUrl = 'http://127.0.0.1:8787/'

# Sentinel exception messages used with `throw` below, so the top-level
# catch block can tell "we already explained this on screen, don't repeat
# the raw message" apart from a genuinely unexpected failure.
$KnownStopReasons = @('claude-cli-missing', 'python-missing', 'claude-login-incomplete', 'venv-failed', 'pip-failed')

# ---------------------------------------------------------------------------
# Small console-output helpers
# ---------------------------------------------------------------------------
function Write-Banner {
    param([string]$Text)
    $line = '=' * ([Math]::Max(40, $Text.Length + 4))
    Write-Host ""
    Write-Host $line -ForegroundColor DarkCyan
    Write-Host " $Text" -ForegroundColor White
    Write-Host $line -ForegroundColor DarkCyan
}
function Write-Step { param([string]$Text) Write-Host ""; Write-Host $Text -ForegroundColor Cyan }
function Write-Info { param([string]$Text) Write-Host "  $Text" }
function Write-Ok   { param([string]$Text) Write-Host "  $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  $Text" -ForegroundColor Yellow }
function Write-Err  { param([string]$Text) Write-Host "  $Text" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Timeout-guarded process probe.
#
# Why this exists instead of just `& python --version`: on a machine where
# Python was never installed, `python`/`py` on PATH can resolve to Windows'
# own 0-byte "app execution alias" stub (confirmed present on this dev
# machine at $env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe, py.exe,
# etc. - Get-Command finds it happily, it just isn't a real interpreter).
# Depending on Windows version/config, invoking that stub can pop open the
# Microsoft Store rather than returning a version string - exactly the kind
# of surprise this installer must never cause a non-technical user. Running
# every probe through .NET's own Process class with redirected output and a
# hard timeout means: if anything unexpected happens (a GUI pops, the alias
# hangs, whatever), we kill it and just treat that candidate as "not a
# working Python" instead of hanging or losing control of the console.
# ---------------------------------------------------------------------------
function Invoke-ProbeProcess {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int]$TimeoutMs = 5000
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = ($ArgumentList -join ' ')
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        [void]$proc.Start()
    } catch {
        return $null
    }

    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $finished = $proc.WaitForExit($TimeoutMs)
    if (-not $finished) {
        try { $proc.Kill() } catch {}
        return $null
    }

    $out = $stdoutTask.GetAwaiter().GetResult()
    $err = $stderrTask.GetAwaiter().GetResult()
    return [PSCustomObject]@{ ExitCode = $proc.ExitCode; StdOut = $out; StdErr = $err }
}

# ---------------------------------------------------------------------------
# Step 1 (part A): is the `claude` CLI installed at all?
# ---------------------------------------------------------------------------
function Test-ClaudeCliInstalled {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    $probe = Invoke-ProbeProcess -FilePath $cmd.Source -ArgumentList @('--version') -TimeoutMs 10000
    if (-not $probe -or $probe.ExitCode -ne 0 -or -not $probe.StdOut) { return $null }
    return [PSCustomObject]@{ Version = $probe.StdOut.Trim(); Path = $cmd.Source }
}

# Fast, non-authoritative heads-up only - `claude auth status` reads local
# CLI state, not a live call. The real yes/no this installer acts on is
# always Test-ClaudeLoginReal (the Agent SDK check) below, per the task's
# instruction to reuse server\main.py's own /v1/claude-status technique
# rather than inventing a different check.
function Get-ClaudeAuthHint {
    param([string]$ClaudePath)
    $probe = Invoke-ProbeProcess -FilePath $ClaudePath -ArgumentList @('auth', 'status', '--json') -TimeoutMs 10000
    if (-not $probe -or $probe.ExitCode -ne 0 -or -not $probe.StdOut) { return $null }
    try { return ($probe.StdOut | ConvertFrom-Json) } catch { return $null }
}

function Step-EnsureClaudeCliPresent {
    Write-Step "[Step 1 of 4] Claude Code"
    Write-Info "Checking for the Claude Code CLI ('claude')..."
    $claude = Test-ClaudeCliInstalled
    if (-not $claude) {
        Write-Err "Claude Code (the 'claude' command) isn't installed on this computer."
        Write-Info "JobLander needs it - every AI feature runs through your own Claude Code login, JobLander has no AI account of its own."
        Write-Info "Install Claude Code first from: https://claude.com/claude-code"
        Write-Info "Then run this installer again."
        throw "claude-cli-missing"
    }
    Write-Ok "Found: $($claude.Version)"

    $hint = Get-ClaudeAuthHint -ClaudePath $claude.Path
    if ($hint -and $hint.loggedIn) {
        Write-Info "Quick heads-up from the claude CLI itself: it reports you're logged in ($($hint.email))."
    } elseif ($hint) {
        Write-Info "Quick heads-up from the claude CLI itself: it reports you're NOT logged in yet."
    }
    Write-Info "We'll fully verify this for real the same way the app itself does, right after Python is set up (next step)."
    return $claude
}

# ---------------------------------------------------------------------------
# Step 2: Python 3.11+
# ---------------------------------------------------------------------------
function Find-WorkingPython {
    $candidates = @(
        @{ Exe = 'python'; Args = @() },
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'py'; Args = @('-3.11') },
        @{ Exe = 'py'; Args = @('-3.14') },
        @{ Exe = 'py'; Args = @('-3') }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $probeArgs = @($c.Args) + @('--version')
        $probe = Invoke-ProbeProcess -FilePath $cmd.Source -ArgumentList $probeArgs -TimeoutMs 5000
        if (-not $probe) { continue }
        $text = "$($probe.StdOut)$($probe.StdErr)"
        if ($text -match 'Python\s+(\d+)\.(\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]; $patch = $Matches[3]
            if ($major -eq 3 -and $minor -ge 11) {
                return [PSCustomObject]@{
                    Exe          = $c.Exe
                    Args         = $c.Args
                    Version      = "$major.$minor.$patch"
                    ResolvedPath = $cmd.Source
                }
            }
        }
    }
    return $null
}

function Update-SessionPathFromRegistry {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machinePath, $userPath) -join ';'
}

function Install-PythonViaWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warn "winget (Windows' built-in app installer) isn't available on this computer."
        return $false
    }

    Write-Warn "About to install Python 3.11 system-wide, using Windows' built-in 'winget' installer."
    Write-Info "This installs the official python.org build - the standard, least-invasive way to get Python on Windows, same as downloading it yourself."
    Write-Info "You may see a Windows security / User Account Control prompt - please approve it to continue."
    $answer = Read-Host "  Install Python 3.11 now? [Y/n]"
    if ($answer -match '^(n|no)$') {
        Write-Warn "Skipped. Install Python 3.11+ yourself from https://www.python.org/downloads/ and run this installer again."
        return $false
    }

    Write-Info "Running: winget install --id Python.Python.3.11 ..."
    # Piped through Out-Host deliberately: without it, winget's own console
    # output becomes part of *this function's* return value alongside the
    # $true/$false below (PowerShell aggregates every uncaptured output in
    # a function into its return value, not just what follows `return`) -
    # found the hard way when it broke Invoke-PipInstall's exit-code check
    # below in exactly this way during testing. Out-Host sends the output
    # straight to the console instead, so only the boolean comes back.
    & winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements | Out-Host
    $exit = $LASTEXITCODE
    Update-SessionPathFromRegistry
    if ($exit -ne 0) {
        Write-Warn "winget reported a problem installing Python (exit code $exit)."
        return $false
    }
    return $true
}

# Removes an existing (broken/outdated) venv directory for real - never
# silently no-ops. On this machine, plain `Remove-Item -Recurse -Force` can
# fail on the venv's ROOT directory specifically with "Access to the path is
# denied" - a known Windows PowerShell 5.1 `-Recurse` defect, aggravated by
# Avast's real-time file shield (confirmed live: every file inside deletes
# fine, only the root directory delete is denied; happens on both a
# populated and a pristine venv; intermittent - timing/AV-scan-dependent,
# not guaranteed every run). The old `-ErrorAction SilentlyContinue` on that
# line swallowed exactly this failure and let the script print "Environment
# created." over the untouched old environment (thousands of stale files,
# including old site-packages) - a silent false success. This function tries
# Remove-Item first (the common case, which usually just works), and if that
# doesn't fully clear the directory, falls back to `cmd /c rmdir /s /q`
# (proven on this machine to succeed where Remove-Item's own -Recurse does
# not). Either way, it verifies the directory is actually gone before
# returning - if it's still there after both attempts, it throws instead of
# letting the caller believe the environment was rebuilt.
function Remove-VenvDirectory {
    try {
        Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Warn "Could not fully remove the old environment the normal way - trying a different method..."
        & cmd /c "rmdir /s /q `"$VenvDir`"" | Out-Host
    }
    if (Test-Path -LiteralPath $VenvDir) {
        Write-Err "Could not remove the old JobLander Python environment at:"
        Write-Err "  $VenvDir"
        Write-Info "Please close any programs that might be using it (including File Explorer windows open on that folder), delete that folder yourself, and run this installer again."
        throw "venv-failed"
    }
}

function Confirm-Venv {
    param($Python)
    if (Test-Path -LiteralPath $VenvPython) {
        $probe = Invoke-ProbeProcess -FilePath $VenvPython -ArgumentList @('--version') -TimeoutMs 5000
        if ($probe -and "$($probe.StdOut)$($probe.StdErr)" -match 'Python\s+3\.(1[1-9]|[2-9]\d)') {
            Write-Ok "A JobLander Python environment already exists - reusing it."
            return
        }
        Write-Warn "An existing JobLander Python environment looks outdated or broken - recreating it."
        Remove-VenvDirectory
    }
    Write-Info "Creating a dedicated Python environment just for JobLander at:"
    Write-Info "  $VenvDir"
    Write-Info "(This keeps JobLander's packages separate from anything else on your computer - nothing is installed into your system/global Python.)"
    $venvArgs = @($Python.Args) + @('-m', 'venv', $VenvDir)
    & $Python.ResolvedPath @venvArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create the Python virtual environment (exit code $LASTEXITCODE)."
        throw "venv-failed"
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Err "Virtual environment creation appeared to succeed, but $VenvPython is missing."
        throw "venv-failed"
    }
    Write-Ok "Environment created."
}

function Step-EnsurePythonAndVenv {
    Write-Step "[Step 2 of 4] Python 3.11 or newer"
    Write-Info "Checking for a working Python 3.11+..."
    $py = Find-WorkingPython
    if (-not $py) {
        Write-Warn "No working Python 3.11+ found on this computer."
        if (Install-PythonViaWinget) {
            Write-Info "Re-checking for Python now that installation finished..."
            $py = Find-WorkingPython
        }
        if (-not $py) {
            Write-Err "Still couldn't find a working Python 3.11+."
            Write-Info "Please install it yourself from https://www.python.org/downloads/ (get 3.11 or newer, and tick 'Add python.exe to PATH' during setup), then run this installer again."
            throw "python-missing"
        }
    }
    Write-Ok "Found Python $($py.Version)"
    Confirm-Venv -Python $py
}

# ---------------------------------------------------------------------------
# Avast / pip SSL workaround.
#
# Root cause (confirmed via live repro, 2026-08-03 - see
# joblander-pip-avast-ssl-fix.md for the full diagnostic writeup): passing
# `--cert <wscert.pem>` alone is NOT a fix, it is a trap. Two facts combine:
#   1. wscert.pem contains exactly ONE certificate - Avast's own Web/Mail
#      Shield root - nothing else.
#   2. pip's `--cert` REPLACES the entire CA bundle. It does not add to it.
# So a bare `--cert $AvastCertPath` only verifies while Avast's Web Shield
# happens to be actively intercepting *that specific connection* (server
# cert chain terminates at the one root in the bundle). The moment Web
# Shield isn't intercepting - mid-update, temporarily disabled, a per-app
# exclusion, or just inconsistent per-connection behavior - pip sees the
# REAL public pypi.org certificate chain, which can never verify against a
# bundle containing only the Avast root. This is exactly why the failure
# looked intermittent: it was a deterministic function of Avast's
# interception state at that moment, not a flaky network blip, and retrying
# the same broken bundle cannot fix a state that hasn't changed.
#
# Fix: never use the Avast root alone. Build a UNION bundle - pip's own
# vendored certifi (the public CA set, always present since pip ships it)
# PLUS the Avast root appended - so verification succeeds in BOTH states.
# See New-CombinedCaBundle below.
# ---------------------------------------------------------------------------
function Get-AvastCertPathIfPresent {
    if (Test-Path -LiteralPath $AvastCertPath) { return $AvastCertPath }
    return $null
}

function New-CombinedCaBundle {
    # Returns a path to a CA bundle containing BOTH the public CAs (from
    # pip's own vendored certifi - a pure local/offline read, no network)
    # AND the Avast root, if present. Written inside $Root only (hard rule
    # 2: never write outside the app folder) and regenerated fresh on every
    # run (cheap - a local file copy plus a read) so it can never go stale
    # if Avast's cert or pip's vendored certifi bundle ever changes.
    $baseBundle = & $VenvPython -c "from pip._vendor import certifi; print(certifi.where())"
    if (-not $baseBundle -or -not (Test-Path -LiteralPath $baseBundle)) { return $null }
    $combined = Join-Path $Root '.joblander-ca-bundle.pem'
    Copy-Item -LiteralPath $baseBundle -Destination $combined -Force
    $avast = Get-AvastCertPathIfPresent
    if ($avast) {
        # Certifi's own bundle file ends with a trailing newline already,
        # but adding one more here costs nothing and guarantees the two
        # PEM blocks never end up glued onto the same line regardless of
        # how the source file happened to end.
        Add-Content -LiteralPath $combined -Value ""
        Add-Content -LiteralPath $combined -Value (Get-Content -LiteralPath $avast -Raw)
    }
    return $combined
}

function Test-AvastRunning {
    if (Get-Process -Name 'AvastSvc', 'AvastUI' -ErrorAction SilentlyContinue) { return $true }
    if (Get-Service -Name 'AvastSvc' -ErrorAction SilentlyContinue) { return $true }
    return $false
}

function Invoke-PipInstall {
    param([string[]]$Packages, [string]$CertPath)
    $pipArgs = @('-m', 'pip', 'install')
    if ($CertPath) { $pipArgs += @('--cert', $CertPath) }
    $pipArgs += $Packages
    Write-Info "Running: python -m pip install $(if ($CertPath) { '--cert <avast-certificate> ' })$($Packages -join ' ')"
    # Out-Host (not a bare call, not `2>&1`) - see the comment in
    # Install-PythonViaWinget for why: this function `return`s $LASTEXITCODE,
    # and a bare `& $VenvPython @pipArgs` here would silently fold pip's
    # entire console output into that return value instead, making
    # `if ($exit -ne 0)` always true downstream. Confirmed as a real,
    # live-reproduced bug during testing (pip genuinely succeeded but was
    # reported as failed) before this fix.
    & $VenvPython @pipArgs | Out-Host
    return $LASTEXITCODE
}

# Shared by every pip-install call site in this script (there were two -
# the dependency-install step and the earlier claude-agent-sdk-only
# install for the login check - and a retry/guidance fix applied to only
# one of them is exactly how a real transient-SSL-failure report from the
# owner turned out to still reproduce: the second call site had no retry
# at all. Fixing this here once, and having every caller go through it,
# means that class of miss can't happen again.
function Install-PipPackagesWithRetry {
    param([string[]]$Packages, [string]$CertPath)
    # SSL/connection errors here have been observed to be transient (antivirus
    # web-shields periodically re-establish their interception certificate;
    # a flaky network blip can also produce the exact same
    # "unable to get local issuer certificate" pip error even with a correct
    # --cert). A few retries after a short pause cost little and have a real
    # chance of clearing a one-off failure rather than stopping the whole
    # install over something that would've worked a few seconds later.
    # Confirmed live (2026-08-03): 3 attempts at a 5s pause was not always
    # enough - a real install run failed all 3, then the identical command
    # against the identical venv succeeded immediately moments later when
    # tried again by hand. That means the underlying interruption can
    # outlast ~15-20s. Widened to 5 attempts with a longer, increasing pause
    # (5s/10s/15s/20s) to give a longer blip more room to actually clear,
    # while still being bounded (not an infinite/silent hang).
    $maxAttempts = 5
    $exit = 1
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        if ($attempt -gt 1) {
            $pauseSeconds = 5 * ($attempt - 1)
            Write-Warn "Retrying in $pauseSeconds seconds (attempt $attempt of $maxAttempts)..."
            Start-Sleep -Seconds $pauseSeconds
        }
        $exit = Invoke-PipInstall -Packages $Packages -CertPath $CertPath
        if ($exit -eq 0) { return $true }
    }

    Write-Err "pip failed to install $($Packages -join ', ') after $maxAttempts attempt(s) (exit code $exit)."
    if ($CertPath) {
        Write-Info "A combined certificate bundle was used ($CertPath), which should work whether or"
        Write-Info "not Avast is intercepting this connection - if the error above still mentions"
        Write-Info "'certificate verify failed' or 'unable to get local issuer certificate', that points"
        Write-Info "at something more specific than a routine Avast state change. Things to try: re-run"
        Write-Info "this installer (in case it's still transient); check whether Avast's Web Shield has"
        Write-Info "an active block or per-app rule for this Python; or check your network/proxy setup."
    }
    $certArgForDisplay = if ($CertPath) { '--cert "' + $CertPath + '" ' } else { '' }
    Write-Info "You can also try the exact command yourself in a terminal to see the full error:"
    Write-Info ('  "' + $VenvPython + '" -m pip install ' + $certArgForDisplay + ($Packages -join ' '))
    return $false
}

# ---------------------------------------------------------------------------
# Real Claude Code login check - mirrors server\main.py's GET
# /v1/claude-status endpoint (model, max_turns=1, tools=[], timeout) as
# instructed, rather than inventing a different technique. Written to a
# temp .py file inside the app folder (never outside it - hard rule 2) and
# deleted again immediately after running.
# ---------------------------------------------------------------------------
function Test-ClaudeLoginReal {
    $checkScript = Join-Path $Root '_joblander_claude_check.tmp.py'
    $pyCode = @'
import asyncio
import json

from claude_agent_sdk import ClaudeAgentOptions, query

PROMPT = "Reply with exactly one word: OK"
TIMEOUT_SECONDS = 60
MODEL = "claude-sonnet-5"


async def run_check():
    # Same shape as server\main.py's GET /v1/claude-status: no tools, one
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
'@
    # Plain "ascii" (not "utf8NoBOM" - that encoding name only exists in
    # PowerShell 7+/Core; Windows PowerShell 5.1's Set-Content only knows
    # Unicode/UTF8(-with-BOM)/UTF7/UTF32/Ascii/Default/Oem/BigEndianUnicode/
    # BigEndianUTF32, and rejects utf8NoBOM outright - confirmed by testing
    # this script for real on this machine's Windows PowerShell 5.1). The
    # script content below is pure ASCII, so this is a safe, simple choice.
    Set-Content -LiteralPath $checkScript -Value $pyCode -Encoding ascii

    try {
        # Deliberately not `2>&1` - PowerShell 5.1 wraps a native command's
        # stderr lines as NativeCommandError records under that operator.
        # Plain assignment captures only stdout (the single JSON line);
        # Python's own stderr, if any, still streams straight to the
        # console for the user to see.
        $raw = & $VenvPython $checkScript
        $exit = $LASTEXITCODE
    } finally {
        Remove-Item -LiteralPath $checkScript -Force -ErrorAction SilentlyContinue
    }

    $jsonLine = $raw | Select-Object -Last 1
    try {
        $obj = $jsonLine | ConvertFrom-Json
        return [PSCustomObject]@{ Connected = [bool]$obj.connected; Detail = [string]$obj.detail }
    } catch {
        return [PSCustomObject]@{ Connected = $false; Detail = "Could not run the login check (exit code $exit)." }
    }
}

function Invoke-ClaudeLoginFlow {
    param([string]$ClaudePath)
    while ($true) {
        Write-Warn "Claude Code isn't logged in (or the session isn't working right now)."
        Write-Info "I'm going to run 'claude auth login' for you - it opens your browser so you can sign in."
        Write-Info "A browser tab should open in a few seconds. Complete the sign-in there, then come back to this window."
        # $null = ... (not a bare Read-Host) - this function returns
        # $true/$false, and Read-Host emits whatever the user typed to the
        # success output stream. A bare, unassigned Read-Host here silently
        # became part of THIS function's own return value alongside the
        # real boolean below - the exact same PowerShell return-stream
        # gotcha documented at the pip/winget call sites, just via Read-Host
        # instead of an external process. Confirmed live: it turned this
        # function's return into a 2-element array (@("", $false)) that is
        # ALWAYS truthy, so a user who declined the retry was silently
        # treated as if login had succeeded. See runs\34-final-clean-slate-prep.md.
        $null = Read-Host "  Press Enter to start sign-in"
        # Out-Host for the same reason as the pip/winget calls above - this
        # function returns $true/$false and a bare call here would leak
        # `claude auth login`'s own console output into that return value.
        & $ClaudePath auth login | Out-Host
        Write-Info "Re-checking your Claude Code login..."
        $status = Test-ClaudeLoginReal
        if ($status.Connected) {
            Write-Ok "Connected - $($status.Detail)"
            return $true
        }
        Write-Err "Still couldn't reach Claude Code: $($status.Detail)"
        $answer = Read-Host "  Try signing in again? [Y/n]"
        if ($answer -match '^(n|no)$') {
            Write-Warn "OK - stopping here. Run this installer again once you've signed in to Claude Code."
            return $false
        }
    }
}

function Step-VerifyClaudeLogin {
    param($Claude, [string]$CertPath)
    Write-Info "Installing a small helper package (claude-agent-sdk) needed to verify your Claude Code login..."
    if (-not (Install-PipPackagesWithRetry -Packages @('claude-agent-sdk') -CertPath $CertPath)) {
        throw "pip-failed"
    }

    Write-Step "Verifying your Claude Code login"
    Write-Info "This makes one small, real request to Claude Code - it usually takes 15-30 seconds."
    $status = Test-ClaudeLoginReal
    if ($status.Connected) {
        Write-Ok "Connected - $($status.Detail)"
        return
    }
    Write-Warn "Could not reach Claude Code: $($status.Detail)"
    # Captured into a variable and compared with -ne $true (not "if (-not
    # (...))" on the raw call) deliberately: a bare "-not (...)" trusts
    # PowerShell truthiness, and an array of any length >= 2 is ALWAYS
    # truthy regardless of what the elements are - which is exactly how the
    # unassigned-Read-Host bug above went undetected here. Testing strict
    # equality to $true catches "not exactly the boolean true" even if some
    # future edit reintroduces stray output into Invoke-ClaudeLoginFlow's
    # return value.
    $loginCompleted = Invoke-ClaudeLoginFlow -ClaudePath $Claude.Path
    if ($loginCompleted -ne $true) {
        throw "claude-login-incomplete"
    }
}

# ---------------------------------------------------------------------------
# Step 3: remaining dependencies
# ---------------------------------------------------------------------------
function Step-InstallDependencies {
    param([string]$CertPath)
    Write-Step "[Step 3 of 4] Installing dependencies"
    if ($CertPath) {
        Write-Info "Using a combined certificate bundle for these installs (the standard public"
        Write-Info "certificates plus Avast's, if present) so pip's HTTPS connections work whether"
        Write-Info "or not Avast happens to be intercepting them:"
        Write-Info "  $CertPath"
    } else {
        Write-Warn "Couldn't build a certificate bundle for pip - continuing with pip's defaults."
        Write-Info "If pip reports SSL/certificate errors below, that's likely why."
    }
    Write-Info "Installing: $($RequiredPackages -join ', ')"
    if (-not (Install-PipPackagesWithRetry -Packages $RequiredPackages -CertPath $CertPath)) {
        throw "pip-failed"
    }
    Write-Ok "All dependencies installed."
}

# ---------------------------------------------------------------------------
# Step 4: finish up
# ---------------------------------------------------------------------------
function New-StartScripts {
    $ps1Path = Join-Path $Root 'start-joblander.ps1'
    $ps1Content = @'
# Launches JobLander: starts the local server from its dedicated Python
# environment, waits for it to come up (polling, not a blind sleep), then
# opens your browser. Created by install.ps1 - safe to re-run any time.

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$ServerDir = Join-Path $Root 'server'
$Url = 'http://127.0.0.1:8787/'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "JobLander hasn't been set up yet." -ForegroundColor Red
    Write-Host "Please run Install-JobLander.bat first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting JobLander..." -ForegroundColor Cyan
Write-Host "Leave this window open while you use the app - closing it stops the server." -ForegroundColor DarkGray
Write-Host ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VenvPython
$psi.Arguments = 'main.py'
$psi.WorkingDirectory = $ServerDir
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)

$maxWaitSeconds = 30
$up = $false
# Real wall-clock stopwatch, not a hand-accumulated counter - measured for
# real on the dev machine that a failed request to a closed port can itself
# take ~2.4s to time out (not the instant "connection refused" you'd get on
# a machine with no security software watching network traffic; this
# machine, like real target machines, has Avast). Tracking only the
# Start-Sleep duration would silently let the real wait run to several
# times the intended 30s cap whenever requests are slow to fail.
$sw = [System.Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt $maxWaitSeconds) {
    if ($proc.HasExited) {
        Write-Host "The server process exited unexpectedly (exit code $($proc.ExitCode)) before it came up." -ForegroundColor Red
        break
    }
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $up = $true; break }
    } catch {
        # Not up yet (connection refused, or still timing out) - keep waiting.
    }
    Start-Sleep -Milliseconds 500
}

if ($up) {
    Write-Host "JobLander is up - opening your browser..." -ForegroundColor Green
    Start-Process $Url
} elseif (-not $proc.HasExited) {
    Write-Host "The server didn't respond within $maxWaitSeconds seconds." -ForegroundColor Yellow
    Write-Host "It may still be starting - try opening $Url yourself in a moment, or check for errors above." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Server is running. Close this window (or press Ctrl+C) to stop JobLander."
Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
'@
    Set-Content -LiteralPath $ps1Path -Value $ps1Content -Encoding ascii

    $batPath = Join-Path $Root 'Start-JobLander.bat'
    $batContent = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-joblander.ps1"
pause
"@
    Set-Content -LiteralPath $batPath -Value $batContent -Encoding ascii
}

function Step-Finish {
    Write-Step "[Step 4 of 4] Finishing up"
    Write-Info "Creating Start-JobLander.bat..."
    New-StartScripts
    Write-Ok "Done."

    Write-Banner "You're all set!"
    Write-Host "Double-click Start-JobLander.bat any time to open JobLander." -ForegroundColor Green
    Write-Host "It starts the app and opens your browser automatically." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
function Invoke-Install {
    Write-Banner "JobLander Setup"
    try {
        $claude = Step-EnsureClaudeCliPresent
        Step-EnsurePythonAndVenv
        $certPath = New-CombinedCaBundle
        Step-VerifyClaudeLogin -Claude $claude -CertPath $certPath
        Step-InstallDependencies -CertPath $certPath
        Step-Finish
    } catch {
        $msg = $_.Exception.Message
        Write-Host ""
        if ($KnownStopReasons -contains $msg) {
            Write-Host "Setup stopped - see the message above for what to do next." -ForegroundColor Yellow
        } else {
            Write-Host "Setup hit an unexpected problem: $msg" -ForegroundColor Red
            Write-Host "Nothing beyond what was shown above should have changed. You can safely run Install-JobLander.bat again." -ForegroundColor Yellow
        }
        exit 1
    }
}

# Only auto-run when executed normally. Dot-sourcing this file (`. .\install.ps1`)
# loads every function above without running the installer - used for testing
# individual pieces (Find-WorkingPython, Test-AvastRunning, Test-ClaudeCliInstalled,
# Test-ClaudeLoginReal, ...) directly and safely against the real machine.
if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Install
}
