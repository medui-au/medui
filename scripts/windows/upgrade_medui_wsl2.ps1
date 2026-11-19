# Upgrade MedUI in an existing WSL2 instance, keeping its data and settings.
# Run from PowerShell (administrator not needed):
#   powershell.exe -NoExit -ExecutionPolicy Bypass -File .\upgrade_medui_wsl2.ps1
# Optionally saves a snapshot of the whole instance first (wsl --export), then runs
# upgrade.sh inside it, which backs up the database and asks before it changes anything.
# See scripts/windows/README.md.

param(
    [string]$Instance = "",     # WSL instance name (asked if not given)
    [string]$To = ""            # tag, branch or commit to upgrade to (default: the installed branch's latest)
)

$ErrorActionPreference = 'Stop'
$DefaultName = "medui"
$AppDirName  = "medui_os"
$SnapshotDir = Join-Path $env:USERPROFILE "WSL-snapshots"
$RepoUrl     = "https://github.com/medui-au/medui.git"

# Pipe plain UTF-8 (no BOM) into wsl.exe
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Get-WslDistroInfo {
    # Parse 'wsl --list --verbose' (UTF-16) into objects: Name, State, Version, IsDefault.
    $old = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::Unicode
        $out = & wsl.exe --list --verbose
    } finally {
        [Console]::OutputEncoding = $old
    }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return @() }
    $rows = foreach ($line in $out) {
        $clean = ($line -replace "`0", '')
        if ($clean -match '^\s*(\*)?\s*(\S+)\s+(Running|Stopped|Installing|Uninstalling|Converting)\s+(\d+)\s*$') {
            [pscustomobject]@{ Name = $Matches[2]; State = $Matches[3]; Version = $Matches[4]; IsDefault = [bool]$Matches[1] }
        }
    }
    return @($rows)
}

function ConvertTo-PlainText([System.Security.SecureString]$Secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Test-GitHubAccess([string]$Token) {
    # Can this token (or none) read the repository? ok, bad-token, no-access, needs-token or
    # unreachable. The token goes only in a request header (as in create_medui_wsl2.ps1).
    if ($RepoUrl -match 'github\.com[/:]([^/]+)/([^/]+?)(\.git)?$') {
        $api = "https://api.github.com/repos/$($Matches[1])/$($Matches[2])"
    } else { return 'unreachable' }
    $headers = @{ 'User-Agent' = 'medui-upgrader'; 'Accept' = 'application/vnd.github+json' }
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    try {
        $null = Invoke-WebRequest -UseBasicParsing -Uri $api -Headers $headers -TimeoutSec 20
    } catch {
        $response = $_.Exception.Response
        if (-not $response) { return 'unreachable' }
        $code = [int]$response.StatusCode
        if ($code -eq 401) { return 'bad-token' }
        if ($code -eq 403 -or $code -eq 404) { if ($Token) { return 'no-access' } else { return 'needs-token' } }
        return 'unreachable'
    }
    return 'ok'
}

function Get-WslBasePath([string]$Name) {
    # Where the instance's disk lives, for 'wsl --import' when restoring a snapshot.
    $key = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' -ErrorAction SilentlyContinue |
        Where-Object { (Get-ItemProperty $_.PSPath).DistributionName -eq $Name } | Select-Object -First 1
    if ($key) { return (Get-ItemProperty $key.PSPath).BasePath -replace '^\\\\\?\\', '' }
    return $null
}

# --- 1. Which instance ---
Write-Host "`n=== 1. MedUI instance ===" -ForegroundColor Cyan
$distros = Get-WslDistroInfo
if (-not $distros) { throw "No WSL instances found ('wsl --list --verbose')." }
$distros | ForEach-Object { Write-Host ("    {0,-24} {1}" -f $_.Name, $_.State) }
if (-not $Instance) {
    $Instance = Read-Host "Instance to upgrade [$DefaultName]"
    if ([string]::IsNullOrWhiteSpace($Instance)) { $Instance = $DefaultName }
}
if (-not ($distros.Name -contains $Instance)) { throw "There is no WSL instance called '$Instance'." }

# The MedUI folder and its owner, inside the instance (this starts the instance if stopped).
# Sent on stdin: Windows PowerShell 5.1 mangles quotes in arguments to native programs.
$findScript = 'for d in /home/*/' + $AppDirName + '; do [ -f "$d/compose.yaml" ] && [ -f "$d/.env" ] && echo "$d $(stat -c %U "$d")"; done; true'
$found = $findScript | & wsl.exe -d $Instance -u root -- bash -c "tr -d '\r' | bash -s"
$found = @($found | Where-Object { $_ -match '\S' })
if ($found.Count -eq 0) { throw "No installed MedUI (/home/<user>/$AppDirName with a .env) found in '$Instance'." }
if ($found.Count -gt 1) { throw "More than one MedUI folder in '$Instance': $($found -join '; '). Run upgrade.sh in the one you mean." }
$AppDir, $LinuxUser = $found[0].Trim() -split ' ', 2
Write-Host "[+] '$Instance': $AppDir (user $LinuxUser)" -ForegroundColor Green

# --- 2. Snapshot of the whole instance (optional) ---
Write-Host "`n=== 2. Snapshot of the whole instance (optional) ===" -ForegroundColor Cyan
Write-Host "    upgrade.sh backs up MedUI's database and settings itself. A snapshot also keeps"
Write-Host "    everything else in the instance (Docker, its images, Ubuntu), and is the simplest way"
Write-Host "    back: it replaces the whole instance. It stops the instance (and MedUI) while it is"
Write-Host "    written, takes several minutes and several GB."
$SnapshotFile = $null
$drive = (Split-Path $SnapshotDir -Qualifier).TrimEnd(':')
$freeGB = [math]::Floor((Get-PSDrive $drive).Free / 1GB)
Write-Host "    Saved to $SnapshotDir ($freeGB GB free on ${drive}:)."
if ((Read-Host "Save a snapshot first? (Y/n)") -notmatch '^[nN]$') {
    if ($freeGB -lt 15) { Write-Host "[!] Less than 15 GB free on ${drive}: - the snapshot may not fit." -ForegroundColor Yellow }
    New-Item -ItemType Directory -Force -Path $SnapshotDir | Out-Null
    $SnapshotFile = Join-Path $SnapshotDir ("{0}-{1}.tar" -f $Instance, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $BasePath = Get-WslBasePath $Instance
    Write-Host "[*] Stopping '$Instance' and writing $SnapshotFile ..." -ForegroundColor Cyan
    # The keep-alive task's loop starts a stopped instance again within seconds, which would let
    # MedUI and PostgreSQL run while the snapshot is written. End the task first; its 5-minute
    # trigger brings it back afterwards (tasks from before that trigger come back at next logon).
    $KeepAliveTask = Get-ScheduledTask -TaskName "WSL2 $Instance keep-alive" -ErrorAction SilentlyContinue
    if ($KeepAliveTask) { $KeepAliveTask | Stop-ScheduledTask }
    wsl.exe --terminate $Instance
    wsl.exe --export $Instance $SnapshotFile
    if ($LASTEXITCODE -ne 0) { throw "wsl --export failed (exit $LASTEXITCODE). Nothing in MedUI was changed." }
    $sizeGB = [math]::Round((Get-Item $SnapshotFile).Length / 1GB, 1)
    Write-Host "[+] Snapshot saved ($sizeGB GB)." -ForegroundColor Green
    # The keep-alive task (create_medui_wsl2.ps1) was ended above. Starting it from here leaves an
    # empty PowerShell window open, so keep the instance running the same way, hidden, until the
    # task's own trigger takes over again (within 5 minutes, or at the next logon).
    if ($KeepAliveTask) {
        Start-Process -FilePath "wsl.exe" -ArgumentList @('-d', $Instance, '--exec', '/bin/sleep', 'infinity') -WindowStyle Hidden
        Write-Host "[+] Instance kept running (as the keep-alive task does)." -ForegroundColor Green
    }
} else {
    Write-Host "[+] No snapshot." -ForegroundColor Green
}

# --- 3. GitHub access ---
# A private repository needs a token for 'git fetch'. It is asked here, checked with GitHub,
# and handed to the instance in an environment variable (WSLENV) for this run only: never on
# a command line, never written to disk. upgrade.sh uses it through a temporary GIT_ASKPASS helper.
Write-Host "`n=== 3. GitHub access ===" -ForegroundColor Cyan
$GitToken = ""
$Access = Test-GitHubAccess ""
while ($Access -ne 'ok') {
    switch ($Access) {
        'needs-token' { Write-Host "    The repository is private: a GitHub token with read access is needed." }
        'bad-token'   { Write-Host "[!] GitHub didn't accept that token. Try again." -ForegroundColor Yellow }
        'no-access'   { Write-Host "[!] That token can't read the repository. Try again." -ForegroundColor Yellow }
        'unreachable' { throw "Couldn't reach GitHub. Check the network and run this again. Nothing in MedUI was changed." }
    }
    Write-Host "    Paste with a right-click (Ctrl+V doesn't paste into this hidden prompt)."
    $GitToken = (ConvertTo-PlainText (Read-Host "GitHub token" -AsSecureString)).Trim()
    if ($GitToken) { Write-Host "Token received: $($GitToken.Length) characters." }
    $Access = Test-GitHubAccess $GitToken
}
Write-Host "[+] Repository readable$(if ($GitToken) { ' with the token' })." -ForegroundColor Green
$env:MEDUI_GIT_TOKEN = $GitToken
$OldWslEnv = $env:WSLENV
$env:WSLENV = (@('MEDUI_GIT_TOKEN/u') + @($OldWslEnv | Where-Object { $_ })) -join ':'

# --- 4. upgrade.sh inside the instance ---
Write-Host "`n=== 4. Upgrade (upgrade.sh, in the instance) ===" -ForegroundColor Cyan
$ToArgs = @(); if ($To) { $ToArgs = @('--to', $To) }
& wsl.exe -d $Instance -u $LinuxUser -e test -f "$AppDir/upgrade.sh"
if ($LASTEXITCODE -eq 0) {
    & wsl.exe -d $Instance -u $LinuxUser --cd $AppDir -- ./upgrade.sh @ToArgs
} else {
    # An installation from before upgrade.sh existed: run the new release's copy from outside the folder.
    Write-Host "[*] This installation predates upgrade.sh; using the copy from the new release." -ForegroundColor Cyan
    $ref = if ($To) { $To } else { "@{u}" }
    $Fetched = "/home/$LinuxUser/medui-upgrade.sh"
    $fetch = "set -e; cd '$AppDir'; " +
             'ask=$(mktemp); trap ''rm -f "$ask"'' EXIT; chmod 700 "$ask"; ' +
             'printf ''#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) printf "%%s\\n" "$MEDUI_GIT_TOKEN" ;; esac\n'' > "$ask"; ' +
             'if [ -n "${MEDUI_GIT_TOKEN:-}" ]; then export GIT_ASKPASS="$ask"; fi; ' +
             'GIT_TERMINAL_PROMPT=0 git fetch --quiet --tags origin; ' +
             "{ git show 'origin/${ref}:upgrade.sh' 2>/dev/null || git show '${ref}:upgrade.sh'; } > '$Fetched'"
    $fetch | & wsl.exe -d $Instance -u $LinuxUser -- bash -c "tr -d '\r' | bash -s"
    if ($LASTEXITCODE -ne 0) { throw "Couldn't get upgrade.sh from the repository (is '$ref' right?). Nothing was changed." }
    & wsl.exe -d $Instance -u $LinuxUser --cd $AppDir -- env "MEDUI_DIR=$AppDir" bash $Fetched @ToArgs
}
$code = $LASTEXITCODE
$env:MEDUI_GIT_TOKEN = $null; $GitToken = $null; $env:WSLENV = $OldWslEnv

# --- 5. Summary ---
Write-Host ""
if ($code -eq 0) {
    Write-Host "[+] Upgrade finished. Check MedUI in the browser." -ForegroundColor Green
} else {
    Write-Host "[!] upgrade.sh stopped (exit $code). Its last message says what to do." -ForegroundColor Yellow
}
if ($SnapshotFile) {
    Write-Host "`nTo put the whole instance back as it was before this upgrade (everything since is lost):" -ForegroundColor Cyan
    if (Get-ScheduledTask -TaskName "WSL2 $Instance keep-alive" -ErrorAction SilentlyContinue) {
        Write-Host "    Stop-ScheduledTask -TaskName 'WSL2 $Instance keep-alive'   # else it starts the instance again"
    }
    Write-Host "    wsl --terminate $Instance"
    Write-Host "    wsl --unregister $Instance"
    if ($BasePath) { Write-Host "    wsl --import $Instance `"$BasePath`" `"$SnapshotFile`"" }
    else { Write-Host "    wsl --import $Instance <folder for the instance's disk> `"$SnapshotFile`"" }
    Write-Host "Delete the snapshot once you're happy with the upgrade: $SnapshotFile"
}
exit $code
