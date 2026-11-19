# Ubuntu, demo installation

**For:** demonstrations, training and screen recordings. **You end up with:** a demo installation
in its own folder, `~/medui_demo`, with a SQL Server of its own holding MedUI's invented demo
practice: 43 made-up patients with results, letters and bookings. It never reads Best Practice,
and it can sit beside a live installation on the same computer.

**It is the [Ubuntu live recipe](ubuntu-live.md) with one switch, `--demo`,** and these
differences.

## What to have ready: differences

| Item | Difference |
|---|---|
| The computer | Intel or AMD (x86-64) only. 8 GB of memory or more is comfortable; under 6 GB the script warns. Allow about 2 GB more disk than a live installation, for SQL Server. |
| GitHub token | Must read `medui-au/medui` **and** `medui-au/medui_demodata` while both are private. |
| EDBA password | Not needed. A demo is never connected to Best Practice. |
| A password for the demo users | New. One password, shared by all the demo's staff logins. |
| Microsoft's SQL Server licence terms | New. You are asked to accept them ([aka.ms/useterms](https://aka.ms/useterms)). SQL Server Express is free. |

## Get MedUI and run the installer

The folder must **not** be called `medui_os`: the installer refuses, so a demo can't be mistaken
for the practice's installation. Clone into `~/medui_demo`:

```bash
cd ~ && git clone https://github.com/medui-au/medui.git ~/medui_demo
```

While `medui_demodata` is private, the installer needs the token too. This line asks for it
without showing it, runs the installer, then forgets it:

```bash
cd ~/medui_demo && read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./install.sh --demo; unset MEDUI_GIT_TOKEN
```

Once `medui_demodata` is public, `cd ~/medui_demo && ./install.sh --demo` is enough.

## What it asks: differences

| Live recipe question | In a demo |
|---|---|
| 2. Live or demo? | Not asked: `--demo` answers it. (Without the switch, answering `d` does the same.) |
| New, before "Install MedUI with these settings?" | Do you accept Microsoft's SQL Server licence terms? (y/N). Type `y`. |
| New, after the demo databases are restored | A password for the demo users. |

If a live installation is on the same computer, the demo's ports move to the next free ones
(5006, 55433, 5708) and the script says so.

## Check it worked, and afterwards

- Open MedUI and log in as a demo user, by name, with the demo users' password:
  **Dr Imogen Thistlewood** (practice owner), Dr Callum Ravensworth (doctor), Rosalind Quenby
  (nurse), Tessa Wyndham-Lowe (reception); or as the administrator you created.
- `./medui.sh demo refresh` brings the dates up to today: do it before each demonstration or
  recording. `./medui.sh demo password` sets a new password for the demo users.
- OCR and AI: as the [Administrator setup guide](../setup-guide.md), leaving out Best Practice.
- **HTTPS:** only one installation on a computer can have ports 443 and 80. For a demo beside a
  live installation, give it other ports:

  ```bash
  cd ~/medui_demo && ./install.sh --https --https-port 8443 --http-port 8080
  ```

  `./medui.sh use` switches which installation on the computer runs.

**A demo stays a demo.** Never point it at Best Practice, and `./medui.sh bp` refuses to. MedUI
keeps BP's patient and user numbers in its own database, so demo records would attach to
whichever real patients have the same numbers. For Best Practice, make a
[live installation](ubuntu-live.md). More in the
[Administrator setup guide](../setup-guide.md#a-demo-installation).

[Back to installing MedUI](README.md)
