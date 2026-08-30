# BtDeck Windows 生命周期驱动（release-artifact-equivalence-gate task .5 / G6）
# 仅在 GitHub windows-2022 Runner 执行（本机无 ISCC，本地结果记 NOT_RUN，不得默认通过）。
#
# 前置（同 job 内先完成）：
#   - python scripts\release\build_frontend.py
#   - deploy\build-windows.bat --release     → dist\btdeck.exe + dist\BtDeck-v1.0.6-*-setup.exe
#   - v1.0.5 portable EXE 夹具（.release-build-v1.0.5\assets\BtDeck-v1.0.5-windows-x64-portable.exe
#     或从 tag 重建），用于“升级数据保留”场景（reconstructed 语义：无 v1.0.5 安装器）
#
# 场景（fail-closed）：
#   A. 免安装 EXE：隔离目录启动→健康/身份→停止→端口释放→二次启动 secret 不重置
#   B. Setup 静默首装→NSSM 服务单实例→同版本静默覆盖→v1.0.5 夹具植入→升级覆盖→
#      secret/数据保留→静默卸载→服务与程序移除、数据默认保留
# 输出：w3-lifecycle-windows.json（job 根目录）

param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path,
    [string]$V105PortableExe = "",
    [string]$ReportPath = "w3-lifecycle-windows.json"
)

$ErrorActionPreference = "Stop"
$script:Phases = New-Object System.Collections.Generic.List[string]
$script:Failed = $false

function Add-Phase([string]$Name, [bool]$Pass, [string]$Details = "") {
    $status = if ($Pass) { "PASS" } else { "FAIL" }
    $entry = @{ name = $Name; status = $status }
    if ($Details) { $entry.details = $Details }
    $script:Phases += ($entry | ConvertTo-Json -Compress)
    if ($Pass) { Write-Output "[PHASE-PASS] $Name" }
    else {
        $script:Failed = $true
        Write-Output "[PHASE-FAIL] $Name $Details"
    }
}

function Wait-Health([string]$Url, [string]$Pattern, [int]$MaxSeconds = 240) {
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $body = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri $Url).Content
            if ($body -match $Pattern) { return $body }
        } catch { Start-Sleep -Seconds 4 }
    }
    return $null
}

function Stop-BtDeckProcesses {
    Get-Process -Name btdeck -ErrorAction SilentlyContinue | Stop-Process -Force
    & "$ProjectRoot\deploy\nssm.exe" stop BtDeck 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

$NewExe = Join-Path $ProjectRoot "dist\btdeck.exe"
$SetupExe = Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "BtDeck-v*-windows-x64-setup.exe" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$IsccNssm = Join-Path $ProjectRoot "deploy\nssm.exe"
$InstallDir = "$env:ProgramFiles\BtDeck"

# ---------------- 场景 A：免安装 EXE ----------------
$IsoDir = Join-Path $env:RUNNER_TEMP "w3-iso"
New-Item -ItemType Directory -Force -Path $IsoDir | Out-Null
Copy-Item $NewExe (Join-Path $IsoDir "btdeck.exe")
$p = Start-Process -FilePath (Join-Path $IsoDir "btdeck.exe") -WorkingDirectory $IsoDir -PassThru -WindowStyle Hidden
$body = Wait-Health "http://127.0.0.1:5001/health/live" '"status":"alive"'
$okA = $null -ne $body -and $body -match '"version": "1.0.6"' -and $body -match '"build": \{"status": "ok"'
Add-Phase "portable_exe_start_identity" $okA ("last=" + ($body -replace '\s+', '')[0..120] -join '')
if (Test-Path (Join-Path $IsoDir "config\btdeck.env")) {
    $secret1 = (Get-FileHash (Join-Path $IsoDir "config\btdeck.env") -Algorithm SHA256).Hash
} else { $secret1 = $null; Get-ChildItem $IsoDir -Recurse | Select-Object -First 5 | ForEach-Object { Write-Output $_.FullName } }
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$portFreed = -not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)
Add-Phase "portable_exe_stop_port_freed" $portFreed
$p2 = Start-Process -FilePath (Join-Path $IsoDir "btdeck.exe") -WorkingDirectory $IsoDir -PassThru -WindowStyle Hidden
$body2 = Wait-Health "http://127.0.0.1:5001/health/live" '"status":"alive"'
$secret2 = if (Test-Path (Join-Path $IsoDir "config\btdeck.env")) {
    (Get-FileHash (Join-Path $IsoDir "config\btdeck.env") -Algorithm SHA256).Hash } else { $null }
Add-Phase "portable_exe_restart_secret_stable" ($null -ne $body2 -and $secret1 -eq $secret2 -and $null -ne $secret1)
Stop-Process -Id $p2.Id -Force -ErrorAction SilentlyContinue
Stop-BtDeckProcesses

# ---------------- 场景 B：Setup 生命周期 ----------------
if ($null -eq $SetupExe) {
    Add-Phase "setup_silent_install" $false "dist 下未找到 setup exe（build-windows.bat --release 应产出）"
} else {
    # B1 静默首装
    Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
    $svc = Get-Service -Name BtDeck -ErrorAction SilentlyContinue
    $bodyB = Wait-Health "http://127.0.0.1:5001/health/live" '"version": "1.0.6"'
    $single = ($svc | Measure-Object).Count -eq 1 -and $svc.Status -eq "Running"
    $listeners = @(Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue).Count
    Add-Phase "setup_silent_install" ($single -and $null -ne $bodyB -and $listeners -eq 1) "listeners=$listeners"

    $envFile = Join-Path $InstallDir "config\btdeck.env"
    $secretB1 = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }

    # B2 同版本静默覆盖
    Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
    Start-Sleep -Seconds 5
    $svc2 = Get-Service -Name BtDeck -ErrorAction SilentlyContinue
    $secretB2 = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }
    $svcCount = @(Get-Service -Name BtDeck -ErrorAction SilentlyContinue).Count
    Add-Phase "setup_same_version_reinstall" `
        ($svcCount -eq 1 -and $svc2.Status -eq "Running" -and $secretB1 -eq $secretB2 -and $null -ne $secretB1) `
        "services=$svcCount secretStable=$($secretB1 -eq $secretB2)"

    # B3 v1.0.5 夹具植入（portable 落位安装目录运行一次，产生 v1.0.5 期配置/数据库）
    $markerPath = Join-Path $InstallDir "config\w3-marker.txt"
    if ($V105PortableExe -and (Test-Path $V105PortableExe)) {
        Stop-BtDeckProcesses
        Copy-Item $V105PortableExe (Join-Path $InstallDir "btdeck-v105-fixture.exe") -Force
        $pf = Start-Process -FilePath (Join-Path $InstallDir "btdeck-v105-fixture.exe") -WorkingDirectory $InstallDir -PassThru -WindowStyle Hidden
        $bodyV105 = Wait-Health "http://127.0.0.1:5001/health/live" '"version": "1.0.5"' 180
        Add-Phase "v105_fixture_seeded" ($null -ne $bodyV105)
        Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        Set-Content -Path $markerPath -Value "w3-windows-upgrade"
        $secretBefore = (Get-FileHash $envFile -Algorithm SHA256).Hash

        # B4 升级覆盖（同 v1.0.6 setup 再装一遍 = 覆盖升级路径）
        Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
        Start-Sleep -Seconds 5
        & $IsccNssm start BtDeck 2>$null | Out-Null
        $bodyUp = Wait-Health "http://127.0.0.1:5001/health/live" '"version": "1.0.6"' 240
        $secretAfter = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }
        Add-Phase "upgrade_keeps_secret_and_data" `
            ($null -ne $bodyUp -and (Test-Path $markerPath) -and $secretBefore -eq $secretAfter) `
            "health=$($null -ne $bodyUp) marker=$(Test-Path $markerPath) secretStable=$($secretBefore -eq $secretAfter)"
    } else {
        Add-Phase "v105_fixture_seeded" $false "未提供 v1.0.5 portable 夹具（--V105PortableExe）"
        Add-Phase "upgrade_keeps_secret_and_data" $false "前置夹具缺失"
    }

    # B5 静默卸载：服务+程序移除、数据默认保留
    $uninst = Join-Path $InstallDir "unins000.exe"
    if (Test-Path $uninst) {
        Start-Process -FilePath $uninst -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES" -Wait
        Start-Sleep -Seconds 3
        $svcGone = $null -eq (Get-Service -Name BtDeck -ErrorAction SilentlyContinue)
        $exeGone = -not (Test-Path (Join-Path $InstallDir "btdeck.exe"))
        $dataKept = (Test-Path $markerPath) -and (Test-Path $envFile)
        Add-Phase "uninstall_removes_program_keeps_data" ($svcGone -and $exeGone -and $dataKept) `
            "svcGone=$svcGone exeGone=$exeGone dataKept=$dataKept"
    } else {
        Add-Phase "uninstall_removes_program_keeps_data" $false "未找到 unins000.exe"
    }
}

Stop-BtDeckProcesses

$verdict = if ($script:Failed) { "FAIL" } else { "PASS" }
$report = @{
    schema_version = 1
    scenario = "windows-lifecycle"
    executed_at = (Get-Date -AsUTC -Format "yyyy-MM-ddTHH:mm:ssZ")
    verdict = $verdict
    phases = $script:Phases
}
$report | ConvertTo-Json -Depth 4 | Set-Content -Path $ReportPath
Write-Output "report: $ReportPath verdict=$verdict"
if ($script:Failed) { exit 1 }
