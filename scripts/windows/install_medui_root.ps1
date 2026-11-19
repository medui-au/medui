# Make this workstation trust MedUI's HTTPS root (medui-root.cer, made by install.sh --https).
# For PCs outside a Windows domain; in a domain, use Group Policy instead (docs/https.md).
#   powershell.exe -ExecutionPolicy Bypass -File .\install_medui_root.ps1 -Path \\server\share\medui-root.cer
# Whole PC (all users): run as administrator. Only you: add -CurrentUser (no administrator needed).
# It shows the root and what it may vouch for, and refuses a root without a name restriction.

param(
    [Parameter(Mandatory)][string]$Path,
    [switch]$CurrentUser
)

$ErrorActionPreference = 'Stop'
$NameConstraintsOid = '2.5.29.30'

if (-not (Test-Path $Path)) { throw "No file at $Path." }
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 (Resolve-Path $Path).Path

$basic = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.19' }
$nc    = $cert.Extensions | Where-Object { $_.Oid.Value -eq $NameConstraintsOid }
if (-not $basic -or -not $basic.CertificateAuthority) { throw "This isn't a root certificate (not a CA). Nothing was installed." }
if (-not $nc) {
    throw "This root has no name restriction, so it could vouch for any website. MedUI's root always has one. Nothing was installed."
}
$sha256 = ([System.BitConverter]::ToString(
    [System.Security.Cryptography.SHA256]::Create().ComputeHash($cert.RawData))) -replace '-', ''

Write-Host "`n=== MedUI HTTPS root ===" -ForegroundColor Cyan
Write-Host "    Subject      : $($cert.Subject)"
Write-Host "    Valid until  : $($cert.NotAfter.ToString('yyyy-MM-dd'))"
Write-Host "    Thumbprint   : $($cert.Thumbprint)   (SHA-1, as install.sh printed it)"
Write-Host "    SHA-256      : $sha256"
Write-Host "    May vouch for only:"
$nc.Format($true) -split "`r?`n" | Where-Object { $_ -match '\S' } | ForEach-Object { Write-Host "        $_" }

if ($CurrentUser) { $store = 'Cert:\CurrentUser\Root'; $who = 'your Windows account' }
else {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Trusting it for the whole PC needs an elevated PowerShell (or add -CurrentUser for your account only)."
    }
    $store = 'Cert:\LocalMachine\Root'; $who = 'every user of this PC'
}
if (Test-Path "$store\$($cert.Thumbprint)") {
    Write-Host "`n[+] Already trusted for $who." -ForegroundColor Green
    exit 0
}
Write-Host "`nCompare the thumbprint with the one shown on the MedUI computer before you go on."
if ((Read-Host "Trust this root for ${who}? (y/N)") -notmatch '^[yY]$') { Write-Host "Nothing was installed."; exit 1 }

Import-Certificate -FilePath (Resolve-Path $Path).Path -CertStoreLocation $store | Out-Null
Write-Host "[+] Trusted for $who. Chrome and Edge use it straight away (restart them if open)." -ForegroundColor Green
Write-Host "    Firefox: set security.enterprise_roots.enabled to true in about:config, or import the root"
Write-Host "    in Firefox's own settings (Privacy & Security > Certificates)."
Write-Host "`nTo remove it later:"
Write-Host "    Remove-Item '$store\$($cert.Thumbprint)'"
