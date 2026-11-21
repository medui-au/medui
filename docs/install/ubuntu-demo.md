# Ubuntu, demo installation

| | |
|---|---|
| **Use this when** | You want to demonstrate MedUI, train staff or make recordings, with invented patients, on a computer that already runs Ubuntu. It never reads Best Practice. |
| **Not this one** | For the practice's real work: [Ubuntu, live](ubuntu-live.md). On a Windows PC: [Windows PC, demo](windows-demo.md). |
| **The script** | `./install.sh --demo`, in a MedUI folder called `medui_demo` that you download with `git clone` (below). |
| **The computer** | Ubuntu with systemd (tested on 24.04 and 26.10), Intel or AMD (x86-64) only; 8 GB of memory or more (under 6 GB the script warns); about 12 GB of free disk; your own login with `sudo`, not root. |
| **Time** | Allow 30 to 40 minutes to install. |

**In short:** have [section 1](#1-what-to-have-ready) ready, then:

```bash
cd ~ && git clone https://github.com/medui-au/medui.git ~/medui_demo
```

```bash
cd ~/medui_demo && read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./install.sh --demo; unset MEDUI_GIT_TOKEN
```

**You end up with:** a demo installation in its own folder, `~/medui_demo`, with a SQL Server
Express of its own holding MedUI's invented demo practice: 43 made-up patients with results,
letters and bookings. It needs no EDBA password, and it can sit beside a live installation on the
same computer.

## 1. What to have ready

| Item | Needed for | Notes |
|---|---|---|
| Ubuntu with systemd, on Intel or AMD (x86-64) | The install | Microsoft's SQL Server runs only on x86-64. On WSL2, systemd must be on (`systemd=true` under `[boot]` in `/etc/wsl.conf`). |
| 8 GB of memory or more | The demo's SQL Server | It takes up to 2 GB on top of MedUI. Under 6 GB the script warns. |
| Your own login with `sudo` | Installing packages | **Not root**: the script refuses to run as root, and asks for your `sudo` password when it needs it. |
| About 12 GB of free disk; internet access | The install | Ubuntu packages, GitHub, Docker Hub, and about 1.6 GB for Microsoft's SQL Server image. |
| A GitHub token | Downloading MedUI and the demo data while the repositories are private | Read-only **Contents** access to **both** `medui-au/medui` and `medui-au/medui_demodata`. Revoke it afterwards. |
| Microsoft's SQL Server licence terms | The demo's SQL Server | You are asked to accept them ([aka.ms/useterms](https://aka.ms/useterms)). SQL Server Express is free. |
| A password for the demo users | Logging in as the demo practice's staff | One password, shared by all the demo's staff logins. Choose one you can give to trainees. |
| The practice's timezone | "Today" on the day sheet | A server is often set to UTC, so check it. |
| A username and password for MedUI's own administrator | Your first login | Username not a number; password at least 12 characters. |

**Not needed:** the BP read-only (EDBA) password. A demo is never connected to Best Practice. AI
provider keys only if you will show AI.

## 2. Get MedUI and run the installer

Log in as your own user and download MedUI into `~/medui_demo`, as shown: the folder's name
becomes the installation's name. Any name works except `medui_os`, which is kept for the
practice's live installation; the installer refuses it for a demo.

```bash
cd ~ && git clone https://github.com/medui-au/medui.git ~/medui_demo
```

While the repository is private, git asks for a username (your GitHub username) and a password
(paste the **token**, not your GitHub password). Don't use `sudo` here: your user should own the
folder. If `git` is missing: `sudo apt install -y git`. If the download fails:
[troubleshooting](../troubleshooting.md#downloading-medui-git-clone).

While `medui-au/medui_demodata` is private, the installer needs the token too. This line asks for it
without showing it, runs the installer, then forgets it:

```bash
cd ~/medui_demo && read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./install.sh --demo; unset MEDUI_GIT_TOKEN
```

Once `medui_demodata` is public, `cd ~/medui_demo && ./install.sh --demo` is enough. To see what
it would do first, without changing anything, add `--dry-run`.

## 3. What it asks, in order

| # | Question | Default | Notes |
|---|---|---|---|
| 1 | Practice timezone | this computer's | A menu of Australian capitals. |
| 2 | Do you accept Microsoft's SQL Server licence terms? (y/N) | N | **Type `y`.** Enter means no, and nothing is installed. |
| 3 | Install MedUI with these settings? (y/N) | N | The settings are listed above it: folder, name, ports, timezone. **Type `y`**: Enter means no, and nothing is changed. |
| 4 | `sudo` password | | Asked by Ubuntu, for the system packages: Docker, Compose, Buildx, git, curl. |
| 5 | A password for the demo users | | Once the demo databases are restored. |
| 6 | MedUI administrator username and password | | After the builds, which take several minutes. Username not a number; password at least 12 characters. |

"Live or demo?" is not asked: `--demo` answers it. Ports are not asked. They are 5005 (MedUI),
55432 (PostgreSQL) and 5707 (OCR), all on this computer only; if a live installation already has
them, the demo's move to the next free ones (5006, 55433, 5708) and the script says so.

## 4. Check it worked

The script ends with the address MedUI answers at. Open it and log in either way:

- as a demo user, by name, with the demo users' password: **Dr Imogen Thistlewood** (practice
  owner), Dr Callum Ravensworth (doctor), Rosalind Quenby (nurse), Tessa Wyndham-Lowe (reception);
- as the MedUI administrator you created.

**Log out and back in before going on.** The installer adds you to the `docker` group, which
takes effect at your next login.

## 5. Afterwards

**Opening MedUI's menu:**

```bash
cd ~/medui_demo && ./medui.sh
```

| Task | How | Notes |
|---|---|---|
| Bring the dates up to today | `./medui.sh demo refresh` | Do this before each demonstration or recording, so results, visits and bookings look recent. |
| Change the demo users' password | `./medui.sh demo password` | |
| OCR and AI | As the [Administrator setup guide](../setup-guide.md), leaving out Best Practice | |
| HTTPS for trainees' PCs | `./medui.sh https` | Only one installation on a computer can have ports 443 and 80. Beside a live installation, give the demo other ports: `cd ~/medui_demo && ./install.sh --https --https-port 8443 --http-port 8080`. See [HTTPS](../https.md). |
| Choose which installation runs | `./medui.sh use` | |
| Upgrade | `./upgrade.sh` (`--dry-run` first) | |
| Remove | `./medui.sh remove` | A live installation on the same computer is not touched. |

**A demo stays a demo.** Never point it at Best Practice, and `./medui.sh bp` refuses to. MedUI
keeps BP's patient and user numbers in its own database, so demo records would attach to
whichever real patients have the same numbers. For Best Practice, make a
[live installation](ubuntu-live.md). More in the
[Administrator setup guide](../setup-guide.md#a-demo-installation).

[Back to installing MedUI](README.md)
