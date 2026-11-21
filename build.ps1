param([string]$Python = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\stop_widget.ps1
& $Python check_widget.py
if ($LASTEXITCODE -ne 0) { throw 'Перевірки не пройшли' }
$settingsFile = Join-Path $PSScriptRoot 'dist\BluettiWidget\settings.ini'
$settingsBytes = if (Test-Path -LiteralPath $settingsFile) { [IO.File]::ReadAllBytes($settingsFile) } else { $null }
& $Python -m PyInstaller --noconfirm --windowed --name BluettiWidget --icon assets/bluetti-widget.ico --add-data assets:assets --additional-hooks-dir hooks --exclude-module PySide6.QtNetwork --collect-submodules bluetti_bt_lib --collect-submodules winrt --copy-metadata bluetti-bt-lib --copy-metadata bleak widget.py
if ($LASTEXITCODE -ne 0) { throw 'Збірка не завершилася' }
# Qt on this Windows version uses the system ICU API. A different ICU DLL
# found on PATH has incompatible exports and must not shadow the Windows DLL.
# The companion ICU data belongs to that excluded DLL. Software OpenGL is
# unused: the application draws only raster QWidget/QPainter surfaces.
foreach ($unusedRelative in @('icuuc.dll', 'icudt78.dll', 'PySide6\opengl32sw.dll')) {
    $unusedTarget = Join-Path $PSScriptRoot ('dist\BluettiWidget\_internal\' + $unusedRelative)
    if (Test-Path -LiteralPath $unusedTarget) { Remove-Item -LiteralPath $unusedTarget }
}
if ($null -ne $settingsBytes) { [IO.File]::WriteAllBytes($settingsFile, [byte[]]$settingsBytes) }
Copy-Item -LiteralPath README.md,LICENSE,THIRD_PARTY.md -Destination dist\BluettiWidget -Force
$sourceTarget = Join-Path $PSScriptRoot 'dist\BluettiWidget\source'
New-Item -ItemType Directory -Path $sourceTarget -Force | Out-Null
Copy-Item -LiteralPath widget.py,views.py,feedback.py,test_feedback.py,updates.py,test_updates.py,powerlink.py,models.py,test_models.py,runtime_estimate.py,requirements.txt,build.ps1,build_portable.py,stop_widget.ps1,check_widget.py,diagnose.py,stream_probe.py,live_checks.py,qa_render.py,README.md,README.uk.md,settings.example.ini,CONTRIBUTING.md,LICENSE,THIRD_PARTY.md -Destination $sourceTarget -Force
Copy-Item -LiteralPath assets,docs -Destination $sourceTarget -Recurse -Force
Copy-Item -LiteralPath hooks -Destination $sourceTarget -Recurse -Force
