param(
    [Parameter(Mandatory=$true)][string]$File,
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [Parameter(Mandatory=$true)][string]$SignTool,
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
# Uses a certificate already installed by the publisher. Never stores a PFX/password in the repo.
if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw 'Release file not found' }
& $SignTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $File
if ($LASTEXITCODE -ne 0) { throw 'Signing failed' }
& $SignTool verify /pa $File
if ($LASTEXITCODE -ne 0) { throw 'Signature verification failed' }
