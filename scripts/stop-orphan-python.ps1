# Stop orphaned Python processes with local loopback connections
# Only processes belonging to this project will be cleaned

$ErrorActionPreference = "SilentlyContinue"

# Get project root path (resolve to absolute path)
$projectRoot = Resolve-Path "$PSScriptRoot\.."
Write-Host "Project root: $projectRoot"

$pythonProcs = Get-Process -Name python -ErrorAction SilentlyContinue
$orphanCount = 0
$checkedCount = 0

if ($pythonProcs) {
    Write-Host "Found $($pythonProcs.Count) Python processes"

    foreach ($proc in $pythonProcs) {
        # Get process command line to check if it belongs to our project
        $processInfo = Get-WmiObject Win32_Process | Where-Object { $_.ProcessId -eq $proc.Id }
        if (-not $processInfo) {
            continue
        }

        $cmdLine = $processInfo.CommandLine

        # Only process Python processes that belong to our project
        # Check by project path in command line
        if ($cmdLine -notlike "*$projectRoot*") {
            continue
        }

        $checkedCount++

        # Check network connections
        $conns = Get-NetTCPConnection -OwningProcess $proc.Id -ErrorAction SilentlyContinue
        if (-not $conns) {
            continue
        }

        # Check if process has local loopback connections
        $localLoopback = $conns | Where-Object { $_.RemoteAddress -eq "127.0.0.1" -and $_.State -eq "Established" }

        # Check if process is listening on a port (not an orphan)
        $listening = $conns | Where-Object { $_.State -eq "Listen" }

        # Only kill if has local loopback but NOT listening (true orphan)
        if ($localLoopback -and -not $listening) {
            Write-Host "Killing orphaned Python PID: $($proc.Id)"
            Stop-Process -Id $proc.Id -Force
            $orphanCount++
        }
    }

    if ($orphanCount -gt 0) {
        Write-Host "Cleaned $orphanCount orphaned Python processes (checked $checkedCount project process)"
    } else {
        Write-Host "No orphaned Python processes found in project (checked $checkedCount project process)"
    }
} else {
    Write-Host "No Python processes found"
}
