param([string]$Compiler)
$ErrorActionPreference = 'Stop'

if (-not $Compiler) {
    $Compiler = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $Compiler) {
        $Compiler = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $Compiler) { throw 'Install Inno Setup 6 or pass the path to ISCC.exe via -Compiler.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'dist\BluettiWidget\BluettiWidget.exe'))) {
    throw 'Run build.ps1 before building the installer.'
}

& $Compiler (Join-Path $PSScriptRoot 'installer\BluettiWidget.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed ($LASTEXITCODE)." }
