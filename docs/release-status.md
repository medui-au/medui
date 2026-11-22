# Release status

**Version 0.57.0, pre-release (November 2026).** Synced with the upstream MedUI application, with
the redaction core 0.2.20. Scope: a new practice installation, not migration of existing MedUI data.
Each release is described in the [changelog](../CHANGELOG.md); this page is the summary of what
is in place and what is left before a release to another practice.

## In place

**Installing and running**
- Four installation recipes, one script each: Windows (a new WSL2 instance) or Ubuntu, live
  or demo ([installing MedUI](install/README.md)), and the
  [Administrator setup guide](setup-guide.md) that follows every one.
- `install.sh`, safe to run again; ports on localhost only; fresh secrets in `.env`. A second
  installation on the same computer gets its own folder, name and ports.
- `./medui.sh`: a menu, or one command at a time, for everyday tasks (status, the BP connection,
  optional features, HTTPS, backups, upgrades, logs, removing an installation).
- `upgrade.sh`: upgrade in place with a verified backup, the new image built before the app
  stops, the seed changes shown before they're applied, and the commands to go back printed if a
  step fails. On Windows, `upgrade_medui_wsl2.ps1` can first take a snapshot of the whole
  instance.
- HTTPS for workstations: Caddy on 443, with the practice's own certificate or a MedUI root
  restricted to MedUI's names, and a setup page that gives each workstation a one-file setup
  ([HTTPS](https.md)).
- Demo installations (`./install.sh --demo`): MedUI's invented demo practice in a SQL Server of
  their own, never BP.
- The practice's timezone is MedUI's local time; backups, restore and upgrades are documented
  ([operations](operations.md)).

**Clinical functions and AI**
- Reads Best Practice through a read-only connection, checks that the login is read-only, and
  never writes to BP.
- AI, outbound messaging, PIT delivery and the external data APIs are off until switched on.
  Seeded workflows arrive as drafts with no model.
- Redaction is the `bps-redaction` core, the same version as upstream's, with a pre-send check and
  review before any cloud AI request. Nurses and reception log in without AI. Cloud
  speech-to-text receives the consultation audio unredacted; a local Whisper keeps it in the
  practice.
- Seeded prompts confined after the wording audit: no result grading, risk classification,
  targets, or screening and vaccination advice. Results are shown with the laboratory's own
  flags and ranges. The HbA1c and eGFR results badges are rules each user chooses to display
  (off until ticked); the criterion review, a record-coding audit, is included but **off**.
  FIB-4 and the NIP line show their formula or schedule, inputs and source.
- The intended purpose names what MedUI is for and not for, including published calculations,
  record-quality audits and rules a user chooses to display ([intended purpose](intended_purpose.md)).
- Off-label guard in the general chatbot, and a list of flagged requests for the practice
  (**Admin → Flagged AI Requests**).
- Governance: a usage record (Application Usage, My Usage) and a privacy review of what was
  sent.

**Intended purpose and documentation**
- [Intended purpose](intended_purpose.md), quoted unchanged in the README, AGENTS.md and the
  app's About page; it includes the practice's responsibility for prompts it writes itself.
- In-app help with search and **?** buttons on the main screens, checked by `flask help check`.
- [SECURITY.md](../SECURITY.md), [getting help](support.md), and the release checklist and wording
  rules ([releasing](maintainers/releasing.md)).

## Tried on real installations

- **Windows (WSL2, Ubuntu 24.04):** installed with the Windows script on several PCs, live and
  demo, with HTTPS trusted on other Windows PCs through the setup page; connected to a live Best
  Practice database with a read-only login; upgraded in place with `upgrade_medui_wsl2.ps1`, including a
  whole-instance snapshot.
- **Ubuntu 26.10 on its own computer:** installed with `install.sh`, without issues.
- **Demo:** installed from MedUI's demo databases, and earlier from BP's sample databases.
- **The development host:** fresh installs, re-runs with data unchanged, upgrades and rollbacks
  rehearsed on throwaway installations, HTTPS end to end.
- **Tests:** 612 passing, including the database tests against a throwaway PostgreSQL.

No claim of clinical validation is made by these installation and startup tests.

## Before release to another practice

**Regulatory and intended purpose** (TGA position: plans kept with the maintainers)
- The AI information sheet in the docs, with version and support contact.
- Seeded prompt wording against the intended purpose (cited guideline content, no tailoring to
  the patient), after testing old and new wording side by side.

**Validation**
- Validate seeded drug and vaccine identifiers and clinical rules for receiving practices.
- Review inherited clinical prompt wording, and validate the AI workflows a practice
  activates.
- The microphone over HTTPS from a workstation, and each workstation's own address in the
  usage record.

**Product**
- **Choose the distribution licence: decided last**, after the discussion with Best Practice
  (which may affect how the queries are distributed). Until then the code is all rights
  reserved ([LICENSE](../LICENSE)), and to keep every option open:
  - dependencies stay permissive or weak copyleft: `test_dependency_licences` fails on a new
    GPL or AGPL dependency, so adding one is a deliberate decision;
  - no outside contributions without a short contributor agreement;
  - no code copied in from GPL projects;
  - a trial at another practice has written permission (use, confidentiality, no
    redistribution).
- A final review of the [request to BP for database access](templates/bp-database-access-request.md)
  template, wording and tone, before practices use it.
- The public copy: a fresh history, its name and owner, and turning on private vulnerability
  reporting for [SECURITY.md](../SECURITY.md).
- Check every role and access path; finish the optional features' screens.
- Define supported hosts and resources from measured use (a WSL2 instance with 4 GB of
  memory has run MedUI with OCR).
