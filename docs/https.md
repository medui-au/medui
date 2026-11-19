# HTTPS for workstations

Notes for the practice's IT provider. MedUI runs on one computer in the practice. On that
computer it is at `http://127.0.0.1:5005`, which browsers already treat as secure. Other
workstations need HTTPS: browsers allow the microphone (dictation and the scribe) and
secure session cookies only on a trusted HTTPS page.

`./install.sh --https` puts [Caddy](https://caddyserver.com/), a web server, in front of
MedUI on port 443, with a small setup page on port 80 (below). MedUI's own ports (5005,
PostgreSQL, OCR) stay on 127.0.0.1; only ports 443 and 80 face the practice network. It also sets `SESSION_COOKIE_SECURE=true` and
`TRUSTED_PROXIES=1`, so MedUI records each workstation's own address, not the proxy's.

## Choosing a certificate

In order of preference:

1. **The practice's own certificate.** If the practice has its own certificate authority
   (for example Active Directory Certificate Services) or IT can supply a certificate for
   the MedUI computer's name, use it. Nothing new is trusted anywhere.
   ```bash
   ./install.sh --https-cert medui.crt --https-key medui.key
   ```
   The file holds the full chain in PEM format; its names must match what workstations
   type. To renew, run the same command with the new files.
2. **A public certificate**, where the practice owns a domain (for example
   `medui.<practice>.com.au`) whose DNS provider has an API: Caddy can obtain and renew a
   Let's Encrypt certificate by DNS, with nothing opened to the internet, and browsers
   trust it without any setup. This needs a Caddy build with the DNS provider's plugin;
   ask the maintainers. Until then, obtain the certificate another way and use option 1.
3. **A MedUI root, restricted to MedUI** (the default for `--https`). Described below.

## The MedUI root

`./install.sh --https` makes a root certificate on the MedUI computer and gives it to Caddy,
which issues and renews MedUI's own certificate from it (short-lived, renewed
automatically). Workstations trust the root once, and then MedUI's certificate whenever it
renews.

**The usual worry, and the answer.** A trusted root can normally vouch for any website, so
if its key were stolen, anyone could impersonate any site, a bank or Medicare, to every PC
that trusts it. MedUI's root carries an X.509 **name constraint** (RFC 5280, marked
critical): it may only vouch for the names and addresses given at installation. A
certificate it signed for any other name is rejected by Windows, Chrome, Edge and Firefox,
even if the key were stolen. `install.sh` checks this every time it runs: a certificate the
root signs for MedUI's own name verifies, one for `example.com` is refused.

| | |
|---|---|
| Names | The computer's name and its address on the practice network by default, or `--https-name` / `--https-ip` (both repeatable): `./install.sh --https --https-name medui-pc --https-name medui-pc.practice.local --https-ip 192.168.1.20` |
| Root | ECDSA P-256, valid 10 years, `CA:TRUE, pathlen:1`, key usage certificate and CRL signing only, name constraint permitting only the names above |
| Its key | `https/ca/root.key` in the MedUI folder, readable by its owner only (and Caddy). In the backups that `upgrade.sh` takes (`https.tgz`): keep those private. It never leaves the MedUI computer otherwise |
| The file for workstations | `https/medui-root.cer` (DER). Its SHA-1 thumbprint, which Windows shows, is printed at the end of `install.sh` |
| Server certificate | Issued by Caddy through an intermediate it renews; nothing to do |
| Removal | Delete the root from the workstations (or the Group Policy), and stop Caddy: `docker compose --profile https stop caddy` |

Check the restriction yourself on the MedUI computer:

```bash
openssl x509 -in https/ca/root.crt -noout -subject -enddate -ext basicConstraints,nameConstraints
```

On Windows, open `medui-root.cer`, Details, **Name Constraints**.

Names can't be added to an existing root, because the restriction is part of it.
`./install.sh --https-new-root` with the new list makes a new root; workstations then need
the new one, and the old one can be removed from them.

## Trusting the root on workstations

**The setup page (simplest, for practices without a domain).** On each workstation, open
`http://<name>` (port 80, plain HTTP, e.g. `http://pc163`). The page checks whether the PC
already trusts MedUI and, if so, goes straight on to `https://<name>`. If not, it shows the
root's thumbprint and offers **one file**, `setup-medui.cmd`, with the root built in:

1. Open it. Windows SmartScreen may say it protected the PC (the file isn't signed): *More
   info*, *Run anyway*.
2. Approve the administrator prompt, to trust it for every user of the PC; without approval
   it trusts it for that Windows account only.
3. It shows the root, its thumbprint and its name restriction, refuses a root without one,
   and asks before installing. Then it opens MedUI.

*The caveat.* The setup page and file travel over plain HTTP: it's the one step before the
PC trusts MedUI, so it can't be HTTPS. Someone already on the practice network could, in
principle, replace them. The check against that is the thumbprint: `install.sh` prints it on
the MedUI computer; whoever sets up the PCs compares it with the one the setup shows. If
the practice's IT prefers no plain-HTTP step, use Group Policy or the script below, and
close port 80 (`--http-port` to move it; `open_medui_https_port.ps1 -HttpPort 0` leaves it
closed in the Windows firewall). Everything else on port 80 just redirects to HTTPS.

**In a Windows domain (Group Policy):** Group Policy Management, a GPO linked to the
workstations' OU, *Computer Configuration > Policies > Windows Settings > Security
Settings > Public Key Policies > Trusted Root Certification Authorities*, Import
`medui-root.cer`. PCs pick it up at their next policy refresh (`gpupdate /force`).
Unlinking or editing the GPO removes it again.

**Intune / Entra-joined PCs:** a *Trusted certificate* configuration profile with
`medui-root.cer`, store *Computer certificate store - Root*.

**Without the setup page:** `scripts/windows/install_medui_root.ps1 -Path <medui-root.cer>`, as
administrator for the whole PC, or with `-CurrentUser` for one person without administrator
rights. It shows the root, its thumbprint and its restriction before asking, and refuses a
root that has no restriction.

**Browsers:** Chrome and Edge use the Windows store. Firefox uses its own unless
`security.enterprise_roots.enabled` is true (or the policy `Certificates > ImportEnterpriseRoots`);
otherwise import the root in Firefox's settings. Macs: Keychain Access, add it to the
System keychain and set it to *Always Trust*. iPads: install it as a profile, then turn on
full trust in *Settings > General > About > Certificate Trust Settings*.

## On WSL2 (Windows)

MedUI runs inside a WSL2 instance with mirrored networking, so ports 443 and 80 are on the
Windows computer's own address. `create_medui_wsl2.ps1` asks whether to set HTTPS up when it
creates the instance, and opens the ports itself after an administrator approves. For an
instance where that question was answered no, run `./medui.sh https` in it, then open the
ports, for Private and Domain networks only:

```powershell
.\scripts\windows\open_medui_https_port.ps1 -Instance medui
```

From that computer, `medui-root.cer` is at
`\\wsl.localhost\<instance>\home\<user>\medui_os\https\medui-root.cer` (`install.sh` prints the
exact path).

## Afterwards

- Workstations use `https://<name>` (the name, or address, the root was made for); a new
  workstation starts at `http://<name>` for the setup page.
- `install.sh` remembers HTTPS: running it again keeps the root and the settings.
- `upgrade.sh` backs up the `https` folder and restarts Caddy after an upgrade.
- If the `https` folder is lost, restore it from a backup. A new root would mean installing
  it on every workstation again.
- Caddy's log: `docker compose --profile https logs caddy`.
