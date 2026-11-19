# Create a new WSL2 Ubuntu instance on Windows and install MedUI in it.
# Run from an ordinary PowerShell window, logged in as the Windows account that will use
# MedUI. NOT "Run as administrator": a WSL instance, .wslconfig and the keep-alive task all
# belong to the account that creates them.
#   powershell.exe -NoExit -ExecutionPolicy Bypass -File .\create_medui_wsl2.ps1
# Only the firewall rules that open SSH, or MedUI over HTTPS, to the network need an
# administrator. At those steps the script says what the rules permit and asks Y/n; on a yes
# it runs itself again with -FirewallOnly behind a Windows (UAC) prompt; that run creates the
# rules and nothing else.
# See scripts/windows/README.md. Existing WSL instances are never changed unless you choose to delete one.

param(
    [switch]$FirewallOnly,     # administrator-only mode: create the firewall rules asked for, then exit
    [string]$Instance,         # with -FirewallOnly: the WSL instance the rules are for
    [int]$Port,                # with -FirewallOnly: the SSH port to open
    [int]$HttpsPort,           # with -FirewallOnly: MedUI's HTTPS port to open, for workstations
    [int]$HttpPort             # with -FirewallOnly and -HttpsPort: the setup page's port (0: leave it closed)
)

$ErrorActionPreference = 'Stop'

# --- DEFAULTS (each can be overridden interactively) ---
$BaseDistro     = "Ubuntu-24.04"       # image from 'wsl --list --online'
$DefaultName    = "medui"              # name of the NEW instance
$DefaultUser    = "medui"
$RepoUrl        = "https://github.com/medui-au/medui.git"
$DemoRepoUrl    = "https://github.com/medui-au/medui_demodata.git"   # a demo's invented databases
$DefaultBranch  = "main"
$AppDirName     = "medui_os"
$DefaultPorts   = [ordered]@{ App = 5005; Database = 55432; OCR = 5707 }
$PubKeyDefault  = Join-Path $env:USERPROFILE ".ssh\id_ed25519.pub"
$WslVmCreatorId = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'   # fixed GUID for the WSL VM (Hyper-V firewall)
# -------------------------------------------------------

# Pipe plain UTF-8 (no BOM) into wsl.exe
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$IsAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# --- Helpers ---
function Wsl-Root {
    # Run a bash command as root in the new instance; throw on failure.
    param([Parameter(Mandatory)][string]$Cmd)
    & wsl.exe -d $DistroName -u root bash -c $Cmd
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed (exit $LASTEXITCODE): $Cmd" }
}

function Wsl-RootStdin {
    # Same, but feeds $Text on stdin (keeps secrets off the command line).
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text, [Parameter(Mandatory)][string]$Cmd)
    $Text | & wsl.exe -d $DistroName -u root bash -c $Cmd
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed (exit $LASTEXITCODE)." }
}

function Wsl-Script {
    # Run a bash script as root, sent on stdin. Windows PowerShell 5.1 mangles some
    # characters in arguments to native programs (a '>&2' broke one), so anything
    # beyond a simple command goes this way.
    param([Parameter(Mandatory)][string]$Script)
    Wsl-RootStdin -Text ($Script -replace "`r", "") -Cmd "tr -d '\r' | bash -s"
}

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

function Get-WslDistros { return @(Get-WslDistroInfo | ForEach-Object { $_.Name }) }

function Get-WslVersion {
    # The installed WSL version, or $null if WSL is missing or too old to report one.
    $old = [Console]::OutputEncoding
    $out = $null
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::Unicode
        $out = & wsl.exe --version
        if ($LASTEXITCODE -ne 0) { $out = $null }
    } catch {
        $out = $null
    } finally {
        [Console]::OutputEncoding = $old
    }
    foreach ($line in @($out)) {
        $clean = ("$line" -replace "`0", '').Trim()
        if ($clean -match '^[^:]+:\s*(\d+\.\d+\.\d+(\.\d+)?)\s*$') { return [version]$Matches[1] }
    }
    return $null
}

function Test-PendingReboot {
    $keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
    foreach ($k in $keys) { if (Test-Path $k) { return $true } }
    return $false
}

function Test-PortBusy([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Read-Port([string]$What, [int]$Default, [int[]]$Taken, [int]$Min = 1024) {
    # Mirrored networking shares one network stack with Windows: the port must be free here too.
    $suggest = $Default
    while ((Test-PortBusy $suggest) -or ($Taken -contains $suggest)) { $suggest++ }
    if ($suggest -ne $Default) { Write-Host "[!] Port $Default is in use on this PC; suggesting $suggest for $What." -ForegroundColor Yellow }
    while ($true) {
        $in = Read-Host "Port for $What [$suggest]"
        $p = if ([string]::IsNullOrWhiteSpace($in)) { $suggest } else { $in }
        if ($p -notmatch '^\d+$' -or [int]$p -lt $Min -or [int]$p -gt 65535) { Write-Host "[!] Enter a port from $Min to 65535." -ForegroundColor Yellow; continue }
        if ((Test-PortBusy ([int]$p)) -or ($Taken -contains [int]$p)) { Write-Host "[!] Port $p is in use. Pick another." -ForegroundColor Yellow; continue }
        return [int]$p
    }
}

function ConvertTo-PlainText([System.Security.SecureString]$Secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Test-GitHubAccess([string]$Token, [string]$Branch, [string]$Repo = $RepoUrl) {
    # Ask GitHub's API whether this token (or none) can read the repository and the branch,
    # before anything is installed. Returns ok, bad-token, no-access, needs-token,
    # no-branch or unreachable. The token goes only in a request header.
    if ($Repo -match 'github\.com[/:]([^/]+)/([^/]+?)(\.git)?$') {
        $api = "https://api.github.com/repos/$($Matches[1])/$($Matches[2])"
    } else { return 'unreachable' }
    $headers = @{ 'User-Agent' = 'medui-installer'; 'Accept' = 'application/vnd.github+json' }
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    foreach ($uri in @($api, "$api/branches/$Branch")) {
        try {
            $null = Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers $headers -TimeoutSec 20
        } catch {
            $response = $_.Exception.Response
            if (-not $response) { return 'unreachable' }
            $code = [int]$response.StatusCode
            if ($code -eq 401) { return 'bad-token' }
            if ($uri -ne $api -and $code -eq 404) { return 'no-branch' }
            if ($code -eq 403 -or $code -eq 404) { if ($Token) { return 'no-access' } else { return 'needs-token' } }
            return 'unreachable'
        }
    }
    return 'ok'
}

# Practice timezone: the menu offered, Windows' own zone translated, and forgiving input
# (a city, a state or a zone name). Always a place, never an offset: daylight saving then
# changes by itself. install.sh checks the final name again.
$TzMenu = [ordered]@{
    'Australia/Brisbane' = 'Brisbane     Queensland'
    'Australia/Sydney'   = 'Sydney       NSW, ACT'
    'Australia/Melbourne'= 'Melbourne    Victoria'
    'Australia/Hobart'   = 'Hobart       Tasmania'
    'Australia/Adelaide' = 'Adelaide     South Australia'
    'Australia/Darwin'   = 'Darwin       Northern Territory'
    'Australia/Perth'    = 'Perth        Western Australia'
}
$WindowsZones = @{
    'E. Australia Standard Time' = 'Australia/Brisbane'; 'AUS Eastern Standard Time' = 'Australia/Sydney'
    'Tasmania Standard Time' = 'Australia/Hobart'; 'Cen. Australia Standard Time' = 'Australia/Adelaide'
    'AUS Central Standard Time' = 'Australia/Darwin'; 'W. Australia Standard Time' = 'Australia/Perth'
    'Aus Central W. Standard Time' = 'Australia/Eucla'; 'Lord Howe Standard Time' = 'Australia/Lord_Howe'
    'Norfolk Standard Time' = 'Pacific/Norfolk'; 'New Zealand Standard Time' = 'Pacific/Auckland'
}
function Resolve-Zone([string]$Text) {
    $t = ($Text.Trim().ToLower() -replace '\s+', ' ')
    switch -Regex ($t) {
        '^(brisbane|qld|queensland)$'                 { return 'Australia/Brisbane' }
        '^(sydney|nsw|new south wales|act|canberra)$' { return 'Australia/Sydney' }
        '^(melbourne|vic|victoria)$'                  { return 'Australia/Melbourne' }
        '^(hobart|tas|tasmania)$'                     { return 'Australia/Hobart' }
        '^(adelaide|sa|south australia)$'             { return 'Australia/Adelaide' }
        '^(darwin|nt|northern territory)$'            { return 'Australia/Darwin' }
        '^(perth|wa|western australia)$'              { return 'Australia/Perth' }
    }
    # A zone name: give each part a capital, as zone names have (australia/lord_howe -> Australia/Lord_Howe).
    if ($t -match '^[a-z]+(/[a-z0-9_+-]+){1,2}$') {
        $known = @($TzMenu.Keys) + @($WindowsZones.Values) | Where-Object { $_.ToLower() -eq $t } | Select-Object -First 1
        if ($known) { return $known }
        return (($t -split '/') | ForEach-Object { ($_ -split '_' | ForEach-Object { if ($_) { $_.Substring(0,1).ToUpper() + $_.Substring(1) } }) -join '_' }) -join '/'
    }
    return $null
}
function Read-PracticeZone {
    $winId = [TimeZoneInfo]::Local.Id
    $detected = $WindowsZones[$winId]
    $default = if ($detected) { $detected } else { 'Australia/Brisbane' }
    $keys = @($TzMenu.Keys)
    $defKey = if ($keys -contains $default) { [string]([array]::IndexOf($keys, $default) + 1) } else { $default }
    while ($true) {
        if ($detected) { Write-Host "Practice timezone (detected from Windows: $winId):" }
        else { Write-Host "Practice timezone (Windows' '$winId' isn't one of these: Brisbane offered):" }
        for ($i = 0; $i -lt $keys.Count; $i++) {
            $mark = if ($keys[$i] -eq $default) { if ($detected) { '   <- detected' } else { '   <- offered' } } else { '' }
            Write-Host ("  {0}  {1}{2}" -f ($i + 1), $TzMenu[$keys[$i]], $mark)
        }
        Write-Host ("  {0}  Other (type a zone name, e.g. Australia/Lord_Howe)" -f ($keys.Count + 1))
        $pick = Read-Host "Choice [$defKey]"
        if ([string]::IsNullOrWhiteSpace($pick)) { $pick = $defKey }
        $n = 0
        if ([int]::TryParse($pick, [ref]$n) -and $n -ge 1 -and $n -le $keys.Count) { return $keys[$n - 1] }
        if ($n -eq $keys.Count + 1) { $pick = Read-Host "Zone name" }
        $zone = Resolve-Zone $pick
        if ($zone) { return $zone }
        Write-Host "[!] '$pick' isn't a timezone. Choose a number, or type a city or state (melbourne, vic, nsw...)." -ForegroundColor Yellow
    }
}

function New-RandomPassword([int]$Length = 24) {
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%^*-_=+'.ToCharArray()
    $bytes = New-Object byte[] $Length
    $rng = New-Object Security.Cryptography.RNGCryptoServiceProvider
    $rng.GetBytes($bytes); $rng.Dispose()
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Add-InboundRule([string]$Name, [int]$Port, [string]$Why) {
    # Windows Firewall (Private + Domain only) and, under mirrored networking, the Hyper-V firewall.
    Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port `
                        -Profile Private,Domain -Description $Why | Out-Null
    # Under mirrored networking the Hyper-V rule is the one that lets traffic into WSL, so it
    # carries the same Private/Domain limit. Older builds have no -Profiles: the rule then
    # applies on every network, and the message below says so.
    $scope = 'Private/Domain networks'
    $hv = Get-Command New-NetFirewallHyperVRule -ErrorAction SilentlyContinue
    if ($hv) {
        try {
            Get-NetFirewallHyperVRule -Name "$Name (Hyper-V)" -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
            $hvArgs = @{
                Name = "$Name (Hyper-V)"; DisplayName = "$Name (Hyper-V)"; Direction = 'Inbound'
                VMCreatorId = $WslVmCreatorId; Protocol = 'TCP'; LocalPorts = $Port
            }
            if ($hv.Parameters.ContainsKey('Profiles')) { $hvArgs['Profiles'] = 'Private', 'Domain' }
            else { $scope = 'ALL networks, Public included (this Windows build cannot limit the Hyper-V rule by profile)' }
            New-NetFirewallHyperVRule @hvArgs | Out-Null
        } catch {
            Write-Host "[!] Could not create the Hyper-V firewall rule: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Write-Host "[+] Firewall: inbound TCP $Port on $scope ($Name)." -ForegroundColor $(if ($scope -like 'ALL*') { 'Yellow' } else { 'Green' })
}

function Get-SshRuleName([string]$ForInstance, [int]$ForPort) { "WSL2 $ForInstance SSH (TCP $ForPort)" }

function Add-HttpsRules([string]$ForInstance, [int]$ForHttps, [int]$ForHttp) {
    # The same rule names as open_medui_https_port.ps1, so either script replaces the other's.
    Add-InboundRule "WSL2 $ForInstance MedUI HTTPS" $ForHttps "MedUI over HTTPS from the practice network (WSL2 instance '$ForInstance')."
    if ($ForHttp -gt 0) {
        Add-InboundRule "WSL2 $ForInstance MedUI setup page (HTTP)" $ForHttp "MedUI's setup page for workstations, and redirects to HTTPS (WSL2 instance '$ForInstance')."
    }
}

function Get-LanAddress {
    # This PC's IPv4 address on the network with the default gateway, or $null.
    try {
        $cfg = Get-NetIPConfiguration -ErrorAction Stop | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
        if ($cfg) { return [string](@($cfg.IPv4Address)[0].IPAddress) }
    } catch { }
    return $null
}

# --- Administrator-only mode: the firewall rule, nothing else ---
if ($FirewallOnly) {
    try {
        if (-not $IsAdmin) { throw "-FirewallOnly must be run as Administrator." }
        if ($Instance -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$') { throw "Invalid or missing -Instance." }
        if ($Port -lt 0 -or $Port -gt 65535 -or $HttpsPort -lt 0 -or $HttpsPort -gt 65535 -or $HttpPort -lt 0 -or $HttpPort -gt 65535) { throw "Invalid port." }
        if ($Port -eq 0 -and $HttpsPort -eq 0) { throw "Missing -Port (SSH) or -HttpsPort." }
        if ($Port -gt 0) { Add-InboundRule (Get-SshRuleName $Instance $Port) $Port "SSH into WSL2 instance '$Instance' (mirrored networking)." }
        if ($HttpsPort -gt 0) { Add-HttpsRules $Instance $HttpsPort $HttpPort }
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "[!] $($_.Exception.Message)" -ForegroundColor Red
        Read-Host "Press ENTER to close this window"
        exit 1
    }
    exit 0
}

# Elevated with another account's credentials, everything below would be built for THAT
# account: the instance, .wslconfig and the keep-alive task. Compare with the desktop's owner.
if ($IsAdmin) {
    $Me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $DesktopUser = $null
    try {
        $sessionId = (Get-Process -Id $PID).SessionId
        $shell = Get-CimInstance Win32_Process -Filter "Name='explorer.exe' AND SessionId=$sessionId" | Select-Object -First 1
        if ($shell) {
            $owner = Invoke-CimMethod -InputObject $shell -MethodName GetOwner
            if ($owner.User) { $DesktopUser = "$($owner.Domain)\$($owner.User)" }
        }
    } catch { }
    if ($DesktopUser -and $DesktopUser -ne $Me) {
        Write-Host "[!] This window runs as '$Me', but '$DesktopUser' is logged in to Windows." -ForegroundColor Red
        Write-Host "    MedUI would be installed for '$Me' and would not appear or start for '$DesktopUser'." -ForegroundColor Red
        Write-Host "    Close this window and run the script from an ordinary (not administrator) PowerShell." -ForegroundColor Red
        if ((Read-Host "Install for '$Me' anyway? (y/N)") -notmatch '^[yY]$') { exit 1 }
    }
}

# =========================================================
Write-Host "=== Preflight: Windows and WSL ===" -ForegroundColor Cyan
$MinWslVersion = [version]'2.4.4'    # 'wsl --install --name' needs roughly this version or later
$MinWinBuild   = 22621               # Windows 11 22H2: mirrored networking and the Hyper-V firewall

$WinBuild = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
if ($WinBuild -lt $MinWinBuild) {
    Write-Host "[!] Windows build $WinBuild is older than $MinWinBuild (Windows 11 22H2). Mirrored networking is not supported." -ForegroundColor Yellow
    Write-Host "    MedUI will still be reachable from this PC's browser, but SSH from the network will not work." -ForegroundColor Yellow
    if ((Read-Host "Continue anyway? (y/N)") -notmatch '^[yY]$') { exit 1 }
}

$WslVer = Get-WslVersion
if ($WslVer -and $WslVer -ge $MinWslVersion) {
    Write-Host "[+] WSL $WslVer is installed (minimum $MinWslVersion)." -ForegroundColor Green
} else {
    $WslState = if ($WslVer) { "version $WslVer, older than the required $MinWslVersion" } else { "not installed" }
    if (-not $WslVer -and -not $IsAdmin) {
        # Turning on the Windows features WSL needs is the one other job for an administrator.
        Write-Host "[!] WSL is not installed, and installing it needs an administrator." -ForegroundColor Yellow
        Write-Host "    Ask one to run this in an administrator PowerShell, then RESTART WINDOWS and run this script again:" -ForegroundColor Yellow
        Write-Host "      wsl --install --no-distribution" -ForegroundColor Yellow
        Read-Host -Prompt "`nPress ENTER to close this window"
        exit 1
    }
    Write-Host "[!] WSL is $WslState. Installing or updating it may require a REBOOT$(if (-not $IsAdmin) { ' and an administrator to approve a Windows prompt' })." -ForegroundColor Yellow
    if ((Read-Host "Install/update WSL now? (Y/n)") -match '^[nN]$') { exit 1 }
    if ($WslVer) { wsl.exe --update } else { wsl.exe --install --no-distribution }
    $WslVer = Get-WslVersion
    if (-not ($WslVer -and $WslVer -ge $MinWslVersion)) {
        Write-Host "[!] WSL is installed or updated but not usable yet. RESTART WINDOWS, then run this script again." -ForegroundColor Yellow
        Read-Host -Prompt "`nPress ENTER to close this window"
        exit 0
    }
    Write-Host "[+] WSL is now version $WslVer." -ForegroundColor Green
    if (Test-PendingReboot) { Write-Host "[!] Windows reports a pending reboot. If a later step fails, restart and run this again." -ForegroundColor Yellow }
}

# =========================================================
Write-Host "`n=== 0. Questions ===" -ForegroundColor Cyan

# Existing instances: listed, and deleted only when chosen and confirmed by typing the name.
$Info = @(Get-WslDistroInfo)
if ($Info.Count -gt 0) {
    Write-Host "Existing WSL instances:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $Info.Count; $i++) {
        $d = $Info[$i]
        $tag = if ($d.IsDefault) { '  [default]' } else { '' }
        Write-Host ("  {0}. {1,-24} {2,-9} WSL{3}{4}" -f ($i + 1), $d.Name, $d.State, $d.Version, $tag)
    }
    $Sel = Read-Host "Numbers to DELETE (e.g. 2,3), or press Enter to delete nothing"
    $ToDelete = @()
    foreach ($tok in ($Sel -split '[,\s]+' | Where-Object { $_ })) {
        if ($tok -notmatch '^\d+$' -or [int]$tok -lt 1 -or [int]$tok -gt $Info.Count) { throw "Invalid selection '$tok'." }
        $ToDelete += $Info[[int]$tok - 1]
    }
    foreach ($d in ($ToDelete | Sort-Object Name -Unique)) {
        Write-Host "[!] '$($d.Name)' will be PERMANENTLY deleted with ALL its data, including any MedUI database in it." -ForegroundColor Red
        if ($d.Name -match '^(docker-desktop|docker-desktop-data|rancher-desktop.*|podman-machine.*)$') {
            Write-Host "[!] '$($d.Name)' looks like a tool-managed instance; deleting it may break that tool." -ForegroundColor Yellow
        }
        $typed = Read-Host "Type the exact name '$($d.Name)' to confirm, or press Enter to skip"
        if ($typed -ceq $d.Name) {
            # The keep-alive task goes first: left running, its loop would start the instance again.
            try {
                $old = Get-ScheduledTask -TaskName "WSL2 $($d.Name) keep-alive" -ErrorAction SilentlyContinue
                if ($old) { $old | Stop-ScheduledTask; $old | Unregister-ScheduledTask -Confirm:$false }
            } catch { Write-Host "[!] Could not remove the task 'WSL2 $($d.Name) keep-alive' (an administrator may have created it): $($_.Exception.Message)" -ForegroundColor Yellow }
            wsl.exe --terminate $d.Name
            wsl.exe --unregister $d.Name
            if ($LASTEXITCODE -ne 0) { throw "Failed to unregister '$($d.Name)'." }
            Write-Host "[+] Deleted '$($d.Name)'." -ForegroundColor Green
        } else {
            Write-Host "[*] Skipped '$($d.Name)'." -ForegroundColor Yellow
        }
    }
}

# Live or demo. A demo has its own instance, folder and SQL Server with MedUI's invented demo
# databases (medui_demodata), and is never pointed at Best Practice: install.sh --demo.
Write-Host "Live: the practice's MedUI, reading its Best Practice database." -ForegroundColor Yellow
Write-Host "Demo: for demonstrations and training, with invented patients in its own SQL Server; never BP." -ForegroundColor Yellow
$Demo = (Read-Host "Install a live practice installation or a demo? (L/d)") -match '^[dD]'
if ($Demo) {
    $DefaultName  = "medui_demo"
    $AppDirName   = "medui_demo"
    $DefaultPorts = [ordered]@{ App = 5006; Database = 55433; OCR = 5708 }   # apart from a live instance's
    Write-Host "[+] Demo installation: instance, folder and ports of its own." -ForegroundColor Green
}

$Existing = Get-WslDistros
while ($true) {
    $DistroName = Read-Host "Name for the NEW WSL instance [$DefaultName]"
    if ([string]::IsNullOrWhiteSpace($DistroName)) { $DistroName = $DefaultName }
    if ($DistroName -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$') { Write-Host "[!] Use letters, digits, '_', '-' or '.' only." -ForegroundColor Yellow; continue }
    if ($Existing -contains $DistroName) { Write-Host "[!] '$DistroName' already exists and will not be touched. Pick another name." -ForegroundColor Yellow; continue }
    break
}

$NewUser = Read-Host "Linux username [$DefaultUser]"
if ([string]::IsNullOrWhiteSpace($NewUser)) { $NewUser = $DefaultUser }
if ($NewUser -cnotmatch '^[a-z_][a-z0-9_-]{0,31}$' -or $NewUser -eq 'root') { throw "Invalid username '$NewUser'." }

$GeneratedPassword = $false
$sec1 = Read-Host "Linux password for '$NewUser' (blank: generate one)" -AsSecureString
$UserPass = ConvertTo-PlainText $sec1
if ([string]::IsNullOrEmpty($UserPass)) {
    $UserPass = New-RandomPassword
    $GeneratedPassword = $true
} else {
    if ($UserPass -cne (ConvertTo-PlainText (Read-Host "Confirm password" -AsSecureString))) { throw "Passwords do not match." }
    if ($UserPass.Length -lt 12) { Write-Host "[!] Password is shorter than 12 characters." -ForegroundColor Yellow }
}

# MedUI ports: MedUI itself, its PostgreSQL and LiteParse OCR. All listen on localhost only.
$Ports = [ordered]@{}
foreach ($k in $DefaultPorts.Keys) { $Ports[$k] = Read-Port $k $DefaultPorts[$k] @($Ports.Values) }

$PracticeTz = Read-PracticeZone
Write-Host "[+] Practice timezone: $PracticeTz" -ForegroundColor Green

# Source: the repository and branch. A private repository needs a GitHub token with read access.
$Branch = Read-Host "Branch to install [$DefaultBranch]"
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = $DefaultBranch }
if ($Branch -notmatch '^[A-Za-z0-9._/-]+$') { throw "Invalid branch name '$Branch'." }
# Checked against GitHub now, so a token that didn't paste is found before anything is installed.
while ($true) {
    Write-Host "Paste the token with a right-click: Ctrl+V and Ctrl+Shift+V do not paste into this hidden prompt. Each character shows as one *." -ForegroundColor Yellow
    $TokenSec = Read-Host "GitHub token for a private repository (blank if the repository is public)" -AsSecureString
    $GitToken = (ConvertTo-PlainText $TokenSec).Trim()
    if ($GitToken) { Write-Host "Token received: $($GitToken.Length) characters." }
    $Access = Test-GitHubAccess $GitToken $Branch
    if ($Access -eq 'ok' -and $Demo) {
        $DemoAccess = Test-GitHubAccess $GitToken 'main' $DemoRepoUrl
        if ($DemoAccess -in @('bad-token', 'no-access', 'needs-token')) {
            Write-Host "[!] The demo data ($DemoRepoUrl) is private and this token can't read it: give the token read access to it too. Try again." -ForegroundColor Yellow
            continue
        }
    }
    if ($Access -eq 'ok') { Write-Host "[+] GitHub: the repository and branch '$Branch' are readable$(if ($Demo) { ', and the demo data' })." -ForegroundColor Green; break }
    if ($Access -eq 'unreachable') { Write-Host "[!] GitHub could not be checked from here; carrying on. The download in step 6 will show any problem." -ForegroundColor Yellow; break }
    if ($Access -eq 'no-branch') { throw "Branch '$Branch' was not found in $RepoUrl. Run the script again with the right branch." }
    $why = @{
        'bad-token'   = 'GitHub rejected the token: expired, mistyped, or not fully pasted.'
        'no-access'   = 'The token works but cannot read this repository: give it read access to its Contents.'
        'needs-token' = 'The repository is private: a token with read access is needed.'
    }[$Access]
    Write-Host "[!] $why Try again." -ForegroundColor Yellow
}

$WantSsh = (Read-Host "Set up SSH into the instance, for IT or a remote coding agent? (Y/n)") -notmatch '^[nN]$'
if ($WantSsh) {
    $DefaultSsh = if (Test-PortBusy 22) { 2222 } else { 22 }
    $SshPort = Read-Port "SSH" $DefaultSsh @($Ports.Values) 1
    $PubKeyPath = Read-Host "Public key file to authorise for SSH [$PubKeyDefault]"
    if ([string]::IsNullOrWhiteSpace($PubKeyPath)) { $PubKeyPath = $PubKeyDefault }
    $PubKey = $null
    if (Test-Path $PubKeyPath) {
        $PubKey = (Get-Content -Raw $PubKeyPath).Trim()
        if ($PubKey -notmatch '^(ssh-|ecdsa-|sk-)') { throw "'$PubKeyPath' does not look like an SSH public key." }
    } else {
        Write-Host "[!] No public key at '$PubKeyPath': password login only." -ForegroundColor Yellow
    }
}

# HTTPS for the practice's workstations. Not by default: until it is on, MedUI answers on this
# PC only. It is done last, after MedUI is installed and running, so a problem with it is
# reported without failing the installation.
$WantHttps = $false; $HttpsName = $null; $HttpsIp = $null
if ($WinBuild -lt $MinWinBuild) {
    Write-Host "HTTPS for workstations isn't offered: this Windows build has no mirrored networking, so other PCs can't reach the instance." -ForegroundColor Yellow
} else {
    Write-Host "MedUI will answer on this PC only (http://127.0.0.1:$($Ports.App)). Other PCs reach it over HTTPS, which the" -ForegroundColor Yellow
    Write-Host "scribe's microphone on those PCs needs too. It can also be turned on later: ./medui.sh https" -ForegroundColor Yellow
    $WantHttps = (Read-Host "Open MedUI to the practice's workstations over HTTPS? (y/N)") -match '^[yY]$'
}
if ($WantHttps) {
    $TakenPorts = @($Ports.Values); if ($WantSsh) { $TakenPorts += $SshPort }
    $HttpsPort = Read-Port "HTTPS" 443 $TakenPorts 1
    $HttpPort  = Read-Port "the setup page each workstation opens once (HTTP)" 80 ($TakenPorts + $HttpsPort) 1
    # MedUI's certificate is good only for the name and address given here. Changing them later
    # means a new MedUI root, installed on every workstation again.
    Write-Host "Workstations open MedUI by this PC's name or address. MedUI's certificate covers only what you give here:" -ForegroundColor Yellow
    Write-Host "changing it later means setting up every workstation again." -ForegroundColor Yellow
    $DefaultHttpsName = "$env:COMPUTERNAME".ToLower()
    while ($true) {
        $HttpsName = (Read-Host "Name workstations will type [$DefaultHttpsName]").Trim().ToLower()
        if ([string]::IsNullOrWhiteSpace($HttpsName)) { $HttpsName = $DefaultHttpsName }
        if ($HttpsName -match '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$') { break }
        Write-Host "[!] Use letters, digits, '.' and '-' only." -ForegroundColor Yellow
    }
    $DefaultHttpsIp = Get-LanAddress
    Write-Host "An address works where the name doesn't resolve, but only while it stays the same: a fixed address or a DHCP reservation." -ForegroundColor Yellow
    while ($true) {
        $HttpsIp = (Read-Host "This PC's address, or 'none' for the name only [$(if ($DefaultHttpsIp) { $DefaultHttpsIp } else { 'none' })]").Trim()
        if ([string]::IsNullOrWhiteSpace($HttpsIp)) { $HttpsIp = $DefaultHttpsIp }
        if (-not $HttpsIp -or $HttpsIp -match '^[nN]') { $HttpsIp = $null; break }
        if ($HttpsIp -match '^(\d{1,3}\.){3}\d{1,3}$') { break }
        Write-Host "[!] '$HttpsIp' isn't an IPv4 address." -ForegroundColor Yellow
    }
}
# By default WSL mounts the Windows drives (/mnt/c) and lets Linux start Windows programs.
# Anyone who gets into the instance, over SSH for one, then reaches this PC's files too.
Write-Host "WSL normally shows the Windows drives inside the instance (/mnt/c) and lets it start Windows programs." -ForegroundColor Yellow
$Isolate = (Read-Host "Turn both off, so the instance cannot reach this PC's files? (Y/n)") -notmatch '^[nN]$'
$InstallSqlcmd = $false   # a demo has no BP connection to test
if (-not $Demo) { $InstallSqlcmd = (Read-Host "Install Microsoft sqlcmd, to test the BP connection from the instance? (y/N)") -match '^[yY]$' }
Write-Host "WSL stops an instance when nothing is using it, which would stop MedUI." -ForegroundColor Yellow
$KeepAlive = (Read-Host "Create a scheduled task that starts '$DistroName' at your logon and keeps it running? (Y/n)") -notmatch '^[nN]$'
$KeepAliveTask = "WSL2 $DistroName keep-alive"

# =========================================================
Write-Host "`n=== 1. Plan ===" -ForegroundColor Cyan
Write-Host "New instance '$DistroName' from $BaseDistro, user '$NewUser'$(if ($Demo) { '. DEMO: SQL Server Express with the invented demo databases, no Best Practice' })." -ForegroundColor Green
Write-Host "MedUI from $RepoUrl ($Branch); ports: MedUI $($Ports.App), PostgreSQL $($Ports.Database), OCR $($Ports.OCR) (localhost only)." -ForegroundColor Green
Write-Host "Practice timezone: $PracticeTz." -ForegroundColor Green
Write-Host "SSH: $(if ($WantSsh) { "port $SshPort, $(if ($PubKey) { 'key only' } else { 'password' })" } else { 'no' }). Windows drives and programs: $(if ($Isolate) { 'off' } else { 'reachable' })." -ForegroundColor Green
Write-Host "HTTPS for workstations: $(if ($WantHttps) { "https://$HttpsName$(if ($HttpsPort -ne 443) { ":$HttpsPort" })$(if ($HttpsIp) { " and $HttpsIp" }); setup page on port $HttpPort" } else { 'no (this PC only)' })." -ForegroundColor Green
Write-Host "sqlcmd: $InstallSqlcmd. Keep-alive task: $KeepAlive. Other instances: not modified." -ForegroundColor Green
if ((Read-Host "Go ahead? (Y/n)") -match '^[nN]$') { exit 0 }

# =========================================================
Write-Host "`n=== 2. Mirrored networking (.wslconfig) ===" -ForegroundColor Cyan
$WslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"
$lines = New-Object System.Collections.Generic.List[string]
if (Test-Path $WslConfigPath) { (Get-Content $WslConfigPath) | ForEach-Object { $lines.Add($_) } }
$secIdx = -1
for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].Trim() -ieq '[wsl2]') { $secIdx = $i; break } }
if ($secIdx -lt 0) {
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1].Trim() -ne '') { $lines.Add('') }
    $lines.Add('[wsl2]'); $lines.Add('networkingMode=mirrored')
} else {
    $keyIdx = -1
    for ($i = $secIdx + 1; $i -lt $lines.Count -and $lines[$i].Trim() -notmatch '^\['; $i++) {
        if ($lines[$i] -match '^\s*networkingMode\s*=') { $keyIdx = $i; break }
    }
    if ($keyIdx -ge 0) { $lines[$keyIdx] = 'networkingMode=mirrored' } else { $lines.Insert($secIdx + 1, 'networkingMode=mirrored') }
}
$OriginalLines = if (Test-Path $WslConfigPath) { @(Get-Content $WslConfigPath) } else { @() }
if (($OriginalLines -join "`n") -ceq ($lines -join "`n")) {
    Write-Host "[+] networkingMode=mirrored already set." -ForegroundColor Green
} else {
    [System.IO.File]::WriteAllLines($WslConfigPath, $lines, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "[+] networkingMode=mirrored set in $WslConfigPath" -ForegroundColor Green
    Write-Host "[!] Applying it needs 'wsl --shutdown', which stops ALL running WSL instances (they are not modified)." -ForegroundColor Yellow
    if ((Read-Host "Run wsl --shutdown now? (Y/n)") -notmatch '^[nN]$') { wsl.exe --shutdown; Start-Sleep -Seconds 3 }
    else { Write-Host "[!] Skipped: mirrored mode applies after the next 'wsl --shutdown'." -ForegroundColor Yellow }
}

# =========================================================
Write-Host "`n=== 3. Installing '$DistroName' from $BaseDistro ===" -ForegroundColor Cyan
wsl.exe --install -d $BaseDistro --name $DistroName --no-launch
if ($LASTEXITCODE -ne 0) { throw "wsl --install failed. Run 'wsl --update' and retry; nothing existing was modified." }
if (-not ((Get-WslDistros) -contains $DistroName)) { throw "'$DistroName' is not registered after install. Check 'wsl --list --verbose'." }

# =========================================================
Write-Host "`n=== 4. User, root locked, systemd ===" -ForegroundColor Cyan
Wsl-Root "id -u $NewUser >/dev/null 2>&1 || useradd -m -s /bin/bash $NewUser"
Wsl-RootStdin -Text "${NewUser}:${UserPass}" -Cmd "tr -d '\r' | chpasswd"
Wsl-Root "usermod -aG sudo $NewUser && passwd -l root >/dev/null"
$WslConf = "[user]`ndefault=$NewUser`n`n[boot]`nsystemd=true`n"
if ($Isolate) { $WslConf += "`n[automount]`nenabled=false`n`n[interop]`nenabled=false`nappendWindowsPath=false`n" }
Wsl-RootStdin -Text $WslConf -Cmd "tr -d '\r' > /etc/wsl.conf"
wsl.exe --terminate $DistroName      # restart so systemd comes up for the remaining steps
Start-Sleep -Seconds 2
Wsl-Script @'
for i in $(seq 1 30); do [ -d /run/systemd/system ] && exit 0; sleep 1; done
echo 'systemd did not start' >&2
exit 1
'@
Write-Host "[+] '$NewUser' has sudo; root password locked; systemd running$(if ($Isolate) { '; Windows drives and programs off' })." -ForegroundColor Green

# =========================================================
Write-Host "`n=== 5. System packages: Docker Engine, Compose, Buildx, git ===" -ForegroundColor Cyan
$pkgs = "ca-certificates curl git docker.io docker-compose-v2 docker-buildx"
if ($WantSsh) { $pkgs += " openssh-server fail2ban" }
# Some networks hand out IPv6 addresses that don't actually connect: apt then retries every
# download over IPv4 and crawls for many minutes with no output. Test it, and use IPv4 for
# apt if IPv6 doesn't work. apt shows its progress, and waits (up to 10 minutes, saying so)
# if Ubuntu's own first-boot update holds the package lock.
$AptScript = @'
set -euo pipefail
if ! curl -6 -s -m 5 -o /dev/null http://archive.ubuntu.com/ubuntu/ 2>/dev/null; then
  echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4
  echo "[i] IPv6 doesn't connect from this instance: package downloads use IPv4."
fi
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=600 update -q
apt-get -o DPkg::Lock::Timeout=600 install -y -q @@PKGS@@
'@
Wsl-Script ($AptScript.Replace('@@PKGS@@', $pkgs))
Wsl-Root "systemctl enable --now docker && usermod -aG docker $NewUser"
Write-Host "[+] Docker running; '$NewUser' in the docker group." -ForegroundColor Green

if ($InstallSqlcmd) {
    $OdbcScript = @'
set -euo pipefail
. /etc/os-release
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -sSL -o "$tmp/packages-microsoft-prod.deb" "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb"
dpkg -i "$tmp/packages-microsoft-prod.deb" >/dev/null
apt-get -o DPkg::Lock::Timeout=600 update -q
ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y -q msodbcsql18 mssql-tools18
echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' > /etc/profile.d/mssql-tools18.sh
'@
    Wsl-RootStdin -Text ($OdbcScript -replace "`r", "") -Cmd "tr -d '\r' | bash -s"
    Write-Host "[+] sqlcmd installed (/opt/mssql-tools18/bin). Driver 18 encrypts by default: add -C for a self-signed BP server." -ForegroundColor Green
}

# =========================================================
Write-Host "`n=== 6. Downloading MedUI ($Branch) ===" -ForegroundColor Cyan
$AppDir = "/home/$NewUser/$AppDirName"
# Runs as the new user. The token (if any) arrives on stdin and is used only through a
# temporary GIT_ASKPASS helper for this one clone: never on a command line, never stored.
$CloneScript = @'
set -euo pipefail
IFS= read -r TOKEN || true
TOKEN="${TOKEN%$'\r'}"            # PowerShell's pipe may add a carriage return
APP="$HOME/@@DIR@@"
[ -e "$APP" ] && { echo "$APP already exists; not touching it." >&2; exit 1; }
ask=$(mktemp); trap 'rm -f "$ask"' EXIT; chmod 700 "$ask"
printf '#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) printf "%%s\\n" "$GIT_TOKEN" ;; esac\n' > "$ask"
if [ -n "$TOKEN" ]; then
  GIT_TOKEN="$TOKEN" GIT_ASKPASS="$ask" GIT_TERMINAL_PROMPT=0 git clone --branch @@BRANCH@@ @@REPO@@ "$APP"
else
  GIT_TERMINAL_PROMPT=0 git clone --branch @@BRANCH@@ @@REPO@@ "$APP"
fi
git -C "$APP" log -1 --format='Version: %h %s'
if [ -n "@@DEMOREPO@@" ]; then   # a demo: its invented databases, with the same token
  if [ -n "$TOKEN" ]; then
    GIT_TOKEN="$TOKEN" GIT_ASKPASS="$ask" GIT_TERMINAL_PROMPT=0 git clone --quiet @@DEMOREPO@@ "$APP/demodata"
  else
    GIT_TERMINAL_PROMPT=0 git clone --quiet @@DEMOREPO@@ "$APP/demodata"
  fi
  git -C "$APP/demodata" log -1 --format='Demo data: %h %ad' --date=short
fi
'@
$CloneScript = $CloneScript.Replace('@@DIR@@', $AppDirName).Replace('@@BRANCH@@', $Branch).Replace('@@REPO@@', $RepoUrl).Replace('@@DEMOREPO@@', $(if ($Demo) { $DemoRepoUrl } else { '' })) -replace "`r", ""
# The script goes to a file first, so that stdin is free to carry the token.
Wsl-RootStdin -Text $CloneScript -Cmd "tr -d '\r' > /tmp/clone_medui.sh && chmod 644 /tmp/clone_medui.sh"
Wsl-RootStdin -Text $GitToken -Cmd "runuser -u $NewUser -- env HOME=/home/$NewUser bash /tmp/clone_medui.sh; rc=`$?; rm -f /tmp/clone_medui.sh; exit `$rc"
$GitToken = $null
# Checked directly, not through the exit code above: from Windows PowerShell 5.1 a failed
# clone came back as success once, and step 7 then failed with a confusing message.
& wsl.exe -d $DistroName -u root -e test -f "$AppDir/install.sh"
if ($LASTEXITCODE -ne 0) { throw "The download failed: $AppDir/install.sh is missing. The git message above says why." }
Write-Host "[+] Cloned to $AppDir" -ForegroundColor Green

# =========================================================
Write-Host "`n=== 7. Installing MedUI (install.sh) ===" -ForegroundColor Cyan
Write-Host "The OCR build takes several minutes. You will be asked for a MedUI administrator username and password." -ForegroundColor Yellow
$DemoArgs = @()
if ($Demo) {
    $DemoArgs = @('--demo')
    Write-Host "A demo also asks you to accept Microsoft's SQL Server licence terms, and for a password the demo users share." -ForegroundColor Yellow
}
# As the user, in this window (so the administrator prompts work). Docker and packages are
# already in place, so install.sh needs no sudo here.
& wsl.exe -d $DistroName -u $NewUser --cd $AppDir -- ./install.sh --yes --no-apt `
    --app-port $($Ports.App) --db-port $($Ports.Database) --ocr-port $($Ports.OCR) --timezone $PracticeTz @DemoArgs
if ($LASTEXITCODE -ne 0) { throw "install.sh failed (exit $LASTEXITCODE). Its output above says which step." }

# =========================================================
if ($WantSsh) {
    Write-Host "`n=== 8. SSH ===" -ForegroundColor Cyan
    if ($PubKey) {
        $setupKeys = "install -d -m 700 -o $NewUser -g $NewUser /home/$NewUser/.ssh && " +
                     "tr -d '\r' > /home/$NewUser/.ssh/authorized_keys && " +
                     "chmod 600 /home/$NewUser/.ssh/authorized_keys && chown ${NewUser}:${NewUser} /home/$NewUser/.ssh/authorized_keys"
        Wsl-RootStdin -Text ($PubKey + "`n") -Cmd $setupKeys
    }
    # With a key installed, passwords are refused: the Linux password also gives sudo, and
    # this port is open to the network. Without a key, password login is the only way in.
    $SshPasswords = if ($PubKey) { 'no' } else { 'yes' }
    $SshdDropIn = @"
# Managed by create_medui_wsl2.ps1
Port $SshPort
PermitRootLogin no
AllowUsers $NewUser
PasswordAuthentication $SshPasswords
PubkeyAuthentication yes
PermitEmptyPasswords no
KbdInteractiveAuthentication no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding local
ClientAliveInterval 300
ClientAliveCountMax 2
"@
    Wsl-Root "mkdir -p /run/sshd /etc/ssh/sshd_config.d"
    Wsl-RootStdin -Text ($SshdDropIn -replace "`r", "") -Cmd "tr -d '\r' > /etc/ssh/sshd_config.d/99-hardening.conf"
    # Ubuntu 24.04's socket activation ignores 'Port': use the plain service.
    Wsl-Script @'
set -e
grep -qE '^\s*Include\s+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config || sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' /etc/ssh/sshd_config
ssh-keygen -A >/dev/null
sshd -t
systemctl disable --now ssh.socket 2>/dev/null || true
systemctl enable ssh >/dev/null 2>&1
systemctl restart ssh
'@
    $F2b = "[DEFAULT]`nbantime  = 1h`nfindtime = 10m`nmaxretry = 4`nbackend  = systemd`n`n[sshd]`nenabled = true`nport    = $SshPort`n"
    Wsl-RootStdin -Text $F2b -Cmd "tr -d '\r' > /etc/fail2ban/jail.local"
    Wsl-Root "systemctl enable fail2ban >/dev/null 2>&1 && systemctl restart fail2ban"
    # The firewall rule is the only step that needs an administrator. Not elevated: run this
    # script again with -FirewallOnly behind a UAC prompt, and wait for it.
    $RuleOk = $false
    if ($IsAdmin) {
        Add-InboundRule (Get-SshRuleName $DistroName $SshPort) $SshPort "SSH into WSL2 instance '$DistroName' (mirrored networking)."
        $RuleOk = $true
    } else {
        # Explain first and wait for an answer: the Windows prompt appears only after a yes, so
        # there is time to read what it is for.
        Write-Host ""
        Write-Host "    Opening SSH to the practice network needs administrator approval." -ForegroundColor Yellow
        Write-Host "    Why:  SSH works from this PC already. For IT, or a coding agent on another computer," -ForegroundColor Yellow
        Write-Host "          to reach it, Windows Firewall must allow it in." -ForegroundColor Yellow
        Write-Host "    What you would permit: one inbound rule for TCP port $SshPort, on Private and Domain" -ForegroundColor Yellow
        Write-Host "          networks only (never Public), in Windows Firewall and the Hyper-V firewall." -ForegroundColor Yellow
        Write-Host "          The approved window runs this script again only to create that rule, then closes." -ForegroundColor Yellow
        Write-Host "          Nothing else is done as administrator." -ForegroundColor Yellow
        Write-Host "    No:   SSH stays reachable from this PC only. The rest of the install is the same," -ForegroundColor Yellow
        Write-Host "          and the rule can be added later (the command is shown)." -ForegroundColor Yellow
        $fwArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -FirewallOnly -Instance $DistroName -Port $SshPort"
        $askFw = (Read-Host "`nOpen SSH port $SshPort to the practice network? Windows asks for approval next. (Y/n)") -notmatch '^[nN]$'
        if ($askFw) {
            try {
                $fw = Start-Process powershell.exe -Verb RunAs -ArgumentList $fwArgs -Wait -PassThru
                $RuleOk = ($fw.ExitCode -eq 0)
            } catch { }
        }
        if ($RuleOk) {
            Write-Host "[+] Firewall rule created by the administrator." -ForegroundColor Green
        } else {
            Write-Host "[!] No firewall rule: SSH works from this PC only. To open it later, an administrator runs:" -ForegroundColor Yellow
            Write-Host "      powershell.exe $fwArgs" -ForegroundColor Yellow
        }
    }
    Write-Host "[+] SSH on port $SshPort ($(if ($PubKey) { 'key only; passwords refused' } else { 'password; no key installed' })), fail2ban active." -ForegroundColor Green
}

# =========================================================
if ($KeepAlive) {
    Write-Host "`n=== 9. Keep-alive scheduled task ===" -ForegroundColor Cyan
    # Two layers, because a task that only starts at logon stays dead once anything ends it:
    #  - a loop, so the instance comes back within seconds if wsl.exe exits (a 'wsl --shutdown',
    #    a WSL update);
    #  - a second trigger every 5 minutes, so the task itself comes back if it is ended.
    #    While it is running, IgnoreNew makes that trigger do nothing.
    # To stop MedUI on purpose, end this task first: otherwise the loop starts the instance again.
    $taskArgs = "-NoProfile -WindowStyle Hidden -Command `"while (`$true) { wsl.exe -d $DistroName --exec /bin/sleep infinity; Start-Sleep -Seconds 10 }`""
    $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArgs
    $trigger  = @(
        (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"),
        (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5))
    )
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    $principalTask = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    # MedUI is already installed by now: a task that can't be created is reported, not fatal.
    try {
        $old = Get-ScheduledTask -TaskName $KeepAliveTask -ErrorAction SilentlyContinue
        if ($old) { $old | Stop-ScheduledTask; $old | Unregister-ScheduledTask -Confirm:$false }
        Register-ScheduledTask -TaskName $KeepAliveTask -Action $action -Trigger $trigger -Settings $settings -Principal $principalTask `
            -Description "Starts WSL2 instance '$DistroName' at logon and keeps it running, so MedUI stays available." | Out-Null
        Start-ScheduledTask -TaskName $KeepAliveTask
        Write-Host "[+] Task '$KeepAliveTask' created and started (at logon of $env:USERDOMAIN\$env:USERNAME; checked every 5 minutes)." -ForegroundColor Green
        Write-Host "    It runs while $env:USERNAME is signed in to Windows: signing out stops the instance, and MedUI with it." -ForegroundColor Yellow
    } catch {
        $KeepAlive = $false
        Write-Host "[!] Could not create the keep-alive task: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "    MedUI is installed, but WSL will stop the instance when nothing is using it." -ForegroundColor Yellow
    }
}

# =========================================================
$HttpsOk = $false; $HttpsRuleOk = $false
$HttpsUrl = "https://$HttpsName$(if ($HttpsPort -ne 443) { ":$HttpsPort" })"
$SetupUrl = "http://$HttpsName$(if ($HttpPort -ne 80) { ":$HttpPort" })"
if ($WantHttps) {
    Write-Host "`n=== 10. HTTPS for workstations ===" -ForegroundColor Cyan
    # MedUI is installed and running by now: install.sh again, to add HTTPS only. A failure
    # here is reported and the installation stands.
    $HttpsArgs = @('--https', '--https-port', "$HttpsPort", '--http-port', "$HttpPort", '--https-name', $HttpsName)
    if ($HttpsIp) { $HttpsArgs += @('--https-ip', $HttpsIp) }
    & wsl.exe -d $DistroName -u $NewUser --cd $AppDir -- ./install.sh --yes --no-apt @HttpsArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] HTTPS was not set up (install.sh exit $LASTEXITCODE; its output above says which step)." -ForegroundColor Yellow
        Write-Host "    MedUI itself is installed and works on this PC. Try again later, in the instance: ./medui.sh https" -ForegroundColor Yellow
    } else {
        $HttpsOk = $true
        $fwHttpsArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -FirewallOnly -Instance $DistroName -HttpsPort $HttpsPort -HttpPort $HttpPort"
        if ($IsAdmin) {
            Add-HttpsRules $DistroName $HttpsPort $HttpPort
            $HttpsRuleOk = $true
        } else {
            Write-Host ""
            Write-Host "    Letting workstations reach MedUI needs administrator approval." -ForegroundColor Yellow
            Write-Host "    Why:  HTTPS works from this PC already. For other PCs, Windows Firewall must allow it in." -ForegroundColor Yellow
            Write-Host "    What you would permit: inbound TCP port $HttpsPort (MedUI over HTTPS) and port $HttpPort (the setup" -ForegroundColor Yellow
            Write-Host "          page a workstation opens once), on Private and Domain networks only (never Public)," -ForegroundColor Yellow
            Write-Host "          in Windows Firewall and the Hyper-V firewall. The approved window runs this script" -ForegroundColor Yellow
            Write-Host "          again only to create those rules, then closes. Nothing else is done as administrator." -ForegroundColor Yellow
            Write-Host "    No:   MedUI stays reachable from this PC only. The rules can be added later (the command is shown)." -ForegroundColor Yellow
            if ((Read-Host "`nOpen ports $HttpsPort and $HttpPort to the practice network? Windows asks for approval next. (Y/n)") -notmatch '^[nN]$') {
                try {
                    $fw = Start-Process powershell.exe -Verb RunAs -ArgumentList $fwHttpsArgs -Wait -PassThru
                    $HttpsRuleOk = ($fw.ExitCode -eq 0)
                } catch { }
            }
        }
        if ($HttpsRuleOk) {
            Write-Host "[+] Firewall rules for HTTPS created." -ForegroundColor Green
            $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -ExpandProperty NetworkCategory -Unique)
            if ($profiles -contains 'Public' -and -not ($profiles -contains 'Private' -or $profiles -contains 'DomainAuthenticated')) {
                Write-Host "[!] This PC's network is set to Public, where the rules don't apply. Set the practice network to" -ForegroundColor Yellow
                Write-Host "    Private (Settings > Network) or ask IT; MedUI stays unreachable from other PCs until then." -ForegroundColor Yellow
            }
        } else {
            Write-Host "[!] No firewall rules: MedUI over HTTPS works from this PC only. To open it later, an administrator runs:" -ForegroundColor Yellow
            Write-Host "      powershell.exe $fwHttpsArgs" -ForegroundColor Yellow
        }
    }
}

# =========================================================
Write-Host "`n=== $(if ($WantHttps) { '11' } else { '10' }). Check ===" -ForegroundColor Cyan
$CheckScript = "systemctl is-active docker$(if ($WantSsh) { ' ssh fail2ban' })`n" +
               "echo -n 'MedUI health: '; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$($Ports.App)/health; echo`n"
$CheckScript | & wsl.exe -d $DistroName -u root bash -c "tr -d '\r' | bash -s"
$FromWindows = try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$($Ports.App)/health").StatusCode } catch { "no answer" }
Write-Host "MedUI health from Windows: $FromWindows" -ForegroundColor $(if ($FromWindows -eq 200) { 'Green' } else { 'Yellow' })

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host " MedUI $(if ($Demo) { 'DEMO ' })installed in WSL2" -ForegroundColor Green
Write-Host " Open          : http://127.0.0.1:$($Ports.App)/  (this PC; log in as $(if ($Demo) { 'a demo user, e.g. Dr Imogen Thistlewood, or ' })the administrator you created)" -ForegroundColor Green
if ($HttpsOk) {
    Write-Host " Workstations  : $(if ($HttpsRuleOk) { "open $SetupUrl once on each PC (it sets the PC up to trust MedUI), then $HttpsUrl" } else { "$HttpsUrl, from this PC only until the firewall rules are added (command above)" })" -ForegroundColor Green
} elseif ($WantHttps) {
    Write-Host " Workstations  : HTTPS was NOT set up (see step 10 above). Later, in the instance: ./medui.sh https" -ForegroundColor Yellow
} else {
    Write-Host " Workstations  : not opened. Later, in the instance: ./medui.sh https" -ForegroundColor Green
}
Write-Host " Instance      : $DistroName  (wsl -d $DistroName)   other instances not modified" -ForegroundColor Green
Write-Host " MedUI folder  : $AppDir   (re-run ./install.sh there any time; it keeps your data)" -ForegroundColor Green
Write-Host " Linux user    : $NewUser (sudo; root locked)" -ForegroundColor Green
if ($WantSsh) { Write-Host " SSH           : ssh -p $SshPort $NewUser@127.0.0.1   ($(if ($RuleOk) { "network: this PC's IP" } else { 'this PC only: no firewall rule' }); $(if ($PubKey) { 'key only' } else { 'password' }))" -ForegroundColor Green }
Write-Host " Keep-alive    : $(if ($KeepAlive) { "task '$KeepAliveTask'" } else { 'none: WSL stops the idle instance, and MedUI with it' })" -ForegroundColor Green
if ($KeepAlive) { Write-Host " Stop MedUI    : Stop-ScheduledTask -TaskName '$KeepAliveTask'; wsl --terminate $DistroName   (the task first, or it starts the instance again)" -ForegroundColor Green }
if ($Demo) { Write-Host " Next          : never point this demo at Best Practice. Dates up to today: ./medui.sh demo refresh" -ForegroundColor Green }
else { Write-Host " Next          : BP connection$(if (-not $HttpsOk) { ', HTTPS' }), AI: ./medui.sh in the MedUI folder opens a menu; see also the end of install.sh's output" -ForegroundColor Green }
Write-Host "=========================================================" -ForegroundColor Green
if ($GeneratedPassword) {
    Write-Host "`nGenerated Linux password for '$NewUser' (shown once, store it now):" -ForegroundColor Yellow
    Write-Host "  $UserPass" -ForegroundColor Yellow
}
$UserPass = $null
Read-Host -Prompt "`nFinished. Press ENTER to close this window"
