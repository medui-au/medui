# Ubuntu, live installation

| | |
|---|---|
| **Use this when** | MedUI is for the practice's real work, reading its Best Practice, on a computer that already runs Ubuntu. |
| **Not this one** | To try MedUI or train staff with invented patients: [Ubuntu, demo](ubuntu-demo.md). On a Windows PC: [Windows PC, live](windows-live.md). |
| **The script** | `./install.sh`, in the MedUI folder you download with `git clone` (below). |
| **The computer** | Ubuntu with systemd (tested on 24.04 and 26.10); about 10 GB of free disk; your own login with `sudo`, not root. |

**In short:** have [section 1](#1-what-to-have-ready) ready, then:

```bash
cd ~ && git clone https://github.com/medui-au/medui.git ~/medui_os
```

```bash
cd ~/medui_os && ./install.sh
```

**For:** an Ubuntu server (bare metal or virtual), or an Ubuntu WSL2 instance you already
have and look after yourself. **You end up with:** MedUI running in Docker in the folder
`~/medui_os`, answering at `http://127.0.0.1:5005` on that computer only, ready for the
[Administrator setup guide](../setup-guide.md).

A server usually has no browser, so in practice the next step is HTTPS for the workstations
(section 5).

For a demo (invented patients, never BP), see [Ubuntu, demo](ubuntu-demo.md) instead.

## 1. What to have ready

| Item | Needed for | Notes |
|---|---|---|
| Ubuntu with systemd | The install | Tested on 24.04 and 26.10; any recent Ubuntu should work. For a practice server, a long-term support (LTS) release such as 24.04 gets updates for longest. On WSL2, systemd must be on (`systemd=true` under `[boot]` in `/etc/wsl.conf`). |
| Your own login with `sudo` | Installing packages | **Not root**: the script refuses to run as root, and asks for your `sudo` password when it needs it. |
| About 10 GB of free disk; internet access | The install | Ubuntu packages, GitHub, Docker Hub. |
| A network path to the Best Practice SQL Server | Reading BP | |
| A fixed address or DHCP reservation, and a name workstations can resolve | HTTPS | MedUI's certificate is made for that name and address. |
| A GitHub token | Downloading MedUI while the repository is private | Read-only **Contents** access to `medui-au/medui`. Revoke it afterwards. |
| The practice's timezone | "Today" on the day sheet | A server is often set to UTC, so check it. |
| A username and password for MedUI's own administrator | Your first login | Username not a number; password at least 12 characters. |

**Not needed to install, needed soon after:** the BP read-only (EDBA) password, and AI provider
keys if the practice will use AI. The
[Administrator setup guide](../setup-guide.md#what-the-administrator-needs) explains both.

## 2. Get MedUI and run the installer

Log in as your own user, start in your home folder, and download MedUI:

```bash
cd ~ && git clone https://github.com/medui-au/medui.git ~/medui_os
```

While the repository is private, git asks for a username (your GitHub username) and a password
(paste the **token**, not your GitHub password). Don't use `sudo` here: your user should own the
folder. If `git` is missing: `sudo apt install -y git`. If the download fails:
[troubleshooting](../troubleshooting.md#downloading-medui-git-clone).

To see what the installer would do, without changing anything:

```bash
cd ~/medui_os && ./install.sh --dry-run
```

Then run it:

```bash
cd ~/medui_os && ./install.sh
```

No switch is needed for a live installation. `./install.sh --help` lists the options, and the
[cheat sheet](../cheatsheet.md) explains each one.

## 3. What it asks, in order

| # | Question | Default | Notes |
|---|---|---|---|
| 1 | Practice timezone | this computer's | A menu of Australian capitals. A server is often set to UTC, so check it. |
| 2 | Live or demo? (L/d) | L | **Enter for live.** |
| 3 | Install MedUI with these settings? (y/N) | N | The settings are listed above it: folder, name, ports, timezone. **Type `y`**: Enter means no, and nothing is changed. |
| 4 | `sudo` password | | Asked by Ubuntu, for the system packages: Docker, Compose, Buildx, git, curl. |
| 5 | MedUI administrator username and password | | After the builds, which take several minutes. Username not a number; password at least 12 characters. |

Ports are not asked. They are 5005 (MedUI), 55432 (PostgreSQL) and 5707 (OCR), all on this
computer only; one that is taken moves to the next free one and the script says so. To choose
them: `--app-port`, `--db-port`, `--ocr-port`.

## 4. Check it worked

The script ends with `MedUI answers at http://127.0.0.1:5005` and a list of next steps. On the
computer itself:

```bash
curl -s http://127.0.0.1:5005/health
```

**Log out and back in before going on.** The installer adds you to the `docker` group, which
takes effect at your next login.

## 5. What is particular to Ubuntu

The rest of the setup (Best Practice, OCR, AI, backups) is the same on every installation: see
the [Administrator setup guide](../setup-guide.md). These parts are particular to an Ubuntu
computer you look after yourself.

**Opening MedUI's menu:**

```bash
cd ~/medui_os && ./medui.sh
```

**HTTPS for the workstations.** Run `./medui.sh https`. It lists the name and address the
certificate will cover (by default this computer's own), then asks "Install MedUI with these
settings?": check them and type `y`. To give them yourself:

```bash
cd ~/medui_os && ./install.sh --https --https-name <name> --https-ip <address>
```

If the computer runs a firewall (`ufw`), allow ports 443 and 80 from the practice network. On an
Ubuntu WSL2 instance, also run `scripts/windows/open_medui_https_port.ps1` on Windows as
administrator. Each workstation then opens `http://<computer name>` once and runs the setup it
offers. See [HTTPS](../https.md).

**An Ubuntu WSL2 instance you made yourself** gets none of what the Windows script arranges on
the Windows side: mirrored networking, the task that keeps the instance running, and the firewall
rules. If you want those, the [Windows recipe](windows-live.md) is the easier route. Clone into
the instance's own filesystem (`~`, under `/home`), not a Windows folder under `/mnt/c`.

**Running `./install.sh` again is safe:** it keeps data, settings and secrets.

**Upgrading:** `./upgrade.sh` in the folder (`--dry-run` first). **Removing:** `./medui.sh remove`.

**A second installation on the same computer** goes in a folder of its own, and takes its name
from the folder: `git clone … ~/medui_test`. Its ports move to free ones by themselves. A test or
training installation must never point at the practice's live BP server: use a
[demo](ubuntu-demo.md) for that.

## Next

The [Administrator setup guide](../setup-guide.md): connect Best Practice, set up the
workstations, OCR and AI, and back up.

[Back to installing MedUI](README.md)
