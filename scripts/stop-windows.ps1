# Close service windows by command line pattern
param(
    [string]$Patterns = "macro-fin,Frontend,douyin-processor"
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Searching for service windows..."

# Get all cmd processes with command line
$cmdProcesses = Get-WmiObject Win32_Process | Where-Object { $_.Name -eq "cmd.exe" }

Write-Host "Found $($cmdProcesses.Count) cmd processes, checking each one..."

$closedCount = 0

foreach ($proc in $cmdProcesses) {
    $cmdLine = $proc.CommandLine
    $procId = $proc.ProcessId

    # Check for different service patterns
    $has8094 = $cmdLine -like '*8094*'
    $has8093 = $cmdLine -like '*8093*'
    $has8070 = $cmdLine -like '*8070*'
    $hasNpmDev = $cmdLine -like '*npm run dev*'

    if ($has8094 -or $has8093 -or $has8070 -or $hasNpmDev) {
        Write-Host "MATCHED PID $procId - Closing..."

        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        if ($?) {
            Write-Host "  -> Successfully closed PID $procId"
            $closedCount++
        } else {
            Write-Host "  -> Failed to close PID $procId"
        }
    }
}

if ($closedCount -gt 0) {
    Write-Host "Closed $closedCount service window(s)"
} else {
    Write-Host "No matching service windows found"
}