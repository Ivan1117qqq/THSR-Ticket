param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$PreviousInstaller,
    [Guid]$AppId = '757AC553-6205-4B6B-ACB3-C6F68972804B'
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$testRoot = Join-Path $workspace ('build/installer-smoke-' + [Guid]::NewGuid().ToString('N'))
$testRoot = [IO.Path]::GetFullPath($testRoot)
if (-not $testRoot.StartsWith(($workspace + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected test path' }
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + $AppId.ToString().ToUpperInvariant() + '}_is1'
if (Test-Path -LiteralPath $registryKey) { throw 'Existing Travel Desk installation detected; test will not modify it' }
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$previousPath = if ($PreviousInstaller) { (Resolve-Path -LiteralPath $PreviousInstaller).Path } else { $installerPath }
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
    Run-Checked $previousPath $arguments
    $previousVersion = (Get-Item -LiteralPath (Join-Path $appDir 'TravelDesk.exe')).VersionInfo.FileVersion
    $marker = Join-Path $appDir 'synthetic.state.json'
    Set-Content -LiteralPath $marker -Value '{"status":"submission_pending","synthetic":true}' -Encoding UTF8
    $originalHash = (Get-FileHash -LiteralPath $marker).Hash
    # Test synthetic data outside {app}, matching the product's separate data layout.
    $dataRoot = Join-Path $testRoot 'synthetic-data'
    $syntheticFiles = @(
        'booking.local.json', 'booking.local.state.json', 'booking.local.task.json',
        'booking.local.runs/demo/result.json', 'booking.local.runs/demo/events.jsonl',
        'booking.local.runs.history-backups/demo/state.json', 'booking.local.runs.operations/demo.json'
    )
    $hashes = @{}
    foreach ($relative in $syntheticFiles) {
        $target = Join-Path $dataRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        [IO.File]::WriteAllText($target, '{"synthetic":true,"status":"submission_pending"}')
        $hashes[$target] = (Get-FileHash -LiteralPath $target).Hash
    }
    # With PreviousInstaller this exercises old -> new, otherwise same-version reinstall.
    Run-Checked $installerPath $arguments
    $installedVersion = (Get-Item -LiteralPath (Join-Path $appDir 'TravelDesk.exe')).VersionInfo.FileVersion
    if ($PreviousInstaller -and $installedVersion -eq $previousVersion) { throw 'Expected an actual version upgrade' }
    if ((Get-FileHash -LiteralPath $marker).Hash -ne $originalHash) { throw 'Upgrade changed local data' }
    foreach ($target in $hashes.Keys) {
        if ((Get-FileHash -LiteralPath $target).Hash -ne $hashes[$target]) { throw 'Upgrade changed synthetic data' }
    }
    $env:QT_QPA_PLATFORM = 'offscreen'
    Run-Checked (Join-Path $appDir 'TravelDesk.exe') @('--self-test', ('"' + $report + '"'))
    $smoke = Get-Content -LiteralPath $report | ConvertFrom-Json
    if (-not ($smoke.qml -and $smoke.ocr_standard -and $smoke.ocr_beta -and $smoke.playwright_driver -and $smoke.private_storage)) {
        throw 'Installed EXE self-test did not pass'
    }
    $guard = [Threading.Mutex]::new($false, 'TravelDeskRunning')
    try {
        $blocked = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait -PassThru
        if ($blocked.ExitCode -eq 0) { throw 'Uninstaller did not block a running application' }
    } finally { $guard.Dispose() }
    Run-Checked $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
    if (Test-Path -LiteralPath (Join-Path $appDir 'TravelDesk.exe')) { throw 'Uninstall left the executable' }
    if ((Get-FileHash -LiteralPath $marker).Hash -ne $originalHash) { throw 'Uninstall changed local data' }
    foreach ($target in $hashes.Keys) {
        if ((Get-FileHash -LiteralPath $target).Hash -ne $hashes[$target]) { throw 'Uninstall changed synthetic data' }
    }
    $validation = @{
        app_id = $AppId.ToString(); previous_version = $previousVersion; installed_version = $installedVersion
        actual_upgrade = [bool]$PreviousInstaller; synthetic_files_preserved = $hashes.Count + 1
        install_mutex_blocked = $true; uninstall_mutex_blocked = $true; uninstall_removed_exe = $true
        self_test = $smoke
    }
    $validation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $testRoot 'validation.json') -Encoding UTF8
    Write-Output 'Installation, upgrade, packaged startup, uninstall and local data preservation passed.'
    Get-Content -LiteralPath $report
} finally {
    if (Test-Path -LiteralPath $uninstaller) {
        Run-Checked $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
    }
}
