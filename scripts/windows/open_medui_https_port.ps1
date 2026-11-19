# Let workstations on the practice network reach MedUI's HTTPS port, and the setup page they
# open first (plain HTTP), in a WSL2 instance.
# Run on the computer that hosts MedUI, from an elevated PowerShell (Run as administrator):
#   powershell.exe -ExecutionPolicy Bypass -File .\open_medui_https_port.ps1 [-Instance medui] [-Port 443] [-HttpPort 80]
# Opens inbound TCP on Private and Domain networks only (never Public), in Windows Firewall
# and, under mirrored networking, the Hyper-V firewall. See docs/https.md.

param(
    [string]$Instance = "medui",
    [int]$Port = 443,
    [int]$HttpPort = 80       # the setup page (install.sh --http-port); 0 to leave it closed
)

$ErrorActionPreference = 'Stop'
$WslVmCreatorId = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'   # fixed GUID for the WSL VM (Hyper-V firewall)

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must be run as Administrator."
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

$RuleName = "WSL2 $Instance MedUI HTTPS"
Add-InboundRule $RuleName $Port "MedUI over HTTPS from the practice network (WSL2 instance '$Instance')."
$HttpRuleName = "WSL2 $Instance MedUI setup page (HTTP)"
if ($HttpPort -gt 0) {
    Add-InboundRule $HttpRuleName $HttpPort "MedUI's setup page for workstations, and redirects to HTTPS (WSL2 instance '$Instance')."
}

$profiles = Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory -Unique
if ($profiles -contains 'Public' -and -not ($profiles -contains 'Private' -or $profiles -contains 'DomainAuthenticated')) {
    Write-Host "[!] This PC's network is set to Public, where the rule doesn't apply. Set the practice network" -ForegroundColor Yellow
    Write-Host "    to Private (Settings > Network) or ask IT; MedUI stays unreachable from other PCs until then." -ForegroundColor Yellow
}

Write-Host "`nTo remove it later:"
Write-Host "    Get-NetFirewallRule -DisplayName '$RuleName' | Remove-NetFirewallRule"
Write-Host "    Get-NetFirewallHyperVRule -Name '$RuleName (Hyper-V)' | Remove-NetFirewallHyperVRule"
if ($HttpPort -gt 0) {
    Write-Host "    Get-NetFirewallRule -DisplayName '$HttpRuleName' | Remove-NetFirewallRule"
    Write-Host "    Get-NetFirewallHyperVRule -Name '$HttpRuleName (Hyper-V)' | Remove-NetFirewallHyperVRule"
}
