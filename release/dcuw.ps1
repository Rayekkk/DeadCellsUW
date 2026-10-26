# Dead Cells Ultrawide installer. Used by Install.bat / Uninstall.bat.
# Replaces libhl.dll with the proxy (libhl_uw.dll) and keeps the original as libhl_orig.dll.
param([ValidateSet('install', 'uninstall')][string]$Action = 'install', [string]$GameDir)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Game {
    if ($GameDir) { return $GameDir }
    if (Test-Path (Join-Path $here 'deadcells.exe')) { return $here }
    $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
    if ($steam) {
        $libs = @($steam)
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs += Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
        }
        foreach ($lib in $libs) {
            $dir = Join-Path $lib 'steamapps\common\Dead Cells'
            if (Test-Path (Join-Path $dir 'deadcells.exe')) { return $dir }
        }
    }
    throw 'Dead Cells not found. Run: Install.bat "D:\path\to\Dead Cells"'
}

# Our proxy forwards to libhl_orig.dll, so that name is in its export table; the real libhl never contains it.
function Test-Proxy($path) { [IO.File]::ReadAllText($path, [Text.Encoding]::ASCII).Contains('libhl_orig.') }

try {
    $game = Find-Game
    $libhl = Join-Path $game 'libhl.dll'
    $orig = Join-Path $game 'libhl_orig.dll'
    if (-not (Test-Path $libhl)) { throw "libhl.dll not found in $game" }
    if (Get-Process deadcells, deadcells_gl -ErrorAction SilentlyContinue) { throw 'Close Dead Cells first.' }

    if ($Action -eq 'install') {
        if (-not (Test-Proxy $libhl)) {
            Copy-Item $libhl $orig -Force  # fresh install, or Steam restored the original after an update/verify
        } elseif (-not (Test-Path $orig)) {
            throw 'libhl_orig.dll is missing. Verify the game files in Steam, then run Install.bat again.'
        }
        Copy-Item (Join-Path $here 'libhl_uw.dll') $libhl -Force
        Remove-Item (Join-Path $game 'dc_ultrawide.cfg') -ErrorAction SilentlyContinue  # left by older versions
        Write-Host "Installed in: $game" -ForegroundColor Green
    } else {
        if ((Test-Proxy $libhl) -and (Test-Path $orig)) {
            Move-Item $orig $libhl -Force
            Write-Host "Restored the original libhl.dll in: $game" -ForegroundColor Green
        } else {
            Write-Host 'The mod is not installed.'
        }
        Remove-Item (Join-Path $game 'dc_ultrawide.log'), (Join-Path $game 'dc_ultrawide.cfg') -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
