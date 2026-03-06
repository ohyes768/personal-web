# Stop Dev Services - Kill Process Tree
Write-Host ""
Write-Host "========================================"
Write-Host "  Stopping Dev Environment"
Write-Host "========================================"
Write-Host ""

Write-Host "Stopping services by port (with process tree)..."

# Target ports and their service names
$services = @{
    8070 = "Gateway"
    8093 = "douyin-processor"
    8094 = "global-macro-fin"
    3000 = "Frontend"
}

$stoppedCount = 0

foreach ($port in $services.Keys) {
    try {
        # Find process listening on the port
        $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop |
                      Select-Object -First 1

        if ($connection) {
            $pid = $connection.OwningProcess
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue

            if ($process) {
                Write-Host "Stopping $($services[$port]) (PID $pid, port $port)..."

                # Use taskkill /T to terminate the entire process tree
                # /T = Terminate all child processes
                # /F = Force termination
                $result = & taskkill /F /T /PID $pid 2>&1

                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  -> Process tree terminated"
                    $stoppedCount++
                } else {
                    Write-Host "  -> Failed: $result"
                }
            }
        }
    } catch {
        # Port not in use, skip
    }
}

Write-Host ""
Write-Host "Stopped $stoppedCount service(s)"
Write-Host "========================================"
Write-Host "  All Services Stopped"
Write-Host "========================================"
Write-Host ""
