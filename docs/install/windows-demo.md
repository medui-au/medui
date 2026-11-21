# Windows PC, demo installation

| | |
|---|---|
| **Use this when** | You want to demonstrate MedUI, train staff or make recordings on a Windows PC, with invented patients. It never reads Best Practice. |
| **Not this one** | For the practice's real work: [Windows PC, live](windows-live.md). On a computer running Ubuntu: [Ubuntu, demo](ubuntu-demo.md). |
| **The script** | [`create_medui_wsl2.ps1`](https://github.com/medui-au/medui/blob/main/scripts/windows/create_medui_wsl2.ps1), the same one as for a live installation. On its GitHub page, choose **Download raw file** (↓). While the repository is private, sign in to GitHub first. |
| **Answer** | `d` to "Live or demo?". |
| **The PC** | Windows 11 22H2 or later, Intel or AMD; 8 GB of memory or more; about 12 GB of free disk. |
| **Time** | Allow 30 to 40 minutes to install. |

**In short:** have [section 2](#2-what-to-have-ready) ready, save the script in `Downloads`, then
in an **ordinary** PowerShell window (not "Run as administrator"):

```powershell
cd $HOME\Downloads
Unblock-File .\create_medui_wsl2.ps1
powershell.exe -NoExit -ExecutionPolicy Bypass -File .\create_medui_wsl2.ps1
```

**You end up with:** a WSL2 instance of its own (`medui_demo`) holding MedUI and a SQL Server
Express of its own with MedUI's invented demo practice: 43 made-up patients with results, letters
and bookings. It needs no EDBA password, and it can sit beside a live installation on the same PC.

MedUI opens straight away in a browser on that PC, at `http://127.0.0.1:5006`. Trainees' own PCs
can reach it once you turn on HTTPS (question 11).

## 1. Choose the PC

The demo runs only while its Windows account is signed in, so choose a PC that:

- stays switched on, and stays signed in to the Windows account that runs the script (locking the
  screen is fine; signing out stops MedUI);
- has 8 GB of memory or more: the demo's SQL Server takes up to 2 GB on top of MedUI;
- has about 12 GB of free disk.

It needs no network path to Best Practice.

## 2. What to have ready

| Item | Needed for | Notes |
|---|---|---|
| Windows 11, 22H2 or later | The install | Older builds work from that PC's browser only. |
| Virtualisation enabled in the BIOS/UEFI | WSL2 | Usually already on. |
| Internet access | The install | Ubuntu image, Ubuntu packages, GitHub, Docker Hub, Microsoft's SQL Server image. |
| An administrator's approval, at up to three points | Installing WSL if it is missing; opening SSH to the network; opening HTTPS to the trainees' PCs | You do **not** run the script as administrator (section 3). |
| A GitHub token | Downloading MedUI and the demo data while the repositories are private | A fine-grained token with read-only **Contents** access to **both** `medui-au/medui` and `medui-au/medui_demodata`. The script checks both before installing anything. Revoke it afterwards. |
| Microsoft's SQL Server licence terms | The demo's SQL Server | You are asked to accept them ([aka.ms/useterms](https://aka.ms/useterms)). SQL Server Express is free. |
| A password for the demo users | Logging in as the demo practice's staff | One password, shared by all the demo's staff logins. Choose one you can give to trainees. |
| A username and password for MedUI's own administrator | Your first login | Username not a number; password at least 12 characters. |
| *(Optional)* an SSH public key | Remote access for IT or a coding agent | Default location `C:\Users\<you>\.ssh\id_ed25519.pub`. |

**Not needed:** the BP read-only (EDBA) password. A demo is never connected to Best Practice. AI
provider keys only if you will show AI.

## 3. Get and run the script

1. Sign in to Windows **as the account that will run the demo**.
2. Download [`create_medui_wsl2.ps1`](https://github.com/medui-au/medui/blob/main/scripts/windows/create_medui_wsl2.ps1)
   from the `main` branch (**Download raw file**, ↓), into any folder, for example `Downloads`.
3. Open an **ordinary** PowerShell window (Start, type `powershell`, Enter). Not "Run as
   administrator": the instance and its start-up task belong to whoever runs the script, so an
   elevated window under another account builds the demo for that account.
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
| 1 | Numbers of existing WSL instances to delete | none | Shown only if the PC already has WSL instances. **Press Enter.** Deleting one destroys everything in it, a live installation included. |
| 2 | Live or demo? (L/d) | L | **Type `d`.** The defaults below then change to a demo's own. |
| 3 | Name for the new instance | `medui_demo` | The WSL instance's name. Must not exist already. |
| 4 | Linux username | `medui` | The account inside the instance that owns MedUI. It has `sudo`; root is locked. |
| 5 | Linux password | generated | Leave blank and one is generated and **shown once at the end: store it**. It is the `sudo` password. |
| 6 | Ports for MedUI, PostgreSQL, OCR | 5006, 55433, 5708 | All three listen on this PC only, apart from a live installation's. If one is in use, the next free one is suggested. |
| 7 | Practice timezone | from Windows | A menu of Australian capitals. |
| 8 | Branch | `main` | Leave as `main` unless you are testing a branch. |
| 9 | GitHub token | blank | **Paste with a right-click**; Ctrl+V doesn't work in this hidden prompt. It is checked with GitHub at once, for both repositories, used for the downloads, and never stored. Blank once both repositories are public. |
| 10 | Set up SSH? (Y/n) | Y | For IT or a coding agent to log in from another computer. Say `n` if nobody will. If yes, it asks the port (22, or 2222 if 22 is taken) and the public key file. |
| 11 | Open MedUI to other PCs over HTTPS? (y/N) | N | Say `y` if trainees will use their own PCs. If yes, it asks the HTTPS port (443), the setup page's port (80), the name they will type (this PC's name) and this PC's address, or `none`. **If a live installation on this PC already has HTTPS, type other ports**, such as 8443 and 8080: 443 and 80 are taken, and the script may not notice. |
| 12 | Turn off Windows drives and programs inside the instance? (Y/n) | Y | Keep `Y`. MedUI needs neither. |
| 13 | Create the keep-alive task? (Y/n) | Y | Keep `Y` unless the demo is only started for sessions. WSL stops an idle instance, and MedUI with it. |
| 14 | Go ahead? (Y/n) | Y | The plan is shown above this. Nothing has changed yet. |

**Then, while it works:**

| When | Question | Notes |
|---|---|---|
| Early, on a first WSL install | Run `wsl --shutdown` now? (Y/n) | Needed once to switch on mirrored networking. It **stops every other running WSL instance** on the PC (it doesn't change them). Say `Y` unless something important is running in one. |
| While it works, before the administrator question | Do you accept Microsoft's SQL Server licence terms? (y/N) | Type `y`. Enter means no, and the installation stops there. |
| Once the demo databases are restored | Password for the demo users | The one password all the demo's staff logins share. |
| After the downloads and builds | MedUI administrator username and password | MedUI's own local administrator. Nothing to do with the Linux user. |
| Near the end, if you chose SSH or HTTPS | Open the ports to the practice network? (Y/n) | Each yes brings up a Windows administrator prompt and creates inbound firewall rules, on Private and Domain networks only. |

More detail on every question: [the Windows scripts](../../scripts/windows/README.md).

## 5. Check it worked

The summary box says `MedUI DEMO installed in WSL2`. Look for `MedUI health from Windows: 200`
and the generated Linux password, if you left question 5 blank: **store it now**.

Open `http://127.0.0.1:5006/` on that PC and log in either way:

- as a demo user, by name, with the demo users' password: **Dr Imogen Thistlewood** (practice
  owner), Dr Callum Ravensworth (doctor), Rosalind Quenby (nurse), Tessa Wyndham-Lowe (reception);
- as the MedUI administrator you created.

## 6. Afterwards

**Opening MedUI's menu.** From PowerShell, open a shell in the instance, then the menu:

```powershell
wsl -d medui_demo
```

```bash
cd ~/medui_demo && ./medui.sh
```

| Task | How | Notes |
|---|---|---|
| Bring the dates up to today | `./medui.sh demo refresh` | Do this before each demonstration or recording, so results, visits and bookings look recent. |
| Change the demo users' password | `./medui.sh demo password` | |
| OCR and AI | As the [Administrator setup guide](../setup-guide.md), leaving out Best Practice | |
| HTTPS, if you answered no to question 11 | `./medui.sh https` in the instance, then `scripts/windows/open_medui_https_port.ps1` on Windows as administrator | Beside a live installation, use other ports (8443 and 8080). Trainees' PCs open `http://<this PC's name>:8080` once, then `https://<this PC's name>:8443`. A PC already set up for the live installation needs the demo's setup too: each has its own certificate. See [HTTPS](../https.md). |
| Stop the demo on purpose | `Stop-ScheduledTask -TaskName "WSL2 medui_demo keep-alive"; wsl --terminate medui_demo` in PowerShell | Stop the task first, or it starts the instance again. `./medui.sh windows` prints these commands. |
| Upgrade | `scripts/windows/upgrade_medui_wsl2.ps1` from Windows (it can save a snapshot first), or `./upgrade.sh` in the instance | |
| Remove | `./medui.sh remove` in the instance, then the Windows commands it prints | A live installation on the same PC is not touched. |

**Running the script again** makes a *second* instance; it never changes an existing one.

**A demo stays a demo.** Never point it at Best Practice, and `./medui.sh bp` refuses to. MedUI
keeps BP's patient and user numbers in its own database, so demo records would attach to
whichever real patients have the same numbers. For Best Practice, make a
[live installation](windows-live.md). More in the
[Administrator setup guide](../setup-guide.md#a-demo-installation).

[Back to installing MedUI](README.md)
