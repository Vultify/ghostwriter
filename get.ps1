# Installs or updates Ghostwriter with one command in PowerShell:
#
#   irm https://raw.githubusercontent.com/Vultify/ghostwriter/main/get.ps1 | iex
#
# It downloads the latest release into a Ghostwriter folder in your user folder, keeps your dictionary,
# settings, and log when updating, and runs install.bat to set up Python, the packages, and the Start menu.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # downloads are far faster without the progress bar
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo = 'Vultify/ghostwriter'
    # GHOSTWRITER_HOME picks the folder (the tray's Check for updates sets it); the other two are for testing.
    $installDir = if ($env:GHOSTWRITER_HOME) { $env:GHOSTWRITER_HOME } else { Join-Path $HOME 'Ghostwriter' }
    $localZip = $env:GHOSTWRITER_ZIP
    $startWhenDone = -not $env:GHOSTWRITER_NO_START

    function Say($text) { Write-Host "  $text" }

    function Read-Version($folder) {
        $init = Join-Path $folder 'ghostwriter\__init__.py'
        if (-not (Test-Path -LiteralPath $init)) { return $null }
        $match = Select-String -LiteralPath $init -Pattern '__version__ = "(.+)"'
        if ($match) { return $match.Matches[0].Groups[1].Value }
        return $null
    }

    Write-Host ''
    Say 'Ghostwriter installer'
    Say '====================='

    if (-not (Get-CimInstance Win32_VideoController | Where-Object Name -like '*NVIDIA*')) {
        Say "Ghostwriter needs an NVIDIA graphics card to turn speech into text, and this PC doesn't seem to have one."
        Say 'Nothing was installed.'
        return
    }

    $work = Join-Path ([IO.Path]::GetTempPath()) ('ghostwriter-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        $zip = Join-Path $work 'ghostwriter.zip'
        if ($localZip) {
            Copy-Item -LiteralPath $localZip -Destination $zip
        } else {
            Say 'Finding the latest version...'
            $tag = (Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest").tag_name
            Invoke-WebRequest "https://github.com/$repo/archive/refs/tags/$tag.zip" -OutFile $zip -UseBasicParsing
        }
        $unzipped = Join-Path $work 'files'
        Expand-Archive -LiteralPath $zip -DestinationPath $unzipped
        $source = (Get-ChildItem -LiteralPath $unzipped -Directory | Select-Object -First 1).FullName
        $latest = Read-Version $source
        $installed = Read-Version $installDir

        if ($installed -eq $latest -and (Test-Path -LiteralPath (Join-Path $installDir '.venv\Scripts\pythonw.exe'))) {
            Say "Ghostwriter $latest is already installed and up to date."
            return
        }
        if ($installed) { Say "Updating Ghostwriter $installed to $latest..." } else { Say "Installing Ghostwriter $latest into $installDir..." }

        # Close Ghostwriter if it's running from this folder, so its files can be replaced.
        $running = Get-Process pythonw -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and $_.Path.StartsWith($installDir, [StringComparison]::OrdinalIgnoreCase) }
        if ($running) {
            Say 'Closing Ghostwriter for the update...'
            $running | Stop-Process -Force
            Start-Sleep -Seconds 1
        }

        # Swap in the new code. Your dictionary, settings, and log aren't in the download, so they're left alone.
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        foreach ($folder in 'ghostwriter', 'scripts', 'tests') {
            $old = Join-Path $installDir $folder
            if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
        }
        robocopy $source $installDir /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Couldn't copy the new files into $installDir" }

        # The setup tools print progress on the error stream, so judge install.bat by its exit code instead.
        $ErrorActionPreference = 'Continue'
        & (Join-Path $installDir 'install.bat') /quiet
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -ne 0) {
            Say 'Setup did not finish. Run the same command again and it picks up where it left off.'
            return
        }

        Write-Host ''
        Say "Done! Ghostwriter $latest is installed in $installDir"
        if ($startWhenDone) {
            Start-Process -FilePath (Join-Path $installDir '.venv\Scripts\pythonw.exe') -ArgumentList '-m', 'ghostwriter' -WorkingDirectory $installDir
            Say 'It is starting now; look for the ghost by the clock.'
        }
        Say 'Hold Right Alt and talk (Right Ctrl on keyboards with an AltGr key).'
        Say 'To update later, right click the ghost and choose Check for updates.'
    } catch {
        Say "Something went wrong: $($_.Exception.Message)"
        Say 'Check your internet connection and run the same command again.'
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
