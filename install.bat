@echo off
rem Sets up Ghostwriter inside this folder: its own Python, its packages, and a Start menu shortcut.
rem Safe to run again; it skips what's already done and picks up where it left off.
rem "install.bat /quiet" skips the questions at the end (get.ps1 uses this).
setlocal
title Ghostwriter setup
cd /d "%~dp0"

set "QUIET="
if /i "%~1"=="/quiet" set "QUIET=1"
set "RESULT=1"
set "UV_VERSION=0.13.5"
set "UV=%~dp0.tools\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%~dp0.python"
set "UV_NO_CACHE=1"

echo.
echo   Ghostwriter setup
echo   =================
echo   Everything goes inside this folder, about 2.5 GB. If you want Ghostwriter
echo   to live somewhere else, close this window, move the folder, and run it again.
echo.

powershell -NoProfile -Command "if (Get-CimInstance Win32_VideoController | Where-Object Name -like '*NVIDIA*') { exit 0 } else { exit 1 }"
if errorlevel 1 goto no_nvidia

if exist "%UV%" goto have_uv
echo   [1/4] Downloading uv, the tool that installs Python and packages...
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; $zip = Join-Path $env:TEMP 'ghostwriter-uv.zip'; Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip; Expand-Archive $zip -DestinationPath '.tools' -Force; Remove-Item $zip"
if errorlevel 1 goto failed
:have_uv

if exist ".venv\Scripts\python.exe" goto have_python
echo   [2/4] Installing Python 3.11 into this folder...
"%UV%" venv .venv --python 3.11 --managed-python
if errorlevel 1 goto failed
:have_python

echo   [3/4] Installing Ghostwriter's packages. The first time this downloads about 2.3 GB and takes a few minutes...
"%UV%" pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto failed

echo   [4/4] Adding Ghostwriter to the Start menu...
.venv\Scripts\python.exe scripts\make_shortcut.py
if errorlevel 1 goto failed

set "RESULT=0"
echo.
echo   All set! To start Ghostwriter, open the Start menu and type Ghostwriter.
echo   The first start downloads the speech model, about 1.6 GB, one time only.
if defined QUIET goto done
echo.
set "START_NOW="
set /p "START_NOW=  Start Ghostwriter now? Type Y and press Enter, or just press Enter to skip: "
if /i "%START_NOW%"=="Y" start "" ".venv\Scripts\pythonw.exe" -m ghostwriter
goto done

:no_nvidia
echo   Ghostwriter needs an NVIDIA graphics card to turn speech into text,
echo   and this PC doesn't seem to have one. Nothing was installed.
goto done

:failed
echo.
echo   Setup ran into a problem; the message above says what went wrong.
echo   Check your internet connection and run install.bat again. It picks up where it left off.

:done
echo.
if not defined QUIET pause
endlocal & exit /b %RESULT%
