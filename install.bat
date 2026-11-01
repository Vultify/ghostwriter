@echo off
rem Sets up Ghostwriter inside this folder: its own Python, its packages, the whisper.cpp speech engine, and a Start
rem menu shortcut. Safe to run again; it skips what's already done and picks up where it left off.
rem "install.bat /quiet" skips the questions at the end (get.ps1 uses this).
rem For testing: GHOSTWRITER_WHISPER_CPP_ZIP installs whisper.cpp from a local zip instead of downloading it, and
rem GHOSTWRITER_NO_NVIDIA sets up as if this PC had no NVIDIA card.
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
set "WHISPER_CPP_VERSION=v1.9.5"
set "WHISPER_CPP_URL=https://github.com/Vultify/ghostwriter/releases/download/whisper-cpp-%WHISPER_CPP_VERSION%/whisper-cpp-%WHISPER_CPP_VERSION%-vulkan-x64.zip"

rem NVIDIA cards also get the CUDA libraries for faster-whisper; every graphics card gets whisper.cpp.
set "NVIDIA="
powershell -NoProfile -Command "if (Get-CimInstance Win32_VideoController | Where-Object Name -like '*NVIDIA*') { exit 0 } else { exit 1 }"
if not errorlevel 1 set "NVIDIA=1"
if defined GHOSTWRITER_NO_NVIDIA set "NVIDIA="

echo.
echo   Ghostwriter setup
echo   =================
if defined NVIDIA echo   Everything goes inside this folder, about 2.5 GB.
if not defined NVIDIA echo   Everything goes inside this folder, about 1 GB.
echo   If you want Ghostwriter to live somewhere else, close this window, move the folder, and run it again.
echo.

if exist "%UV%" goto have_uv
echo   [1/5] Downloading uv, the tool that installs Python and packages...
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; $zip = Join-Path $env:TEMP 'ghostwriter-uv.zip'; Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip; Expand-Archive $zip -DestinationPath '.tools' -Force; Remove-Item $zip"
if errorlevel 1 goto failed
:have_uv

if exist ".venv\Scripts\python.exe" goto have_python
echo   [2/5] Installing Python 3.11 into this folder...
"%UV%" venv .venv --python 3.11 --managed-python
if errorlevel 1 goto failed
:have_python

if not defined NVIDIA goto packages_without_nvidia
echo   [3/5] Installing Ghostwriter's packages. The first time this downloads about 2.3 GB and takes a few minutes...
"%UV%" pip install --python .venv\Scripts\python.exe -r requirements.txt -r requirements-nvidia.txt
if errorlevel 1 goto failed
goto have_packages
:packages_without_nvidia
echo   [3/5] Installing Ghostwriter's packages. The first time this downloads about 200 MB...
"%UV%" pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto failed
:have_packages

findstr /x /c:"%WHISPER_CPP_VERSION%" ".whisper-cpp\VERSION.txt" >nul 2>&1
if not errorlevel 1 goto have_whisper_cpp
echo   [4/5] Downloading whisper.cpp, the speech engine that runs on any graphics card...
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; $zip = Join-Path $env:TEMP 'ghostwriter-whisper-cpp.zip'; if ($env:GHOSTWRITER_WHISPER_CPP_ZIP) { Copy-Item -LiteralPath $env:GHOSTWRITER_WHISPER_CPP_ZIP -Destination $zip } else { Invoke-WebRequest '%WHISPER_CPP_URL%' -OutFile $zip }; if (Test-Path '.whisper-cpp') { Remove-Item '.whisper-cpp' -Recurse -Force }; Expand-Archive $zip -DestinationPath '.whisper-cpp' -Force; Remove-Item $zip"
if errorlevel 1 goto failed
:have_whisper_cpp

echo   [5/5] Adding Ghostwriter to the Start menu...
.venv\Scripts\python.exe scripts\make_shortcut.py
if errorlevel 1 goto failed

set "RESULT=0"
echo.
echo   All set! To start Ghostwriter, open the Start menu and type Ghostwriter.
if defined NVIDIA echo   The first start downloads the speech model, about 1.6 GB, one time only.
if not defined NVIDIA echo   The first start downloads the speech model, about 0.6 GB, one time only.
if defined QUIET goto done
echo.
set "START_NOW="
set /p "START_NOW=  Start Ghostwriter now? Type Y and press Enter, or just press Enter to skip: "
if /i "%START_NOW%"=="Y" start "" ".venv\Scripts\pythonw.exe" -m ghostwriter
goto done

:failed
echo.
echo   Setup ran into a problem; the message above says what went wrong.
echo   Check your internet connection and run install.bat again. It picks up where it left off.

:done
echo.
if not defined QUIET pause
endlocal & exit /b %RESULT%
