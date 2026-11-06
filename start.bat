@echo off
rem ACE-Step 1.5 one-click launcher (Windows)
rem Starts Gradio UI + REST API, waits for health check, opens the browser.
rem Safe to run repeatedly: already-running services are reused.
setlocal EnableExtensions
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "ENTRY=%ROOT%music-gen\scripts\start_local.ps1"

if not exist "%ENTRY%" (
  echo [ERROR] Missing script: %ENTRY%
  echo Please keep start.bat at the same level as the music-gen folder.
  pause
  exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] powershell.exe not found on this system.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ENTRY%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  pause
)

endlocal & exit /b %RC%
