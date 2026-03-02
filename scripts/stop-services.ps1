# Stop Macro Dev Services
Write-Host ""
Write-Host "========================================"
Write-Host "  Stopping Dev Environment"
Write-Host "========================================"
Write-Host ""

Write-Host "Stopping services..."

# Find cmd processes and close them with their child processes
$cmdProcesses = Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' }

foreach ($proc in $cmdProcesses) {
    $cmdLine = $proc.CommandLine
    $procId = $proc.ProcessId

    # Match using -like (wildcard search)
    if ($cmdLine -like '*8094*' -or $cmdLine -like '*8070*' -or $cmdLine -like '*npm run dev*') {
        Write-Host "Stopping: PID $procId"

        # Stop process tree (parent + all children)
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue

        # Also kill any child processes directly
        $children = Get-WmiObject Win32_Process | Where-Object { $_.ParentProcessId -eq $procId }
        foreach ($child in $children) {
            Write-Host "  -> Child PID: $($child.ProcessId)"
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "  All Services Stopped"
Write-Host "========================================"
Write-Host ""
