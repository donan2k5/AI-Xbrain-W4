param(
    [int[]]$Ports = @(8001, 5173)
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$logsDir = Join-Path $root "logs"
$pidFiles = @(
    Join-Path $logsDir "backend.pid"
    Join-Path $logsDir "frontend.pid"
)

foreach ($pidFile in $pidFiles) {
    if (Test-Path $pidFile) {
        $pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pidValue) {
            try {
                Stop-Process -Id ([int]$pidValue) -Force -ErrorAction Stop
                Write-Output "Stopped PID $pidValue from $pidFile"
            } catch {
                Write-Output "PID $pidValue was not running"
            }
        }
    }
}

$netstat = netstat -ano
foreach ($port in $Ports) {
    $matches = $netstat | Select-String "127.0.0.1:$port\s+.*LISTENING\s+(\d+)"
    foreach ($match in $matches) {
        $pidValue = [int]$match.Matches[0].Groups[1].Value
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Write-Output "Stopped listener PID $pidValue on port $port"
        } catch {
            Write-Output "Listener PID $pidValue on port $port was not running"
        }
    }
}
