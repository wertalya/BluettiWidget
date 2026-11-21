param([string]$Compiler)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $Compiler) {
    $Compiler = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $Compiler) {
        $Compiler = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $Compiler) { throw 'Установіть Inno Setup 6 або вкажіть шлях до ISCC.exe параметром -Compiler.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'dist\BluettiWidget\BluettiWidget.exe'))) {
    throw 'Перед створенням інсталятора запустіть scripts\build.ps1.'
}

& $Compiler (Join-Path $projectRoot 'installer\BluettiWidget.iss')
if ($LASTEXITCODE -ne 0) { throw "Помилка збірки Inno Setup ($LASTEXITCODE)." }
