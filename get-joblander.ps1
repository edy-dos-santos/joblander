<#
    JobLander bootstrap script - downloads the app itself, then hands off to
    the app's own installer.

    This is the file Get-JobLander.bat downloads and runs. It is meant to be
    fetched fresh every time (Get-JobLander.bat pulls it from GitHub's raw
    URL right before running it), so - unlike install.ps1 - it must not
    assume anything about this machine except that Windows PowerShell and an
    internet connection exist. It never assumes install.ps1, server\, or any
    other project file is sitting next to it: that is the entire point of
    this script's existence.

    What this script does, in order (see runs\36-implement-bootstrap-installer.md
    for the full writeup, including what was live-tested):

      1. Explain what is about to happen, in plain language, before doing
         anything.
      2. Work out where to put the app (Desktop\JobLander by default) and,
         if something is already there, ask what to do instead of silently
         overwriting it - especially if it looks like a previous install
         with real saved profiles in it.
      3. Download the app as a .zip straight from GitHub (no git required)
         and unzip it into that location.
      4. Hand off to the app's own install.ps1 (via Install-JobLander.bat's
         exact mechanism, just invoked directly) so the rest of setup -
         Claude Code check, Python, the app's dependencies, Avast handling -
         runs completely unchanged. This script does not re-implement any of
         that.
      5. Delete the downloaded .zip and any scratch files; keep only the
         extracted app.

    Like install.ps1, every function here can be dot-sourced (`. .\get-joblander.ps1`)
    without auto-running anything, for testing individual pieces safely.
#>

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
$RepoOwner = 'edy-dos-santos'
$RepoName = 'joblander'
$Branch = 'main'
$ZipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
$RepoPageUrl = "https://github.com/$RepoOwner/$RepoName"

$KnownStopReasons = @('download-failed', 'extract-failed', 'copy-failed', 'installer-missing')

# ---------------------------------------------------------------------------
# Small console-output helpers - deliberately the same shape as install.ps1's
# (Write-Banner/Step/Info/Ok/Warn/Err) for a consistent look. Duplicated here
# rather than dot-sourced from install.ps1, because install.ps1 does not
# exist on disk yet when this script runs - that is exactly the problem this
# script exists to solve.
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
# Where to put the app, and what to do if something is already there.
# ---------------------------------------------------------------------------
function Get-DefaultInstallDir {
    # [Environment]::GetFolderPath('Desktop') rather than a hardcoded
    # "$env:USERPROFILE\Desktop" - correctly resolves a redirected/localized
    # Desktop (confirmed live on this machine: on a non-English Windows
    # locale this resolves to that language's own Desktop folder name, not
    # literally "Desktop" - a plain hardcoded path would silently miss it).
    $desktop = [Environment]::GetFolderPath('Desktop')
    return (Join-Path $desktop 'JobLander')
}

function Get-NextAvailableDir {
    param([string]$BaseDir)
    $parent = Split-Path -Parent $BaseDir
    $name = Split-Path -Leaf $BaseDir
    $i = 2
    while ($true) {
        $candidate = Join-Path $parent "$name ($i)"
        if (-not (Test-Path -LiteralPath $candidate)) { return $candidate }
        $i++
    }
}

# Looks for signs that $Dir is a previous real JobLander install, and
# specifically whether it has actual saved profile data in it - that is the
# case this script must never silently clobber.
function Test-LooksLikePreviousInstall {
    param([string]$Dir)
    $hasProfileData = $false
    $instancesDir = Join-Path $Dir 'instances'
    if (Test-Path -LiteralPath $instancesDir) {
        $sub = Get-ChildItem -LiteralPath $instancesDir -Directory -ErrorAction SilentlyContinue
        if ($sub -and @($sub).Count -gt 0) { $hasProfileData = $true }
    }
    $hasAppFiles = (Test-Path -LiteralPath (Join-Path $Dir 'server\main.py')) -or `
                   (Test-Path -LiteralPath (Join-Path $Dir 'install.ps1'))
    return [PSCustomObject]@{
        HasProfileData     = $hasProfileData
        LooksLikeJobLander = ($hasAppFiles -or $hasProfileData)
    }
}

# Decides the final install path and mode ('Fresh' or 'Update'), asking the
# user when the default location already has something in it. Returns
# Mode='Cancel' (Path=$null) if the user explicitly declines.
function Resolve-InstallTarget {
    $target = Get-DefaultInstallDir

    if (-not (Test-Path -LiteralPath $target)) {
        return [PSCustomObject]@{ Path = $target; Mode = 'Fresh' }
    }

    $items = Get-ChildItem -LiteralPath $target -Force -ErrorAction SilentlyContinue
    if (-not $items -or @($items).Count -eq 0) {
        # Exists but empty - nothing to protect, safe to use directly.
        return [PSCustomObject]@{ Path = $target; Mode = 'Fresh' }
    }

    $info = Test-LooksLikePreviousInstall -Dir $target

    if ($info.HasProfileData) {
        Write-Warn "A JobLander folder already exists at:"
        Write-Warn "  $target"
        Write-Info "It looks like it has your existing profile data in it (a saved 'instances' folder)."
        Write-Info "Whatever you choose below, your existing profiles will NOT be deleted or overwritten."
        Write-Host ""
        Write-Host "  [U] Update the app files here, keep my existing profiles/data  (recommended)"
        Write-Host "  [N] Install fresh into a new, separate folder instead - leave this one exactly as it is"
        Write-Host "  [C] Cancel - do nothing"
        while ($true) {
            $answer = Read-Host "Choice [U/n/c]"
            $a = $answer.Trim().ToLower()
            if ($a -eq '' -or $a -eq 'u') { return [PSCustomObject]@{ Path = $target; Mode = 'Update' } }
            if ($a -eq 'n') { return [PSCustomObject]@{ Path = (Get-NextAvailableDir $target); Mode = 'Fresh' } }
            if ($a -eq 'c') { return [PSCustomObject]@{ Path = $null; Mode = 'Cancel' } }
            Write-Warn "Please type U, N, or C."
        }
    } else {
        Write-Warn "A folder already exists at:"
        Write-Warn "  $target"
        Write-Info "It doesn't look like it has any saved JobLander profiles in it, but it isn't empty either."
        Write-Host ""
        Write-Host "  [O] Use this folder anyway - JobLander's files will be added/overwritten here  (recommended if this is an old or incomplete JobLander download)"
        Write-Host "  [N] Install fresh into a new, separate folder instead"
        Write-Host "  [C] Cancel - do nothing"
        while ($true) {
            $answer = Read-Host "Choice [O/n/c]"
            $a = $answer.Trim().ToLower()
            if ($a -eq '' -or $a -eq 'o') { return [PSCustomObject]@{ Path = $target; Mode = 'Update' } }
            if ($a -eq 'n') { return [PSCustomObject]@{ Path = (Get-NextAvailableDir $target); Mode = 'Fresh' } }
            if ($a -eq 'c') { return [PSCustomObject]@{ Path = $null; Mode = 'Cancel' } }
            Write-Warn "Please type O, N, or C."
        }
    }
}

# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------
function Get-JobLanderZip {
    param([string]$DestZipPath)
    Write-Info "Downloading JobLander from GitHub:"
    Write-Info "  $ZipUrl"
    $oldProgressPref = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        Invoke-WebRequest -Uri $ZipUrl -OutFile $DestZipPath -UseBasicParsing
    } catch {
        Write-Err "Could not download JobLander from GitHub."
        Write-Err "  $($_.Exception.Message)"
        Write-Info "Check your internet connection and try again. If you're on a work/school network, a firewall may be blocking github.com."
        throw "download-failed"
    } finally {
        $ProgressPreference = $oldProgressPref
    }
    if (-not (Test-Path -LiteralPath $DestZipPath)) { throw "download-failed" }
    Write-Ok "Download complete."
}

# GitHub's branch zips always nest everything one level deep inside a single
# top-level folder (e.g. joblander-main\) - this finds that folder rather
# than assuming its exact name, so a future branch rename can't break it.
function Expand-JobLanderZip {
    param([string]$ZipPath, [string]$ExtractDir)
    Write-Info "Extracting..."
    if (Test-Path -LiteralPath $ExtractDir) {
        Remove-Item -LiteralPath $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractDir -Force
    $nested = @(Get-ChildItem -LiteralPath $ExtractDir -Directory)
    if ($nested.Count -ne 1) {
        Write-Err "The downloaded zip didn't look the way it should (expected exactly one top-level folder, found $($nested.Count))."
        throw "extract-failed"
    }
    return $nested[0].FullName
}

# Copies the extracted app's files into the final target folder. Uses
# robocopy (built into every Windows install, no separate download needed)
# rather than Copy-Item -Recurse, deliberately: robocopy merges a source
# folder's *contents* into an existing destination folder correctly, where
# Copy-Item -Recurse's behaviour when the destination subfolder already
# exists is a known source of confusion/nesting bugs. Without /MIR or
# /PURGE, robocopy only ever adds or overwrites files that exist in the
# freshly-downloaded app - it never deletes anything already in the target
# that isn't part of the app's own file list. In particular, a previous
# install's `instances\` (real saved profiles) and `.venv\` (the Python
# environment) are never even referenced by the source zip, so they are
# never touched, added, or removed by this step - confirmed live, see the
# test report.
function Copy-JobLanderFiles {
    param([string]$SourceDir, [string]$TargetDir)
    if (-not (Test-Path -LiteralPath $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }
    Write-Info "Copying app files into:"
    Write-Info "  $TargetDir"
    # /E = copy subfolders (incl. empty), /NFL /NDL /NJH /NJS /NC /NS = quiet
    # per-file noise but keep the summary. Piped through Out-Host for the
    # same reason every external-process call in install.ps1 is: without it,
    # robocopy's own console output would silently become part of this
    # function's return value instead of just going to the screen.
    & robocopy $SourceDir $TargetDir /E /NFL /NDL /NJH /NJS /NC /NS | Out-Host
    $rc = $LASTEXITCODE
    # Robocopy's exit codes are a bitmask, not a plain 0=success convention:
    # 0-7 all mean some flavour of success (0 = nothing to do, 1 = files
    # copied, 2 = extra files present, etc.); 8 and above mean a real
    # failure. See Microsoft's robocopy exit-code table.
    if ($rc -ge 8) {
        Write-Err "Copying the app's files failed (robocopy exit code $rc)."
        throw "copy-failed"
    }
}

# ---------------------------------------------------------------------------
# Hand off to the app's own, already-tested installer. Deliberately invokes
# install.ps1 directly (the same file Install-JobLander.bat calls) rather
# than re-implementing any of its logic - Claude Code check, Python/venv,
# dependencies, Avast handling all stay exactly as they are.
# ---------------------------------------------------------------------------
function Invoke-RealInstaller {
    param([string]$TargetDir)
    $installPs1 = Join-Path $TargetDir 'install.ps1'
    if (-not (Test-Path -LiteralPath $installPs1)) {
        Write-Err "Could not find install.ps1 inside the downloaded app at:"
        Write-Err "  $TargetDir"
        Write-Info "The download may be incomplete, or the app's layout changed. Try running Get-JobLander.bat again, or download the app manually from $RepoPageUrl."
        throw "installer-missing"
    }
    Write-Step "[Step 3 of 3] Handing off to the JobLander installer"
    Write-Info "Running install.ps1 - this checks Claude Code and Python, and installs the app's own dependencies."
    Write-Info "(From here on this is the exact same installer JobLander has always used - nothing new is happening.)"
    Write-Host ""
    Push-Location $TargetDir
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $installPs1 | Out-Host
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
function Invoke-Bootstrap {
    Write-Banner "JobLander Setup"
    Write-Host "This is going to:"
    Write-Host "  1. Download JobLander from GitHub ($RepoPageUrl) as a .zip file"
    Write-Host "  2. Unzip it onto this computer, into a folder you'll see below"
    Write-Host "  3. Run JobLander's own installer, which checks for Claude Code and Python"
    Write-Host "     and sets up everything else JobLander needs"
    Write-Host ""
    Write-Host "Nothing outside that one folder is touched, other than the small, clearly-"
    Write-Host "explained system checks the installer itself already does in step 3 (like"
    Write-Host "checking whether Python is installed)."
    Write-Host ""
    $null = Read-Host "Press Enter to continue (or close this window to cancel)"

    try {
        $resolved = Resolve-InstallTarget
    } catch {
        Write-Err "Couldn't figure out where to install JobLander: $($_.Exception.Message)"
        exit 1
    }
    if ($resolved.Mode -eq 'Cancel') {
        Write-Warn "Cancelled - nothing was downloaded and nothing changed."
        return
    }
    $targetDir = $resolved.Path

    Write-Step "[Step 1 of 3] Where JobLander will go"
    Write-Info "$targetDir"

    Write-Step "[Step 2 of 3] Downloading and unpacking JobLander"
    $stageRoot = Join-Path $env:TEMP "joblander-bootstrap-$PID"
    $zipPath = Join-Path $stageRoot 'joblander.zip'
    $extractDir = Join-Path $stageRoot 'extract'
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    try {
        Get-JobLanderZip -DestZipPath $zipPath
        $extractedAppDir = Expand-JobLanderZip -ZipPath $zipPath -ExtractDir $extractDir
        Copy-JobLanderFiles -SourceDir $extractedAppDir -TargetDir $targetDir
        Write-Ok "JobLander's files are ready."
    } finally {
        # Clean up the scratch download/extract area regardless of outcome -
        # only the extracted app inside $targetDir is meant to survive.
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    $exit = Invoke-RealInstaller -TargetDir $targetDir
    Write-Host ""
    if ($exit -eq 0) {
        Write-Banner "All done!"
        Write-Host "JobLander is installed at:" -ForegroundColor Green
        Write-Host "  $targetDir" -ForegroundColor Green
        Write-Host "From now on, just double-click Start-JobLander.bat inside that folder to open it." -ForegroundColor Green
    } else {
        Write-Warn "The JobLander installer reported a problem (exit code $exit) - see the messages above for what to do next."
        Write-Info "Your JobLander files are already in place at:"
        Write-Info "  $targetDir"
        Write-Info "so once it's fixed you can just re-run Install-JobLander.bat inside that folder - no need to download again."
    }
}

# Only auto-run when executed normally. Dot-sourcing this file
# (`. .\get-joblander.ps1`) loads every function above without running
# anything - used to test individual pieces (Resolve-InstallTarget,
# Expand-JobLanderZip, Copy-JobLanderFiles, ...) directly and safely.
if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-Bootstrap
    } catch {
        $msg = $_.Exception.Message
        Write-Host ""
        if ($KnownStopReasons -contains $msg) {
            Write-Host "Setup stopped - see the message above for what to do next." -ForegroundColor Yellow
        } else {
            Write-Host "Setup hit an unexpected problem: $msg" -ForegroundColor Red
        }
        exit 1
    }
}
