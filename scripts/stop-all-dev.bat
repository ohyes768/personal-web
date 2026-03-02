@echo off
REM ============================================
REM personal-web Local Development - Stop All
REM Stop Gateway, Frontend, douyin-processor
REM ============================================

echo.
echo ========================================
echo   Stop personal-web Dev Environment
echo ========================================
echo.

echo Stopping services by port...
echo.

powershell -NoProfile -Command ^
  "$ports = @(8070, 8093, 3000);" ^
  "$names = @{8070='Gateway'; 8093='douyin-processor'; 3000='Frontend'};" ^
  "foreach ($port in $ports) {" ^
  "  try {" ^
  "    $pid = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1).OwningProcess;" ^
  "    if ($pid) {" ^
  "      Write-Host \"Stopping $($names[$port]) (PID $pid)...\";" ^
  "      Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue;" ^
  "    }" ^
  "  } catch {}" ^
  "}"

timeout /t 2 /nobreak >nul

echo ========================================
echo   All Services Stopped
echo ========================================
echo.
pause
