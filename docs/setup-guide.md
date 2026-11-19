# Administrator setup guide

**For:** whoever sets MedUI up for the practice and looks after it: the practice's IT provider
or administrator. **When:** after any [installation recipe](install/README.md) has finished. The
steps are the same whether MedUI runs in a WSL2 instance on a Windows PC or on an Ubuntu
computer; the recipe pages cover the few parts that differ. An administrator can also open this
guide in MedUI: **Admin → Application Setup → Administrator setup guide**.

Commands run in the MedUI folder (`~/medui_os` by default) on the Ubuntu or WSL2 computer, as the
install user, not root. Never paste `.env`, API keys, passwords or patient details into a ticket,
chat or AI tool.

## In order

| Step | What | Needed for |
|---|---|---|
| 1 | [Sign in](#1-sign-in) as the administrator the installer created | Everything |
| 2 | [Connect Best Practice](#2-best-practice-connection) | Patients, and BP staff logins |
| 3 | [HTTPS for the workstations](#3-https-for-the-workstations), if not done during the install | Using MedUI from any other computer, and the scribe's microphone |
| 4 | [OCR](#4-ocr-liteparse) | Reading scanned documents |
| 5–8 | [AI](#5-turn-on-ai): turn it on, add a provider, activate workflows, check the guardrails | AI features only; leave out if the practice won't use AI |
| 9 | [Other optional features](#9-other-optional-features) | Messaging, PIT export, patient API |
| 10 | [Backups](#10-backups) | Every live installation |

A demo installation leaves out step 2: see [a demo installation](#a-demo-installation).

## What the administrator needs

**The BP read-only (EDBA) password.** MedUI reads BP's SQL Server with a read-only database
login. Best Practice Software supplies its password under an Elevated Database Access Agreement
(EDBA) with the practice, for access to `BPSPatients`, `BPSDocumentsInbox` and all the
`BPSDocuments` databases. The practice applies to BP for the agreement; whether it is granted is
decided by Best Practice Software. BP then provides a script that creates the login. Have ready:
the server name (usually a named instance, such as `BPSERVER\BPSINSTANCE`), the login and its
EDBA password. MedUI installs and runs without it, but shows no patients.

**AI provider keys, only if the practice will use AI:**

| Key for | Used for | Without a key |
|---|---|---|
| A language-model provider: OpenRouter, OpenAI, Anthropic, Groq or DeepSeek | The AI assistant, chatbots, document summaries, the scribe's write-ups and other workflows | A local Ollama or LM Studio server on the practice network needs no key and keeps requests inside the practice. |
| A speech-to-text provider: Deepgram | The scribe: turning the consultation's audio into text. **It receives the recording unredacted** (below). | A local Whisper server needs no key and keeps the audio inside the practice. |

Text sent to a cloud language model is redacted first; MedUI refuses cloud models for workflows
that don't redact. **Audio is not redacted:** with a cloud speech-to-text provider such as
Deepgram, the consultation recording itself goes to that provider, names and all, because names
can't be removed from audio the way they can from text. The transcript that comes back is
redacted before it reaches a cloud language model. If the audio must stay inside the practice,
use a local Whisper server; with Deepgram, its Australian address (`https://api.au.deepgram.com`)
keeps the audio in Deepgram's Australian region. The policy template below has a line for
telling patients which is used before a consultation is recorded. One provider is enough to
start. Read the practice
[AI-use policy template](templates/practice-ai-use-policy.md) before turning AI on for clinicians.

**For the workstations:** the name of the MedUI computer on the practice network, and a fixed
address for it (or a DHCP reservation), for HTTPS.

## MedUI's menu

Most steps here have a command in MedUI's menu. Open a shell on the MedUI computer: on Windows,
`wsl -d medui` from PowerShell (`medui_demo` for a demo); on Ubuntu, log in as the install user.
Then:

```bash
cd ~/medui_os && ./medui.sh
```

`./medui.sh help` lists the same commands one per line, and each prints the command it runs, so
it can be repeated by hand ([cheat sheet](cheatsheet.md)).

## Two places settings live

| Where | What | How a change takes effect |
|---|---|---|
| `.env` in the MedUI folder | Database and BP connection, secrets, feature switches (`AI_ENABLED` and others), the practice's timezone (`PRACTICE_TIMEZONE`) | Recreate the app container: `./medui.sh reload`. A plain restart keeps the old values. |
| **Admin → Application Setup** in MedUI | OCR service, AI providers and models, users, messaging | Immediately |

`PRACTICE_TIMEZONE` is a place such as `Australia/Melbourne`, never an offset: daylight
saving then changes by itself. The installer asks for it from a menu, with Windows' (or the
computer's) own timezone offered; `./install.sh --timezone melbourne` (a city, a state such as
`vic`, or a zone name) changes it. **Admin → Application Setup → General → Practice Timezone**
changes it too, at once and without a terminal; a zone set there takes precedence over `.env`
("The installation's" goes back to the `.env` value). It sets MedUI's local time, so
"today" on the day sheet is the practice's today.

Apply a `.env` change by hand (what `./medui.sh reload` runs):

```bash
docker compose --profile app up -d --force-recreate app
```

## First-time setup

### 1. Sign in

Open `http://127.0.0.1:5005` on the MedUI computer (or, once HTTPS is set up, its HTTPS address
from a workstation) and sign in with the local administrator created during installation. BP
users can sign in once the BP connection works; practice owners and managers become
administrators.

### 2. Best Practice connection

**Use the read-only account BP supplies for database access** ([above](#what-the-administrator-needs)).
MedUI only reads, and it checks what its login may do: **Application Setup → Database** shows
whether the login is read-only in every database it can open. If the login could change data,
administrators see a notice on every page, and MedUI won't run SQL written in Query Manager or
Best Practice data sources until the login is changed.

**The BP login can read every database it has access to on that server**, not only the
one in `BPSDB_DATABASE`: several of MedUI's queries name BP's databases directly. For a
test, demo or training installation, use a SQL Server that holds only test data, never the
practice's live server. Two choices:
- **A demo installation** (`./install.sh --demo`, below): MedUI's own invented demo databases,
  [medui_demodata](https://github.com/medui-au/medui_demodata), in a SQL Server of the
  installation's own, set up in one step. This is the usual choice.
- BP's sample databases, restored under BP's usual names on a SQL Server holding nothing else.

The installer doesn't ask for the BP connection. Set it with:

```bash
./medui.sh bp
```

It asks for the server, the database (`BPSPatients`), the login, its password and whether to
trust the server's certificate (usually yes on a practice network), writes them to `.env`,
recreates the app and checks the login. `./medui.sh bp-check` checks it again later. Then check
**Application Setup → Database** in MedUI. BP staff can then log in with their BP names.

By hand, the same settings are the `BPSDB_*` lines in `.env`, followed by `./medui.sh reload`.
A named instance takes **one** backslash in `.env`:

```text
BPSDB_HOST=192.0.2.10\BPSINSTANCE
BPSDB_TRUST_SERVER_CERTIFICATE=true
```

The second line is the usual setting for BP's self-signed certificate on a practice
network. More in [troubleshooting](troubleshooting.md#best-practice-connection).

### 3. HTTPS for the workstations

MedUI answers only on its own computer until HTTPS is on. If the installation didn't turn it on,
`./medui.sh https` does; opening its ports to the practice network differs by platform (the
[Windows](install/windows-live.md#6-what-is-particular-to-windows) and
[Ubuntu](install/ubuntu-live.md#5-what-is-particular-to-ubuntu) recipes say how).

Then, on each workstation, open the setup page once: `http://<MedUI computer's name>`. It offers
a one-file setup that makes the workstation trust MedUI's certificate, then goes on to
`https://<MedUI computer's name>`. Windows with Chrome or Edge needs nothing more; Firefox on
Linux needs the certificate imported by hand in its settings. HTTPS is also what lets a
workstation's microphone be used for the scribe. For group policy, Intune, Macs, iPads and the
practice's own certificate, see [HTTPS](https.md).

### 4. OCR (LiteParse)

The installer starts the LiteParse container unless `--no-ocr` was used. In
**Application Setup → External Sources → + Add Service**:

| Field | Value |
|---|---|
| Display name | Local LiteParse |
| Service type | OCR |
| Base URL | `http://liteparse:5707` |

Leave the other fields blank and press **Test**: it should say "✓ LiteParse is
reachable". `127.0.0.1` inside the app container is the app itself,
and the host's LAN address doesn't reach LiteParse, because its port is published
on localhost only. Without a saved entry MedUI uses `OCR_SERVICE_URL` from the
environment. See [OCR](ocr.md).

### 5. Turn on AI

AI is off until it is switched on in `.env`. `./medui.sh features` asks about each optional
feature and recreates the app; `./medui.sh features AI_ENABLED=on` turns on AI alone. By hand:

```bash
grep -n '^AI_ENABLED' .env                                   # shows the current value
sed -i 's/^AI_ENABLED=.*/AI_ENABLED=true/' .env              # if the line exists
docker compose --profile app up -d --force-recreate app
```

If `grep` shows nothing, add the line with `echo 'AI_ENABLED=true' >> .env`
instead of the `sed` command. Until then, a provider's **Test** button reports "AI
features are disabled", and the AI menus and the document buttons ([TXT], [SUM],
[EXP]) are hidden or blocked. AI is available to doctors and administrators only.

Read the practice's [AI-use policy template](templates/practice-ai-use-policy.md)
before turning AI on for clinicians.

### 6. Add an AI provider and models

In **Application Setup → Providers**: add a provider from a preset (OpenRouter, OpenAI,
Anthropic, a local Ollama or LM Studio, and others), enter its API key, press
**Test**, then **Fetch Models** and choose the models the practice will use in
**Models**. Local providers keep requests inside the practice; cloud providers
receive only redacted requests.

### 7. Review and activate workflows

Seeded workflows install as **drafts with no model**. In **Admin → Pipeline
Designer**, open each workflow the practice wants, read its prompt, select a
**Model** on the inference step, and press **Activate**. The document buttons need
their own workflows: [SUM] runs *Document Summary* and [EXP] runs *Summarise
Document*.

A cloud model works only with workflows whose redaction policy is `redact_all`
(all seeded workflows are). `redact_pii_only` and `redact_none` are refused for
cloud models. See [seed data](seed-data.md).

### 8. AI guardrails (Application Setup → AI scope)

Three layers start **on** in this edition, and each can be changed here:

- **Scope instruction**: a short boundary placed before every workflow's system
  prompt, e.g. *Record — organise and summarise what the record says*, or *Scribe —
  write up only what was said*. Each seeded system prompt names its wording; the
  practice default (`record`) covers the rest. A reply the AI marks as out of scope
  is flagged on screen and recorded on the run. The wordings are editable here.
- **Request check**: what a user types is checked for requests outside a workflow's
  purpose (asking for a diagnosis, for example). Recorded only.
- **Notices**: the one-line note above AI output ("AI draft — check it against the
  record…"). Each workflow can choose its notice on its inference step.

**Pre-send review.** Before anything goes to a cloud model, the prompt is checked
for the patient's or a practitioner's identifiers. A hit holds the request on a
**Sending** tab (AI assistant, chatbots, scribe) to remove or edit it before it
goes; afterwards **Sent** shows what was sent. Users can also choose to review every
request, in **My settings** (top menu), where the practice's defaults and locks
(Application Setup → User defaults) apply.

### 9. Other optional features

`MESSAGING_ENABLED`, `PIT_EXPORT_ENABLED` and `PATIENT_API_ENABLED` are switched on
in `.env` the same way as AI (`./medui.sh features`), and are configured in Application Setup.

### 10. Backups

```bash
./medui.sh backup
```

It backs up the database (and reads the dump back to check it), a copy of `.env`, the app's data
and, with HTTPS on, the `https` folder, into `backups/` in the MedUI folder. `./medui.sh backups`
lists them. `.env` holds the encryption key: encrypted records can't be recovered without it, so
keep the backups as safe as the database itself. A backup on the same computer is not enough:
**store another copy off the computer**, and rehearse a restore before you need one
([operations](operations.md#backup)). `./upgrade.sh` makes its own backup before every upgrade.

## A demo installation

For demonstrations, training and screen recordings; the recipes are
[Windows PC, demo](install/windows-demo.md) and [Ubuntu, demo](install/ubuntu-demo.md). A demo installation reads MedUI's invented
demo databases ([medui_demodata](https://github.com/medui-au/medui_demodata): a fictional
practice in Sampleford, with 43 patients, their results, letters and bookings; every row is
made up) in a SQL Server 2022 Express container of its own, and never Best Practice.

```bash
git clone <repository> ~/medui_demo && cd ~/medui_demo
./install.sh --demo
```

A new installation without `--demo` asks whether it is live or a demo; `--demo` answers that
for it. With `--yes` (scripts and agents) it is live unless `--demo` is given.

On Windows, `create_medui_wsl2.ps1` asks first whether the installation is live or a demo:
answer `d`, and the demo gets an instance (`medui_demo`), folder and ports of its own.

What `--demo` does, besides an ordinary installation:
- It asks you to accept Microsoft's SQL Server licence terms ([aka.ms/useterms](https://aka.ms/useterms)),
  once. SQL Server Express is free; its usage reports to Microsoft are turned off in its settings.
- It starts SQL Server (service `bpsql`, about 1.6 GB to download, up to 2 GB of memory). It has no
  port on the computer: only this installation's containers reach it.
- It downloads medui_demodata into `demodata/`, restores its three databases, and creates a
  read-only login that it writes to `.env` with the server (`BPSDB_HOST=bpsql`). While
  medui_demodata is private, give a GitHub token that can read it, as for upgrades
  ([operations](operations.md#upgrades)): `MEDUI_GIT_TOKEN`.
- It asks for one password for all the demo users. They log in by name on MedUI's login page:
  Dr Imogen Thistlewood (practice owner), Dr Callum Ravensworth (doctor), Rosalind Quenby
  (nurse), Tessa Wyndham-Lowe (reception) and others.
- It brings the data's dates up to today, so results, visits and bookings look recent.

Afterwards, `./medui.sh demo` shows the demo data, `./medui.sh demo refresh` brings the dates
up to today again (before a demo or a recording), and `./medui.sh demo password` sets a new
password for the demo users.

**A demo stays a demo.** MedUI keeps Best Practice's patient and user numbers in its own
database, with no record of which server they came from. So `install.sh` won't turn an existing
installation into a demo, and on a demo `./medui.sh bp` refuses: demo records would attach to
whichever real patients have the same numbers. For BP, use an installation of its own. A demo
and a live installation can share a computer (their own folders, names and ports); only one
can have HTTPS on port 443, and `./medui.sh use` switches which one runs.

## Updating MedUI

In the MedUI folder, `./upgrade.sh` does the whole update: it shows what's new, backs
up the database, settings and app data, builds the new version while the current one
keeps running, then upgrades the database, lists the seed changes for you to accept,
and starts MedUI. `./upgrade.sh --dry-run` shows the plan; `--to <tag>` picks a
release. If a step fails, it prints the commands that put the previous version back.
On Windows, `scripts/windows/upgrade_medui_wsl2.ps1` can also save a snapshot of the
whole WSL instance first ([Windows](../scripts/windows/README.md)).

The version shown at the foot of each page should then match the release. The steps by hand,
and the private-repository token: [operations](operations.md#upgrades). Prompts or workflows
you have edited are kept when the seeds are updated: [seed data](seed-data.md#after-an-upgrade-seed-resync).

## When something goes wrong

`./medui.sh status` shows what is running and its health, `./medui.sh logs` the app's recent
output, and `./medui.sh support` a summary to copy into a question, with no data or secrets.
Logs can contain patient details: share the error line, not the whole log.

[Troubleshooting](troubleshooting.md) has the symptoms and fixes, including every page giving a
500 error after `.env` was replaced or edited
([the database password](troubleshooting.md#set-the-database-password-to-the-one-in-env)).

## More help

- [Installing MedUI](install/README.md): the four installation recipes
- [Troubleshooting](troubleshooting.md): symptoms and fixes, the Windows installer,
  administrator access, starting fresh
- [Operations](operations.md): backups, restore and upgrades
- [HTTPS](https.md): access from workstations, certificates, trusting the MedUI root
- [OCR](ocr.md): LiteParse details
- [Seed data](seed-data.md): what the starter pack contains
