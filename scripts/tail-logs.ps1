param(
    [ValidateSet("backend", "frontend")]
    [string]$Target = "backend",
    [int]$Tail = 80
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$logPath = Join-Path $root "logs\$Target.txt"

if (!(Test-Path $logPath)) {
    Write-Error "Log file not found: $logPath. Run .\scripts\start-local.ps1 first."
    exit 1
}

Get-Content -Path $logPath -Tail $Tail -Wait
