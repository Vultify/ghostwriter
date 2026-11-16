# Writes the lock files install.bat installs from: the exact versions, with checksums, of every package in
# requirements.txt (and requirements-nvidia.txt for NVIDIA PCs). The versions come from this folder's .venv, so a
# lock only ever holds what the tests just passed with. Run it before a release, after updating the venv on purpose:
#
#   powershell -ExecutionPolicy Bypass -File scripts\lock_requirements.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Invoke-Uv {
    $uv = Join-Path $root '.tools\uv.exe'
    if (Test-Path -LiteralPath $uv) { & $uv @args } else { & python -m uv @args }
    if ($LASTEXITCODE -ne 0) { throw "uv $($args[0]) $($args[1]) failed" }
}

$tested = Join-Path ([IO.Path]::GetTempPath()) 'ghostwriter-tested-versions.txt'
try {
    Invoke-Uv pip freeze --python .venv\Scripts\python.exe | Set-Content -LiteralPath $tested -Encoding utf8
    $options = @('--python-version', '3.11', '--python-platform', 'x86_64-pc-windows-msvc', '--generate-hashes',
                 '--constraint', $tested, '--custom-compile-command', 'scripts\lock_requirements.ps1', '--no-annotate',
                 '--quiet')  # no notes on where each package came from, since that names a temp file on this PC
    Invoke-Uv pip compile requirements.txt --output-file requirements-windows.lock @options
    Invoke-Uv pip compile requirements.txt requirements-nvidia.txt --output-file requirements-windows-nvidia.lock @options
    Write-Host 'Wrote requirements-windows.lock and requirements-windows-nvidia.lock'
} finally {
    Remove-Item -LiteralPath $tested -ErrorAction SilentlyContinue
}
