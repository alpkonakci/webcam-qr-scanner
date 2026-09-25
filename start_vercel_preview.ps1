[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$previewOrigin = "https://webcam-qr-scanner-git-codex-vercel-48147c-alpkonakcis-projects.vercel.app"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$launcherPath = Join-Path $PSScriptRoot "launcher.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python environment was not found at $pythonPath"
}

$secureSecret = Read-Host "Paste the NEW Vercel automation bypass secret" -AsSecureString
$secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)

try {
    $plainSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
}

if ([string]::IsNullOrWhiteSpace($plainSecret)) {
    throw "The Vercel bypass secret cannot be empty."
}

$health = Invoke-RestMethod `
    -Uri "$previewOrigin/healthz" `
    -Headers @{ "x-vercel-protection-bypass" = $plainSecret } `
    -TimeoutSec 15

if (
    $health.status -ne "ok" -or
    $health.protocol -ne "wqrs/1" -or
    $health.transport -ne "supabase-realtime"
) {
    throw "The Vercel preview returned an unexpected health response."
}

$env:WQRS_RELAY_ORIGIN = $previewOrigin
$env:WQRS_VERCEL_BYPASS_ORIGIN = $previewOrigin
$env:WQRS_VERCEL_BYPASS_SECRET = $plainSecret

Write-Host "Vercel preview verified. Starting QR Scanner..." -ForegroundColor Green

try {
    & $pythonPath $launcherPath
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:WQRS_VERCEL_BYPASS_SECRET -ErrorAction SilentlyContinue
    $plainSecret = $null
}
