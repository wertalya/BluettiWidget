param([string]$Python)
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $projectRoot
& .\scripts\stop_widget.ps1
& $Python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'Перевірки не пройшли' }
$settingsFile = Join-Path $projectRoot 'dist\BluettiWidget\settings.ini'
$settingsBytes = if (Test-Path -LiteralPath $settingsFile) { [IO.File]::ReadAllBytes($settingsFile) } else { $null }
& $Python -m PyInstaller --noconfirm --windowed --name BluettiWidget --icon assets/bluetti-widget.ico --add-data assets:assets --additional-hooks-dir installer/hooks --exclude-module PySide6.QtNetwork --collect-submodules bluetti_bt_lib --collect-submodules winrt --copy-metadata bluetti-bt-lib --copy-metadata bleak run.py
if ($LASTEXITCODE -ne 0) { throw 'Збірка не завершилася' }
# Qt on this Windows version uses the system ICU API. A different ICU DLL
# found on PATH has incompatible exports and must not shadow the Windows DLL.
# The companion ICU data belongs to that excluded DLL. Software OpenGL is
# unused: the application draws only raster QWidget/QPainter surfaces.
foreach ($unusedRelative in @('icuuc.dll', 'icudt78.dll', 'PySide6\opengl32sw.dll')) {
    $unusedTarget = Join-Path $projectRoot ('dist\BluettiWidget\_internal\' + $unusedRelative)
    if (Test-Path -LiteralPath $unusedTarget) { Remove-Item -LiteralPath $unusedTarget }
}
if ($null -ne $settingsBytes) { [IO.File]::WriteAllBytes($settingsFile, [byte[]]$settingsBytes) }
Copy-Item -LiteralPath README.md,LICENSE -Destination dist\BluettiWidget -Force
Copy-Item -LiteralPath docs,examples -Destination dist\BluettiWidget -Recurse -Force
$sourceTarget = Join-Path $projectRoot 'dist\BluettiWidget\source'
New-Item -ItemType Directory -Path $sourceTarget -Force | Out-Null
Copy-Item -LiteralPath run.py,requirements.txt,README.md,LICENSE -Destination $sourceTarget -Force
Copy-Item -LiteralPath app,scripts,tests,assets,docs,examples,installer -Destination $sourceTarget -Recurse -Force
