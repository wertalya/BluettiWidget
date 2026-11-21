$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$widgetExecutable = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist\BluettiWidget\BluettiWidget.exe'))
$portableExecutable = [IO.Path]::GetFullPath((Join-Path $projectRoot 'portable\BluettiWidget.exe'))
if (-not ('PowerCompanionQuit' -as [type])) {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class PowerCompanionQuit { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); [DllImport("user32.dll")] public static extern bool PostThreadMessage(uint threadId, uint msg, IntPtr wParam, IntPtr lParam); }'
}
Get-Process BluettiWidget -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $widgetExecutable -or $_.Path -eq $portableExecutable } | ForEach-Object {
    $widgetOwnerId = [uint32]0
    $widgetThreadId = [PowerCompanionQuit]::GetWindowThreadProcessId($_.MainWindowHandle, [ref]$widgetOwnerId)
    if ($widgetThreadId) {
        [PowerCompanionQuit]::PostThreadMessage($widgetThreadId, 18, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    }
    if (-not $_.WaitForExit(10000)) { Stop-Process -Id $_.Id }
}
