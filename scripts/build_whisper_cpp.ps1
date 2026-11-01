# Builds whisper.cpp with Vulkan: the speech engine for PCs whose graphics card isn't NVIDIA (AMD, Intel, or built in).
#
# Only the PC that builds it needs the tools: CMake, the Visual Studio C++ build tools, and the Vulkan SDK.
# People who install Ghostwriter just download the finished files.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_whisper_cpp.ps1
#
# The source goes in .tools\, and the finished programs land in .whisper-cpp\. The zip it makes in .tools\ is what
# install.bat downloads: upload it to the GitHub prerelease named whisper-cpp-<version>.

param([string]$Version = 'v1.9.5')

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$source = Join-Path $project ".tools\whisper.cpp-$Version"
$build = Join-Path $source 'build'
$output = Join-Path $project '.whisper-cpp'

function Check($step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit code $LASTEXITCODE)" }
}

if (-not (Test-Path -LiteralPath $source)) {
    git clone --quiet --depth 1 --branch $Version https://github.com/ggml-org/whisper.cpp $source
    Check 'Downloading whisper.cpp'
}

# GGML_NATIVE off keeps the build from using instructions only this PC's processor has, so it runs on other PCs too.
cmake -S $source -B $build -DGGML_VULKAN=ON -DGGML_NATIVE=OFF -DBUILD_SHARED_LIBS=OFF `
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF
Check 'Setting up the build'
cmake --build $build --config Release --target whisper-server whisper-cli --parallel
Check 'Building'

New-Item -ItemType Directory -Force -Path $output | Out-Null
Copy-Item -Path (Join-Path $build 'bin\Release\whisper-server.exe'), (Join-Path $build 'bin\Release\whisper-cli.exe') -Destination $output
Copy-Item -LiteralPath (Join-Path $source 'LICENSE') -Destination (Join-Path $output 'LICENSE.txt')
Set-Content -LiteralPath (Join-Path $output 'VERSION.txt') -Value $Version -Encoding ascii
Write-Host "Built whisper.cpp $Version with Vulkan into $output"

# Ghostwriter only uses the server, so that's all that goes in the download.
$zip = Join-Path $project ".tools\whisper-cpp-$Version-vulkan-x64.zip"
Compress-Archive -Force -DestinationPath $zip -Path (Join-Path $output 'whisper-server.exe'),
    (Join-Path $output 'LICENSE.txt'), (Join-Path $output 'VERSION.txt')
Write-Host "Release download: $zip"
