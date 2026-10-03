param([Parameter(Mandatory=$true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$testRoot = Join-Path $workspace ('build/installer-smoke-' + [Guid]::NewGuid().ToString('N'))
$testRoot = [IO.Path]::GetFullPath($testRoot)
if (-not $testRoot.StartsWith(($workspace + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected test path' }
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{757AC553-6205-4B6B-ACB3-C6F68972804B}_is1'
if (Test-Path -LiteralPath $registryKey) { throw 'Existing Travel Desk installation detected; test will not modify it' }
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$appDir = Join-Path $testRoot 'app'
$report = Join-Path $testRoot 'package-smoke.json'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=',('/DIR="' + $appDir + '"'))
function Run-Checked($file, $arguments) {
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw ('Process failed: ' + $process.ExitCode) }
}
$uninstaller = Join-Path $appDir 'unins000.exe'
try {
    $guard = [Threading.Mutex]::new($false, 'TravelDeskRunning')
    try {
        $blocked = Start-Process -FilePath $installerPath -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
        if ($blocked.ExitCode -eq 0) { throw 'Installer did not block a running application' }
    } finally { $guard.Dispose() }
    Run-Checked $installerPath $arguments
    $marker = Join-Path $appDir 'synthetic.state.json'
    Set-Content -LiteralPath $marker -Value '{"status":"submission_pending","synthetic":true}' -Encoding UTF8
    $originalHash = (Get-FileHash -LiteralPath $marker).Hash
    # Repeat installation exercises an in-place upgrade. No user profile is read.
    Run-Checked $installerPath $arguments
    if ((Get-FileHash -LiteralPath $marker).Hash -ne $originalHash) { throw 'Upgrade changed local data' }
    $env:QT_QPA_PLATFORM = 'offscreen'
    Run-Checked (Join-Path $appDir 'TravelDesk.exe') @('--self-test', ('"' + $report + '"'))
    $guard = [Threading.Mutex]::new($false, 'TravelDeskRunning')
    try {
        $blocked = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait -PassThru
        if ($blocked.ExitCode -eq 0) { throw 'Uninstaller did not block a running application' }
    } finally { $guard.Dispose() }
    Run-Checked $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
    if (Test-Path -LiteralPath (Join-Path $appDir 'TravelDesk.exe')) { throw 'Uninstall left the executable' }
    if ((Get-FileHash -LiteralPath $marker).Hash -ne $originalHash) { throw 'Uninstall changed local data' }
    Write-Output 'Installation, upgrade, packaged startup, uninstall and local data preservation passed.'
    Get-Content -LiteralPath $report
} finally {
    if (Test-Path -LiteralPath $uninstaller) {
        Run-Checked $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
    }
}
