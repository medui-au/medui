# MedUI on Windows: a WSL2 instance in one script

`create_medui_wsl2.ps1` creates a **new** Ubuntu 24.04 instance under WSL2 and
installs MedUI in it with `install.sh`. To upgrade an existing one, use
`upgrade_medui_wsl2.ps1` ([Upgrading](#upgrading)). It asks its questions first, shows the
plan, and changes nothing until you confirm. Existing WSL instances are never
changed unless you choose to delete one and type its name to confirm.

## Requirements

| Item | Requirement |
|---|---|
| Windows | Windows 11 22H2 or later recommended (mirrored networking). On older builds MedUI still works from this PC's browser; SSH from the network does not. |
| WSL | 2.4.4 or later. The script offers to install or update WSL; **a reboot may be needed**, after which you run the script again. |
| Shell | Windows PowerShell 5.1, an **ordinary** window (not "Run as administrator"), signed in as the Windows account that will use MedUI. |
| Virtualisation | Enabled in the firmware (BIOS/UEFI). |
| Network | Internet access for the Ubuntu image, Ubuntu packages, GitHub and Docker Hub. |
| Disk | About 10 GB free. |
| Repository access | While the repository is private: a GitHub personal access token with read access to it. Prefer a fine-grained token with read-only **Contents** access to this one repository, and revoke it after installing. |
| Administrator | Only for the firewall rules that open SSH, or MedUI over HTTPS, to the network (a Windows prompt at those steps), and to install WSL if it is missing. |

## Running it

From an ordinary PowerShell window, in the folder holding the script:

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass -File .\create_medui_wsl2.ps1
```

`-ExecutionPolicy Bypass` applies to that one process only. If the script was
downloaded, you may first need `Unblock-File .\create_medui_wsl2.ps1`.

Don't run it as administrator: the instance, `.wslconfig` and the keep-alive task belong
to the account that runs the script, so elevating with another account's password builds
MedUI for that account instead. If the window is elevated under an account other than the
one signed in to Windows, the script says so and stops unless you confirm. If WSL is not
installed and you are not an administrator, it prints the command for one to run
(`wsl --install --no-distribution`), then a restart.

## What it asks

| Question | Default | Notes |
|---|---|---|
| Instances to delete | none | Each deletion needs the exact name typed. Deleting an instance deletes any MedUI database in it. |
| Live or demo | live | A demo ([recipe](../../docs/install/windows-demo.md)) has invented patients in a SQL Server of its own and never reads Best Practice. It gets its own defaults: instance `medui_demo`, folder `~/medui_demo`, ports 5006, 55433, 5708, so it can sit beside a live instance. Its GitHub token must also read medui_demodata while that is private. `install.sh` then asks you to accept Microsoft's SQL Server licence terms and for the demo users' password. |
| Name of the new instance | `medui` | Must not exist already. |
| Linux username and password | `medui`, generated | A generated password is shown once at the end: store it. |
| Ports for MedUI, PostgreSQL, OCR | 5005, 55432, 5707 | Checked against Windows, since mirrored networking shares one network: a port in use gets the next free one suggested. All three listen on localhost only. |
| Branch | `main` | Lets you test a branch before it is merged. |
| GitHub token | blank | Paste with a right-click: Ctrl+V and Ctrl+Shift+V do not paste into this hidden prompt (each sends one character). Each character shows as one `*`, so a token shows as a long row. Checked against GitHub straight away, with the branch, and asked again if it doesn't work, before anything is installed. Used once, for the clone, through a temporary helper. Never written to disk or shown on a command line. Leave blank for a public repository. |
| SSH | yes | For IT or a remote coding agent: hardened sshd, fail2ban, a firewall rule for Private and Domain networks only. With a public key, login is **key only** (passwords refused, since the Linux password also gives sudo); without one, password login. Local forwarding is allowed, so `ssh -L` can reach MedUI from another PC; reverse tunnels are refused. The firewall rule needs an administrator: the script first explains what the rule permits and asks **Y/n**; the Windows prompt appears only after a yes. Answer no, or cancel the prompt, to keep SSH to this PC only (the script prints the command to add it later). |
| HTTPS for workstations | no | Until HTTPS is on, MedUI answers on this PC only; other PCs, and the scribe's microphone on them, need it. On a yes it asks the HTTPS port (443), the port of the setup page each workstation opens once (80), the name workstations will type (this PC's name) and this PC's address (`none` for the name only; an address must stay the same). MedUI's certificate covers only that name and address: changing them later means setting up every workstation again. Set up last, with `install.sh --https`; a failure is reported and the installation stands. The firewall rules need an administrator: the script explains, asks Y/n, then Windows prompts. A no here leaves it for later: `./medui.sh https` ([HTTPS](../../docs/https.md)). |
| Windows drives and programs | off | Turns off `/mnt/c` and starting Windows programs from the instance, so a login to the instance doesn't reach this PC's files. MedUI uses neither. |
| sqlcmd | no | Microsoft's command-line client, to test the BP login from the instance before configuring MedUI. Not asked for a demo. |
| Keep-alive task | yes | WSL stops an idle instance, and MedUI with it. The task starts the instance at your logon and keeps it running: it starts it again within about 10 seconds if it stops, and the task itself is checked every 5 minutes. It runs while you are signed in to Windows. |

## What it does

1. Checks Windows and WSL; installs or updates WSL if needed.
2. Sets `networkingMode=mirrored` in `%USERPROFILE%\.wslconfig`, keeping other settings. Applying it needs `wsl --shutdown`, which stops (but does not change) running instances; it asks first.
3. Installs the new instance, creates the user (sudo; root password locked) and switches on systemd.
4. Installs Docker Engine, Compose, Buildx and git from Ubuntu's repositories, and adds the user to the `docker` group.
5. Clones MedUI to `~/medui_os` as the user (a demo: `~/medui_demo`, with medui_demodata in it).
6. Runs `./install.sh` there (`--demo` for a demo), in this window: you are asked for MedUI's administrator username and password. The OCR build takes several minutes.
7. Optionally: SSH, sqlcmd, the keep-alive task.
8. Optionally: HTTPS for workstations (`./install.sh --https` with the name, address and ports you gave), and its firewall rules.
9. Checks Docker and MedUI's health, from inside the instance and from Windows, and prints a summary.

MedUI is then at `http://127.0.0.1:5005/` (or the port you chose) in a browser
on this PC. Other PCs reach it only over HTTPS: answer yes to the HTTPS question, or turn it
on later ([HTTPS for other PCs](#https-for-other-pcs)).

## Afterwards

```powershell
wsl -d medui                         # a shell in the instance
wsl -d medui --cd /home/medui/medui_os -- ./install.sh   # re-run the installer: keeps data and settings
```

To stop MedUI on purpose, end the keep-alive task first, or it starts the instance again:

```powershell
Stop-ScheduledTask -TaskName "WSL2 medui keep-alive"
wsl --terminate medui
```

`Start-ScheduledTask -TaskName "WSL2 medui keep-alive"` starts it again (or wait for the
5-minute check).

Inside the instance, `./medui.sh` in `~/medui_os` opens MedUI's menu, and `./medui.sh status`
shows what is running. Best Practice, HTTPS, OCR, AI and backups: the
[Administrator setup guide](../../docs/setup-guide.md).

## Upgrading

`upgrade_medui_wsl2.ps1` upgrades MedUI in an existing instance and keeps its data
and settings. It doesn't need an elevated PowerShell:

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass -File .\upgrade_medui_wsl2.ps1
```

1. Asks for the instance (default `medui`) and finds MedUI's folder in it.
2. Offers a **snapshot** of the whole instance (`wsl --export` to
   `%USERPROFILE%\WSL-snapshots`). It stops the instance while it is written, takes
   several minutes and several GB, and is the simplest way back: it replaces the whole
   instance. The keep-alive task is ended first, so it can't start the instance during
   the snapshot. The instance is kept running afterwards, hidden, as the task does; the
   task itself takes over again within 5 minutes (or, for an instance created before
   this release, at the next logon).
3. While the repository is private, asks for a GitHub token (paste with a right-click),
   checks it with GitHub, and passes it to the instance for this run only, in an
   environment variable: never on a command line, never written to disk.
4. Runs `upgrade.sh` in the instance, in this window: it shows what's new, backs up
   the database and settings, and asks before changing anything (see
   [operations](../../docs/operations.md#upgrades)). An installation from before
   `upgrade.sh` existed gets the new release's copy.
5. Prints how to restore the snapshot, if one was taken.

`-Instance <name>` and `-To <tag or branch>` skip the question and pick a release.

## HTTPS for other PCs

If you answered yes to `create_medui_wsl2.ps1`'s HTTPS question, the first step below is done.
Otherwise, after `./medui.sh https` (or `./install.sh --https`) in the instance
([HTTPS](../../docs/https.md)):

- `open_medui_https_port.ps1`, as administrator on this PC: opens port 443, and port 80 for
  the setup page, on Private and Domain networks only (where Windows cannot limit the
  Hyper-V rule by network, it says the ports are open on all networks).
- On each workstation outside a Windows domain: open `http://<this PC's name>` and run the
  one-file setup it offers (in a domain, Group Policy does it instead).
  `install_medui_root.ps1 -Path <medui-root.cer>` does the same from a copied file.

## Removing it

Replace `medui` with your instance name (and, in paths, your Linux username).

```powershell
Stop-ScheduledTask -TaskName "WSL2 medui keep-alive"
wsl --terminate medui
wsl --unregister medui              # permanently deletes the instance and MedUI's data in it
Unregister-ScheduledTask -TaskName "WSL2 medui keep-alive" -Confirm:$false
Get-NetFirewallRule -DisplayName "WSL2 medui SSH*" | Remove-NetFirewallRule
Get-NetFirewallHyperVRule | Where-Object DisplayName -like 'WSL2 medui SSH*' | Remove-NetFirewallHyperVRule
Get-NetFirewallRule -DisplayName "WSL2 medui MedUI*" | Remove-NetFirewallRule
Get-NetFirewallHyperVRule | Where-Object DisplayName -like 'WSL2 medui MedUI*' | Remove-NetFirewallHyperVRule
```

The firewall lines need an administrator PowerShell. The last two remove the HTTPS rules, if
the instance's HTTPS ports were opened to the network.

To undo mirrored networking, remove `networkingMode=mirrored` from
`%USERPROFILE%\.wslconfig` and run `wsl --shutdown`. Other instances may rely on it.
