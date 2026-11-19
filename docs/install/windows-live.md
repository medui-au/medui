# Windows PC, live installation

**For:** whoever installs MedUI for the practice on a Windows PC. **You end up with:** a new
Ubuntu 24.04 instance under WSL2, used only for MedUI, with MedUI running in Docker inside it,
ready for the [Administrator setup guide](../setup-guide.md).

MedUI opens straight away in a browser on that PC, at `http://127.0.0.1:5005`. No other computer
can reach it until you turn on HTTPS for the practice's workstations, which nearly every live
installation will want: the script asks (question 11), or you can do it later. Best Practice and
AI stay off until the administrator sets them up.

**Time:** 20 to 40 minutes, most of it downloads and the OCR build. Longer if WSL has to be
installed first, which needs a restart.

For a demo (invented patients, never BP), see [Windows PC, demo](windows-demo.md) instead.

## 1. Choose the PC

MedUI runs only while its Windows account is signed in, so choose a PC that:

- stays switched on, and stays signed in to the Windows account that runs the script (locking the
  screen is fine; signing out stops MedUI);
- can reach the Best Practice SQL Server over the practice network;
- has about 10 GB of free disk.

The BP server itself can be used, if the practice's IT is comfortable with that.

## 2. What to have ready

| Item | Needed for | Notes |
|---|---|---|
| Windows 11, 22H2 or later | The install | Older builds work from that PC's browser only. |
| Virtualisation enabled in the BIOS/UEFI | WSL2 | Usually already on. |
| Internet access | The install | Ubuntu image, Ubuntu packages, GitHub, Docker Hub. |
| An administrator's approval, at up to three points | Installing WSL if it is missing; opening SSH to the network; opening HTTPS to the workstations | You do **not** run the script as administrator (section 3). |
| A GitHub token | Downloading MedUI while the repository is private | A fine-grained token with read-only **Contents** access to `medui-au/medui`. Revoke it afterwards. |
| The practice's timezone | "Today" on the day sheet | Offered from Windows; just confirm it. |
| A username and password for MedUI's own administrator | Your first login | Username not a number; password at least 12 characters. |
| *(Optional)* an SSH public key | Remote access for IT or a coding agent | Default location `C:\Users\<you>\.ssh\id_ed25519.pub`. |

**Not needed to install, needed soon after:** the BP read-only (EDBA) password, and AI provider
keys if the practice will use AI. The
[Administrator setup guide](../setup-guide.md#what-the-administrator-needs) explains both.

## 3. Get and run the script

1. Sign in to Windows **as the account that will run MedUI**.
2. Download [`scripts/windows/create_medui_wsl2.ps1`](../../scripts/windows/create_medui_wsl2.ps1)
   from the `main` branch, into any folder, for example `Downloads`.
3. Open an **ordinary** PowerShell window (Start, type `powershell`, Enter). Not "Run as
   administrator": the instance and its start-up task belong to whoever runs the script, so an
   elevated window under another account builds MedUI for that account.
4. Go to the folder and run it:

   ```powershell
   cd $HOME\Downloads
   Unblock-File .\create_medui_wsl2.ps1
   powershell.exe -NoExit -ExecutionPolicy Bypass -File .\create_medui_wsl2.ps1
   ```

   `Unblock-File` clears the "downloaded from the internet" mark. `-ExecutionPolicy Bypass`
   applies to this one run only.

**If WSL is missing or old,** the script offers to install or update it. An administrator may
have to approve, and Windows may need a restart; then run the same command again.

## 4. What it asks, in order

The script asks everything first, shows a plan, and changes nothing until you confirm. Enter
accepts the default shown in brackets.

| # | Question | Default | What it is for, and what to consider |
|---|---|---|---|
| 1 | Numbers of existing WSL instances to delete | none | Shown only if the PC already has WSL instances. **Press Enter.** Deleting one destroys everything in it. |
| 2 | Live or demo? (L/d) | L | **Enter for live.** |
| 3 | Name for the new instance | `medui` | The WSL instance's name. Must not exist already. |
| 4 | Linux username | `medui` | The account inside the instance that owns MedUI. It has `sudo`; root is locked. |
| 5 | Linux password | generated | Leave blank and one is generated and **shown once at the end: store it**. It is the `sudo` password. |
| 6 | Ports for MedUI, PostgreSQL, OCR | 5005, 55432, 5707 | All three listen on this PC only. If one is in use, the next free one is suggested. |
| 7 | Practice timezone | from Windows | A menu of Australian capitals; pick the practice's. |
| 8 | Branch | `main` | Leave as `main` unless you are testing a branch. |
| 9 | GitHub token | blank | **Paste with a right-click**; Ctrl+V doesn't work in this hidden prompt. It is checked with GitHub at once, used for the one download, and never stored. Blank once the repository is public. |
| 10 | Set up SSH? (Y/n) | Y | For IT or a coding agent to log in from another computer. Say `n` if nobody will. If yes, it asks the port (22, or 2222 if 22 is taken) and the public key file. With a key, passwords are refused; without one, login is by the Linux password. |
| 11 | Open MedUI to the practice's workstations over HTTPS? (y/N) | N | **Say `y` for a practice installation** unless MedUI will only ever be used on this PC. If yes, it asks four things: the HTTPS port (443); the port of the setup page each workstation opens once (80); the name workstations will type (this PC's name); and this PC's address, or `none`. Choose with care: MedUI's certificate covers only that name and address, and changing them later means setting up every workstation again. Give an address only if it stays the same (a fixed address or a DHCP reservation). If another program on the PC already uses 443 or 80, choose other ports, such as 8443 and 8080. |
| 12 | Turn off Windows drives and programs inside the instance? (Y/n) | Y | Keep `Y`. Someone who gets into the instance then can't reach this PC's files. MedUI needs neither. |
| 13 | Install sqlcmd? (y/N) | N | Microsoft's command-line SQL client. Say `y` if you want to test the BP login by hand before giving it to MedUI. |
| 14 | Create the keep-alive task? (Y/n) | Y | Keep `Y`. WSL stops an idle instance, and MedUI with it; this task starts it when you sign in and keeps it running. |
| 15 | Go ahead? (Y/n) | Y | The plan is shown above this. Nothing has changed yet. |

**Then, while it works:**

| When | Question | Notes |
|---|---|---|
| Early, on a first WSL install | Run `wsl --shutdown` now? (Y/n) | Needed once to switch on mirrored networking. It **stops every other running WSL instance** on the PC (it doesn't change them). Say `Y` unless something important is running in one. |
| After the downloads and builds | MedUI administrator username and password | MedUI's own local administrator: your first login. Nothing to do with the Linux user. |
| Near the end, if you chose SSH | Open the SSH port to the practice network? (Y/n) | A yes brings up a Windows administrator prompt. It creates one inbound firewall rule, on Private and Domain networks only. `n` leaves SSH working from this PC only; the command to add the rule later is printed. |
| At the end, if you chose HTTPS | Open the HTTPS and setup-page ports to the practice network? (Y/n) | The same again for the two HTTPS ports: a yes brings up a second Windows administrator prompt. If the HTTPS step itself fails, the script says so and MedUI stays installed; turn HTTPS on later (section 6). |

More detail on every question: [the Windows scripts](../../scripts/windows/README.md).

## 5. Check it worked

The script ends with a summary box. Look for:

- `MedUI health from Windows: 200`;
- the address to open, `http://127.0.0.1:5005/`;
- `Workstations`: the address each workstation opens once to be set up, if you chose HTTPS;
- the generated Linux password, if you left question 5 blank. **Store it now.**

Open the address in a browser on that PC and log in as the administrator you just created.

## 6. What is particular to Windows

The rest of the setup (Best Practice, OCR, AI, backups) is the same on every installation: see
the [Administrator setup guide](../setup-guide.md). These parts are particular to a WSL2
instance.

**Opening MedUI's menu.** From PowerShell, open a shell in the instance, then the menu:

```powershell
wsl -d medui
```

```bash
cd ~/medui_os && ./medui.sh
```

**HTTPS, if you answered no to question 11.** In the instance, run `./medui.sh https`. Then, on
Windows, run `scripts/windows/open_medui_https_port.ps1` as administrator to open the two ports
to the practice network. See [HTTPS](../https.md).

**Stopping MedUI on purpose:** stop the keep-alive task first, or it starts the instance again.

```powershell
Stop-ScheduledTask -TaskName "WSL2 medui keep-alive"; wsl --terminate medui
```

`./medui.sh windows` prints these Windows commands for the instance you are in.

**Running the script again** makes a *second* instance; it never changes an existing one. To
repair or re-run the install inside the instance, use `./install.sh` in `~/medui_os`: it keeps
data and settings.

**Upgrading:** `scripts/windows/upgrade_medui_wsl2.ps1` from Windows, which can save a snapshot of
the whole instance first, or `./upgrade.sh` inside the instance.

**Removing it:** `./medui.sh remove` inside the instance, then the Windows commands it prints.

**A test or training installation must never point at the practice's live BP server:** the login
reads every database it can open there. Use a [demo](windows-demo.md) for that.

## Next

The [Administrator setup guide](../setup-guide.md): connect Best Practice, set up the
workstations, OCR and AI, and back up.

[Back to installing MedUI](README.md)
