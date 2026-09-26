[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Read-PlainTextSecret {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt
    )

    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Test-ApiKey {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    return $Value.StartsWith($Prefix, [StringComparison]::Ordinal) `
        -and $Value.Length -ge ($Prefix.Length + 20) `
        -and $Value.Length -le 4096 `
        -and $Value -notmatch '\s'
}

function New-RateLimitPepper {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

$projectUrl = (Read-Host "Supabase Project URL").Trim().TrimEnd("/")
$publishableKey = (Read-Host "Supabase publishable key").Trim()
$secretKey = Read-PlainTextSecret "Supabase secret key (input is hidden)"

try {
    $parsedUrl = [Uri]$projectUrl
    if (
        $parsedUrl.Scheme -ne "https" `
        -or $parsedUrl.AbsolutePath -ne "/" `
        -or $parsedUrl.Query `
        -or $parsedUrl.Fragment `
        -or -not $parsedUrl.Host.EndsWith(".supabase.co", [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Supabase Project URL is invalid."
    }
    if (-not (Test-ApiKey -Value $publishableKey -Prefix "sb_publishable_")) {
        throw "The publishable key format is invalid."
    }
    if (-not (Test-ApiKey -Value $secretKey -Prefix "sb_secret_")) {
        throw "The secret key format is invalid."
    }

    $env:SUPABASE_URL = $projectUrl
    $env:SUPABASE_PUBLISHABLE_KEY = $publishableKey
    $env:SUPABASE_SECRET_KEY = $secretKey
    $env:RELAY_RATE_LIMIT_PEPPER = New-RateLimitPepper

    Write-Host "Starting the local Next.js relay without writing secrets to disk..."
    Push-Location -LiteralPath $PSScriptRoot
    try {
        npm run dev
    }
    finally {
        Pop-Location
    }
}
finally {
    $secretKey = $null
    Remove-Item Env:SUPABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SUPABASE_PUBLISHABLE_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:SUPABASE_SECRET_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:RELAY_RATE_LIMIT_PEPPER -ErrorAction SilentlyContinue
}
