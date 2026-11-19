# Windows PC, demo installation

**For:** demonstrations, training and screen recordings. **You end up with:** a WSL2 instance of
its own (`medui_demo`) holding MedUI and a SQL Server of its own with MedUI's invented demo
practice: 43 made-up patients with results, letters and bookings. It never reads Best Practice,
so it needs no EDBA password. It can sit beside a live installation on the same PC.

**It is the [Windows live recipe](windows-live.md) with these differences.** Follow that page,
sections 1 to 5, and change only what is listed here.

## What to have ready: differences

| Item | Difference |
|---|---|
| The PC | Intel or AMD (x86-64), with 8 GB of memory or more: the demo's SQL Server takes up to 2 GB on top of MedUI. Allow about 2 GB more disk than a live installation, for SQL Server. |
| GitHub token | It must be able to read **two** repositories while both are private: `medui-au/medui` and `medui-au/medui_demodata`. The script checks both before installing anything. |
| EDBA password | Not needed. A demo is never connected to Best Practice. |
| A password for the demo users | New. One password, shared by all the demo's staff logins. Choose one you can give to trainees. |
| Microsoft's SQL Server licence terms | New. You are asked to accept them ([aka.ms/useterms](https://aka.ms/useterms)). SQL Server Express is free. |

## What it asks: differences

| Live recipe question | In a demo |
|---|---|
| 2. Live or demo? | **Answer `d`.** |
| 3. Instance name | Default becomes `medui_demo`. |
| 6. Ports | Defaults become 5006, 55433 and 5708, so a live instance's ports stay free. |
| 11. HTTPS for workstations | Say `y` if trainees will use their own PCs. **If a live installation on this PC already has HTTPS, type other ports here**, such as 8443 and 8080: 443 and 80 are taken, and the script may not notice. |
| 13. sqlcmd | Not asked. |

**Then, while it works,** two extra questions appear before the MedUI administrator one:

| Question | Notes |
|---|---|
| Do you accept Microsoft's SQL Server licence terms? (y/N) | Type `y`. Enter means no, and the installation stops there. |
| Password for the demo users | Asked once the demo databases are restored. |

## Check it worked

The summary box says `MedUI DEMO installed in WSL2`. Open `http://127.0.0.1:5006/` and log in
either way:

- as a demo user, by name, with the demo users' password: **Dr Imogen Thistlewood** (practice
  owner), Dr Callum Ravensworth (doctor), Rosalind Quenby (nurse), Tessa Wyndham-Lowe (reception);
- as the MedUI administrator you created.

## Afterwards

```powershell
wsl -d medui_demo
```

```bash
cd ~/medui_demo && ./medui.sh
```

| Step | How | Notes |
|---|---|---|
| Bring the dates up to today | `./medui.sh demo refresh` | Do this before each demonstration or recording, so results, visits and bookings look recent. |
| Change the demo users' password | `./medui.sh demo password` | |
| Workstations, OCR, AI | As the [Administrator setup guide](../setup-guide.md), leaving out Best Practice | With other ports, workstations open `http://<this PC's name>:8080` once, then `https://<this PC's name>:8443`. A PC already set up for the live installation needs the demo's setup too: each has its own certificate. |

Stopping, upgrading and removing work as on the [live recipe](windows-live.md#6-what-is-particular-to-windows),
with `medui_demo` in place of `medui`.

**A demo stays a demo.** Never point it at Best Practice, and `./medui.sh bp` refuses to. MedUI
keeps BP's patient and user numbers in its own database, so demo records would attach to
whichever real patients have the same numbers. For Best Practice, make a
[live installation](windows-live.md). More in the
[Administrator setup guide](../setup-guide.md#a-demo-installation).

[Back to installing MedUI](README.md)
