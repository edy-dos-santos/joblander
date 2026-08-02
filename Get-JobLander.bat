@echo off
setlocal
title JobLander Setup

echo.
echo ============================================
echo  JobLander Setup
echo ============================================
echo.
echo Getting ready - downloading the JobLander setup script from GitHub...
echo.

set "JL_STAGE=%TEMP%\joblander-bootstrap-%RANDOM%"
mkdir "%JL_STAGE%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/edy-dos-santos/joblander/main/get-joblander.ps1' -OutFile '%JL_STAGE%\get-joblander.ps1' -UseBasicParsing -ErrorAction Stop } catch { Write-Host ''; Write-Host 'Could not download the JobLander setup script.' -ForegroundColor Red; Write-Host $_.Exception.Message -ForegroundColor Red; Write-Host ''; Write-Host 'Check your internet connection and try again.' -ForegroundColor Yellow; exit 1 }"

if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%JL_STAGE%\get-joblander.ps1"

rmdir /s /q "%JL_STAGE%" >nul 2>&1

echo.
pause
