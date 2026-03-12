# Close service windows by port and command line patterns
# Parameters: comma-separated ports (e.g. "8094,8093,8070") and command patterns (e.g. "npm run dev,pnpm run dev")
param(
    [string]$Ports = "",
    [string]$Commands = ""
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Searching for service windows..."

# Parse ports and commands into arrays
$portArray = if ($Ports) { $Ports -split ',' | ForEach-Object { $_.Trim() } } else { @() }
$cmdPatternArray = if ($Commands) { $Commands -split ',' | ForEach-Object { $_.Trim() } } else { @() }

if ($portArray.Count -gt 0) {
    Write-Host "Ports to match: $($portArray -join ', ')"
}
if ($cmdPatternArray.Count -gt 0) {
    Write-Host "Command patterns: $($cmdPatternArray -join ', ')"
}

# Get all cmd processes with command line
$cmdProcesses = Get-WmiObject Win32_Process | Where-Object { $_.Name -eq "cmd.exe" }

Write-Host "Found $($cmdProcesses.Count) cmd processes, checking each one..."

$closedCount = 0

foreach ($proc in $cmdProcesses) {
    $cmdLine = $proc.CommandLine
    $procId = $proc.ProcessId

    $matched = $false

    # Check for port matches
    foreach ($port in $portArray) {
        if ($cmdLine -like "*$port*") {
            $matched = $true
            Write-Host "MATCHED PID $procId - Port '$port' found"
            break
        }
    }

    # Check for command pattern matches
    if (-not $matched) {
        foreach ($pattern in $cmdPatternArray) {
            if ($cmdLine -like "*$pattern*") {
                $matched = $true
                Write-Host "MATCHED PID $procId - Command pattern '$pattern' found"
                break
            }
        }
    }

    if ($matched) {
        Write-Host "  -> Closing PID $procId..."
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