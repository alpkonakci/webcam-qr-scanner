function Resolve-ReleaseVersion {
    param(
        [Parameter(Mandatory)][string]$ProjectDirectory,
        [string]$RequestedVersion = ''
    )
    $versionPython = Join-Path $ProjectDirectory '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $versionPython -PathType Leaf)) {
        throw "Virtual environment not found: $versionPython"
    }
    Push-Location -LiteralPath $ProjectDirectory
    try {
        $applicationVersion = & $versionPython -c 'from app_info import APP_VERSION; print(APP_VERSION)'
        if ($LASTEXITCODE -ne 0 -or $applicationVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
            throw 'Cannot resolve application version.'
        }
    }
    finally { Pop-Location }
    $expectedVersion = "v$applicationVersion"
    if ($RequestedVersion -and $RequestedVersion -cne $expectedVersion) {
        throw 'Package version does not match application version.'
    }
    return $expectedVersion
}
