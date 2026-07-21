param(
    [string]$Version = "v0.1.0"
)

$ErrorActionPreference = "Stop"

$projectDirectory = [System.IO.Path]::GetFullPath($PSScriptRoot)
$distDirectory = Join-Path $projectDirectory "dist"
$executablePath = Join-Path $distDirectory "QR-Scanner.exe"
$packageName = "Webcam-QR-Scanner-$Version-windows-x64"
$packageDirectory = Join-Path $distDirectory $packageName
$archivePath = Join-Path $distDirectory "$packageName.zip"
$checksumsPath = Join-Path $distDirectory "SHA256SUMS.txt"
$pythonPath = Join-Path $projectDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $executablePath)) {
    throw "Build the executable first: $executablePath"
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment not found: $pythonPath"
}

foreach ($target in @($packageDirectory, $archivePath, $checksumsPath)) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $resolvedTarget.StartsWith(
        $distDirectory + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to replace a path outside the dist directory: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

$licenseDirectory = Join-Path $packageDirectory "THIRD_PARTY_LICENSES"
New-Item -ItemType Directory -Path $licenseDirectory -Force | Out-Null

Copy-Item -LiteralPath $executablePath -Destination $packageDirectory
Copy-Item -LiteralPath (Join-Path $projectDirectory "LICENSE") `
    -Destination (Join-Path $packageDirectory "LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $projectDirectory "THIRD_PARTY_NOTICES.md") `
    -Destination $packageDirectory

$pythonBase = & $pythonPath -c "import sys; print(sys.base_prefix)"
$pythonLicense = Join-Path $pythonBase "LICENSE.txt"
Copy-Item -LiteralPath $pythonLicense `
    -Destination (New-Item -ItemType Directory -Path `
        (Join-Path $licenseDirectory "Python") -Force)

$sitePackages = Join-Path $projectDirectory ".venv\Lib\site-packages"

$opencvLicenseDirectory = New-Item -ItemType Directory -Path `
    (Join-Path $licenseDirectory "OpenCV") -Force
Copy-Item -LiteralPath `
    (Join-Path $sitePackages "opencv_python-5.0.0.93.dist-info\LICENSE.txt") `
    -Destination $opencvLicenseDirectory
Copy-Item -LiteralPath `
    (Join-Path $sitePackages "opencv_python-5.0.0.93.dist-info\LICENSE-3RD-PARTY.txt") `
    -Destination $opencvLicenseDirectory

$numpyLicenseSource = Join-Path $sitePackages `
    "numpy-2.5.1.dist-info\licenses"
Copy-Item -LiteralPath $numpyLicenseSource `
    -Destination (Join-Path $licenseDirectory "NumPy") -Recurse

$pyInstallerLicenseDirectory = New-Item -ItemType Directory -Path `
    (Join-Path $licenseDirectory "PyInstaller") -Force
Copy-Item -LiteralPath `
    (Join-Path $sitePackages "pyinstaller-6.21.0.dist-info\licenses\COPYING.txt") `
    -Destination $pyInstallerLicenseDirectory

Compress-Archive -LiteralPath $packageDirectory -DestinationPath $archivePath `
    -CompressionLevel Optimal

$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash
$executableHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $executablePath).Hash
$checksumContent = @(
    "$archiveHash  $packageName.zip"
    "$executableHash  QR-Scanner.exe (inside ZIP)"
)
Set-Content -LiteralPath $checksumsPath -Value $checksumContent -Encoding ascii

Remove-Item -LiteralPath $packageDirectory -Recurse -Force

Write-Output "Release package: $archivePath"
Write-Output "Checksums: $checksumsPath"
