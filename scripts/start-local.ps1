param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$logsDir = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$backendLog = Join-Path $logsDir "backend.txt"
$frontendLog = Join-Path $logsDir "frontend.txt"
$backendPid = Join-Path $logsDir "backend.pid"
$frontendPid = Join-Path $logsDir "frontend.pid"
$runner = Join-Path $PSScriptRoot "run_with_log.py"

function Stop-PortListeners {
    param([int[]]$Ports)

    $netstat = netstat -ano
    foreach ($port in $Ports) {
        $matches = $netstat | Select-String "127.0.0.1:$port\s+.*LISTENING\s+(\d+)"
        foreach ($match in $matches) {
            $pidValue = [int]$match.Matches[0].Groups[1].Value
            try {
                Stop-Process -Id $pidValue -Force -ErrorAction Stop
                Write-Output "Stopped existing listener PID $pidValue on port $port"
            } catch {
                Write-Output "Existing listener PID $pidValue on port $port was not running"
            }
        }
    }
}

Stop-PortListeners -Ports @($BackendPort, $FrontendPort)

$backendArgs = @(
    $runner,
    "--cwd", $backendDir,
    "--log", $backendLog,
    "--hello", "hello-backend",
    "--env", "HTTP_PROXY=",
    "--env", "HTTPS_PROXY=",
    "--env", "http_proxy=",
    "--env", "https_proxy=",
    "--env", "NO_PROXY=localhost,127.0.0.1,::1",
    "--env", "no_proxy=localhost,127.0.0.1,::1",
    "--",
    "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort"
)

$frontendArgs = @(
    $runner,
    "--cwd", $frontendDir,
    "--log", $frontendLog,
    "--hello", "hello-frontend",
    "--env", "VITE_API_BASE_URL=http://127.0.0.1:$BackendPort",
    "--",
    "npm.cmd", "run", "dev", "--", "--port", "$FrontendPort"
)

$backend = Start-Process -FilePath python -ArgumentList $backendArgs -PassThru -WindowStyle Hidden
$frontend = Start-Process -FilePath python -ArgumentList $frontendArgs -PassThru -WindowStyle Hidden

Set-Content -Path $backendPid -Value $backend.Id
Set-Content -Path $frontendPid -Value $frontend.Id

Start-Sleep -Seconds 4

Write-Output "Backend PID: $($backend.Id) log: $backendLog"
Write-Output "Frontend PID: $($frontend.Id) log: $frontendLog"
Write-Output "Backend URL: http://127.0.0.1:$BackendPort"
Write-Output "Frontend URL: http://127.0.0.1:$FrontendPort"
Write-Output "Tail backend: .\scripts\tail-logs.ps1 backend"
Write-Output "Tail frontend: .\scripts\tail-logs.ps1 frontend"
