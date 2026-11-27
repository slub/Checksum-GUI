[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Iscc = "",
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "dist")
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
if ($env:OS -ne "Windows_NT") { throw "Run this script on Windows." }

if (-not $Iscc) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $Iscc = $command.Source }
    else {
        foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, "$env:LOCALAPPDATA\Programs")) {
            if ($base) {
                $candidate = Join-Path $base "Inno Setup 6\ISCC.exe"
                if (Test-Path $candidate) { $Iscc = $candidate; break }
            }
        }
    }
}
if (-not $Iscc) { throw "Install Inno Setup 6.3 or newer, or supply -Iscc with the path to ISCC.exe." }

& $Python -c "import sys, struct, PyQt6, PyInstaller; assert sys.version_info >= (3, 10); assert struct.calcsize('P') == 8 and __import__('platform').machine().lower() in ('amd64', 'x86_64'), 'Use x64 Python'"
if ($LASTEXITCODE -ne 0) { throw "Use x64 Python 3.10+ with requirements.txt and PyInstaller installed." }

$version = & $Python (Join-Path $PSScriptRoot "version.py")
if ($LASTEXITCODE -ne 0) { throw "Cannot read application version." }

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$build = Join-Path $PSScriptRoot "build\windows"
Push-Location $repo
try {
    & $Python -m PyInstaller --noconfirm --clean --workpath "$build\work" --distpath "$build\dist" (Join-Path $repo "chksmg.windows.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    & $Iscc "/DAppVersion=$version" "/DAppExe=$build\dist\chksmg.exe" "/O$OutputDirectory" (Join-Path $PSScriptRoot "chksmg.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
} finally {
    Pop-Location
}
Write-Host "Built $OutputDirectory\chksmg-setup.exe"
