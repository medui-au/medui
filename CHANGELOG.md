# Changelog

MedUI's releases. The version is in `app/version.py`, shown at the foot of every page and in
`/health`. See [releasing](docs/maintainers/releasing.md).

## 0.61.4 — public pre-release (November 2026)

**Upgrade from 0.61.3**: `./upgrade.sh`. Nothing in the app changes.

- **Releasing** ([releasing](docs/maintainers/releasing.md#publishing)) says how each release is
  published to `medui-au/medui`: one commit per release, tagged `vx.y.z`, never force-pushed;
  `./upgrade.sh --to vx.y.z` goes to one release.

## 0.61.3 — public pre-release (November 2026)

**Upgrade from 0.61.2**: `./upgrade.sh`. Nothing in the app changes.

- **No GitHub token needed**: the repositories are public, so the install recipes, upgrades,
  cheat sheet, setup guide, troubleshooting and the Windows scripts' guide drop the "while the
  repository is private" token steps. At the Windows script's token question, press Enter. The
  scripts still accept a token, for a private copy.
- **Release status** now describes the public pre-release and what is left before 1.0.
- **Diagrams of how data moves**, on a page of their own without the technical detail
  ([how data moves](docs/how-data-moves.md), linked from the README and how MedUI is built): where
  data goes, the guards on one AI request, and the switches and fixed guards. The guards diagram is
  also in the [AI information sheet](docs/ai-information-sheet.md). The in-app guide shows them too.
- **Contributing** ([CONTRIBUTING.md](CONTRIBUTING.md), linked from the README and getting help):
  questions, issues and ideas welcome; code contributions not accepted yet, until a contributor
  agreement is in place (to keep the option of licensing MedUI on other terms).

## 0.61.2 — pre-release (November 2026)

**Upgrade from 0.61.1**: `./upgrade.sh`. Nothing to migrate.

- **The intended-purpose statement's last sentence is split in two**, so it can't be read as
  MedUI providing clinical judgement: "It provides information. Clinical judgement, decisions
  about a patient's care and the record remain with the health professional." The meaning and
  scope are unchanged. Updated in docs/intended_purpose.md, the README, AGENTS.md, the About page
  and the AI information sheet.
- **AI information sheet:** the chatbot with no patient is called the generic chatbot throughout
  its section, and "no patient context" replaces "no patient" (Chatbot Generic, the Library
  workflow, the recipe assistant).

## 0.61.1 — pre-release (November 2026)

**Upgrade from 0.61.0**: `./upgrade.sh`. Nothing to migrate.

- **New OpenRouter and Groq providers start with their models URL** (upstream ADR-191). Added
  from its preset, an OpenRouter provider fetches OpenRouter's zero-data-retention list
  (`https://openrouter.ai/api/v1/endpoints/zdr`), so only models whose providers don't keep the
  requests are offered; a Groq provider fetches `https://api.groq.com/openai/v1/models`. The
  Models URL can be changed or cleared; its hint now shows each provider's own URL. Providers
  already set up are not changed.
- **Messaging setup placeholders** use example domains and an invented practice name.

## 0.61.0 — pre-release (November 2026)

**Upgrade from 0.60.1**: `./upgrade.sh`. Nothing to migrate. A MINOR release: chats gain a
retention period.

- **Chats have a retention period** (upstream ADR-189). Application Setup → Maintenance → Data
  retention has a fourth window, **Chats (days)**, 90 to start. When an administrator presses
  **Purge**, chatbot conversations with no activity in that time are deleted with their messages
  and generated files, whether still open, ended with **New conversation** or removed from the
  list (removing one from the list only hides it). Before this, chats were never deleted. Chats are
  stored with the patient's details restored, so they aren't kept indefinitely; anything worth
  keeping belongs in Best Practice. The AI run records only those chats referred to go in the same
  purge. The purge preview counts chats, and the chatbot help says conversations are deleted after
  the practice's period.
- **Maintenance tab rearranged** (upstream ADR-190): Staff Privacy and Privacy Review first, with
  **Save Privacy Settings**; then Data Retention, with **Save Retention**, directly above
  **Purge**. Each Save changes only its own settings. After a Save the purge preview now shows
  its counts instead of "Loading purge preview…".
- **AI information sheet:** "For the practice" says what MedUI keeps, how long, and what the
  usage record keeps without a patient reference.

## 0.60.1 — pre-release (November 2026)

**Upgrade from 0.60.0**: `./upgrade.sh`. Nothing to migrate.

- **Purge works when old AI runs are still in use** (upstream ADR-188). Application Setup →
  Maintenance → **Purge** failed, deleting nothing, as soon as an old AI run record was still
  referred to by a chat reply, care plan, GPCCMP session, patient message or privacy report.
  Purge now keeps those runs, so the record keeps its AI detail, and the preview and the result
  say how many were kept. They become eligible once nothing refers to them.
- **"Enable automatic daily cleanup" removed.** The switch was saved but nothing used it; purging
  is done with **Purge**, when the administrator chooses. The Maintenance tab no longer shows
  amber for it, and a new installation no longer adds the setting.

## 0.60.0 — pre-release (November 2026)

**Upgrade from 0.59.8**: `./upgrade.sh`. Nothing in the app changes. A MINOR release: the
intended purpose is reworded.

- **Intended purpose: guidance is shown with its source.** "shows what named published guidance
  says when they ask" becomes "shows what named, published guidance says, with its source, when
  they ask", in [intended purpose](docs/intended_purpose.md), the README, AGENTS.md, the
  [AI information sheet](docs/ai-information-sheet.md) and the About page. This matches the full
  statement's Reference entry, which already shows the source. The statement is now:

  > MedUI is a workflow tool for appropriately registered health professionals working in a
  > medical practice. It helps them find, organise, present, summarise and document information
  > that is already in the patient record or was stated in the consultation, shows what named,
  > published guidance says, with its source, when they ask, and streamlines practice
  > communication and administration. AI features produce drafts for the health professional to
  > review, edit and approve. MedUI does not diagnose, recommend treatment or investigations,
  > triage or monitor patients; it provides information, and clinical judgement, decisions about a
  > patient's care and the record remain the health professional's.

## 0.59.8 — pre-release (November 2026)

**Upgrade from 0.59.7**: `./upgrade.sh`. Nothing in the app changes.

- **Asking and reporting on GitHub**: three issue forms (something isn't working, a doc that's
  wrong or unclear, a suggestion), each with a required tick that it holds no patient details. A
  blank issue isn't offered; the new-issue page points security problems to private reporting and
  questions to Discussions. The README and [getting help](docs/support.md) say where each goes.

## 0.59.7 — pre-release (November 2026)

**Upgrade from 0.59.6**: `./upgrade.sh`. Nothing in the app changes.

- **Where the redaction core lives**: the README, NOTICE, AGENTS.md, the technical overview, the
  release status and `requirements.txt` link to its source,
  [medui-au/redaction-core](https://github.com/medui-au/redaction-core).

## 0.59.6 — pre-release (November 2026)

**Upgrade from 0.59.5**: `./upgrade.sh`. No migrations.

- **Redaction core 0.2.21**: comments, docs and packaging only (a SECURITY.md, the licence and
  NOTICE inside the wheel). No rule changes: redaction behaves exactly as in 0.2.20.

## 0.59.5 — pre-release (November 2026)

**Upgrade from 0.59.4**: `./upgrade.sh`. Nothing in the app changes.

- **AI information sheet**: the practice's responsibility to choose providers, a cloud
  speech-to-text service included, that don't train on or keep its data; and who does what in the
  care plan (the doctor, MedUI without AI, the AI), set out step by step; and where the data source charts' AI Analytics tab is.

## 0.59.4 — pre-release (November 2026)

**Upgrade from 0.59.3**: `./upgrade.sh`. No migrations.

- **Help ▾ in the top bar**, with **Help** (the guide) and **About** (the version running and
  MedUI's intended purpose). The version also stays at the foot of every page.
- **Results Rollup**: a **Deselect all** link beside the count, and the button now reads **Copy
  to Clipboard**.

## 0.59.3 — pre-release (November 2026)

**Upgrade from 0.59.2**: `./upgrade.sh`. Nothing in the app changes.

- **The AI information sheet** ([docs/ai-information-sheet.md](docs/ai-information-sheet.md)). It
  covers every AI function MedUI ships: what each is for, what it reads, where it can run (local or
  cloud) and its limits. It also covers the intended purpose and regulatory status, what isn't AI,
  and what the practice does before switching AI on. A test checks that it names every seeded
  workflow and carries the release's version.

## 0.59.2 — pre-release (November 2026)

**Upgrade from 0.59.1**: `./upgrade.sh`. No migrations.

- **COVID-19 NIP eligibility** (schedule as updated 1 October 2026). For 65–74 and Aboriginal and
  Torres Strait Islander adults 50–74, the note now says the schedule allows a second dose in the
  year with a medical risk condition. For adults 18–64 with severe immunocompromise, it says a
  second dose in the year is allowed. Adults 18–64 without severe immunocompromise get their own
  not-funded note, which says the schedule lists a dose each year as an option. When a dose is
  shown as due is unchanged.

## 0.59.1 — pre-release (November 2026)

**Upgrade from 0.59.0**: `./upgrade.sh`. No migrations.

- The **[EXP]** links beside documents and results are no longer shown; [SUM] and [TXT] are
  unchanged. The wiring is kept for a future purpose: `EXP_LINKS_ENABLED=true` in `.env` (then
  recreate the app container) shows them again. While it is off, an [EXP] address starts nothing.

## 0.59.0 — pre-release (November 2026)

**Upgrade from 0.58.1**: `./upgrade.sh` runs one migration (two new tables only). A policy already
saved becomes version 1 the first time it is opened. A MINOR release: a new function.

- **AI-use policy versions** (Governance → AI-use policy). Every save is kept as a numbered version,
  with an optional note of what changed and **Appendix A as it was at that moment**. **Versions**
  lists them; any version opens, prints and downloads exactly as it was. An administrator approves
  the latest version once, with the next review date and a ticked confirmation. **Start again from
  the template** now opens the template in the editor and removes nothing.
- Versions are kept in a general store for the practice's own documents (`practice_documents`,
  `practice_document_versions`). Today it holds only the AI-use policy.
- The template no longer asks the practice to keep copies in its document management. The docs copy
  has a short header pointing to MedUI.
- The suggested wording for the request to Best Practice for database access is final.

## 0.58.1 — pre-release (November 2026)

**Upgrade from 0.58.0**: `./upgrade.sh`. Nothing in the app changes.

- The suggested wording for the request to Best Practice for database access is shorter and plainer:
  one paragraph saying what the access is for, how AI is used, and that the application only reads.

## 0.58.0 — pre-release (November 2026)

**Upgrade from 0.57.2**: `./upgrade.sh`. No migrations: the condition codes table gets its new column
the first time it is read.

- **Condition names without BPSDrugs.** Admin → Mapping Tables → condition_codes names each code in
  two columns, for reading only. **bp_item**: Best Practice's dictionary names, which need read
  access to `BPSDrugs`. **practice_item** (new): the wording most often recorded for the code in the
  practice's own past history, from `BPSPatients`, taken only when at least 3 entries use it. Each
  fills on its own and stays blank if its source can't be read. Which codes count as each condition
  is unchanged: always the item code.
- The request to Best Practice for database access no longer asks for `BPSDrugs`: MedUI needs only
  `BPSPatients`, `BPSDocumentsInbox` and the `BPSDocuments` databases.

## 0.57.2 — pre-release (November 2026)

**Upgrade from 0.57.1**: `./upgrade.sh`. Nothing in the app changes.

- NOTICE gives an additional permission (AGPL section 7) to combine MedUI with Microsoft's ODBC
  Driver for SQL Server, names that driver and its licence terms, and lists the services MedUI runs
  beside it (PostgreSQL, LiteParse, Caddy, and SQL Server for the demo) with their licences.
- `install.sh` and `upgrade.sh` say, before they build MedUI's image, that the build accepts Microsoft's licence
  terms for the ODBC driver.

## 0.57.1 — pre-release (November 2026)

**Upgrade from 0.57.0**: `./upgrade.sh`. Nothing in the app changes.

- **Licence: GNU Affero General Public License v3** (LICENSE). Copyright, the third-party
  components (the redaction core is under the Apache License 2.0) and what the licence asks if you
  change MedUI are in NOTICE.

## 0.57.0 — pre-release (November 2026)

**Upgrade from 0.56.0**: `./upgrade.sh`. No migrations. The seed resync adds the guidelines the
protocol setup wizard cites to the guideline library (new ones only). A MINOR release: a new function.

- **Protocol setup wizard** (Admin → Practice Protocols → Set up with the wizard): builds a first
  practice protocol from one question per measure and patient group. The options come from
  Australian guidelines, each with its section and a short quote. Example condition wording
  (de-identified) and prevention lines can be kept or dropped. Nothing is pre-chosen and every
  question needs an answer. The result is a **draft**, which the practice reads, edits and approves.
  Still no protocol is shipped.
- **Guideline library**: `install seeds`, `install resync-seeds`, `flask protocol seed-guidelines`
  and a button on the Guidelines tab add those guidelines, new ones only.
- **Approve** now needs a sign-off: the version has been read through, and it is the practice's own,
  reviewed decisions.
- A patient's targets screen lists each target option once, even when the protocol uses it for
  more than one patient group.

## 0.56.0 — pre-release (November 2026)

**Upgrade from 0.55.1**: `./upgrade.sh` runs the three new migrations (new tables only) and the seed
resync, which adds the GPCCMP drafting workflow as a draft with no model. A MINOR release: new
functions and new seeded prompts.

GP Chronic Condition Management Plans, built so that every clinical decision is the doctor's,
recorded as data, and the AI only words the plan:

- **Practice protocols** (Admin → Practice Protocols): the practice's own target options per
  measure, with the guidelines behind them and a rule that preselects an option from conditions
  **coded** in the record; condition wording; prevention lines MedUI works out from age, sex and
  coded history; a guideline library; draft and approve versions with a review date; a printable
  decision record generated from the protocol; and a list of targets to review when an option
  changes or a guideline is superseded. **No protocol is shipped**: each practice builds its own.
- **Patient targets** (Patient Data → GPCCMP: Targets & Plan, and Targets in Patient Tools): each
  patient's targets, set by their doctor (nurses can see them), with the protocol default
  preselected and its reason, guideline background, individual targets, and a history that is
  never overwritten. The latest result is shown beside each target, only from a result token that
  measures it.
- **Plan decisions**: plan type (billing eligibility shown as a fact), issues ticked from coded
  conditions, directions, services, modifiers, review interval and consent, all the doctor's;
  carried forward from the patient's last plan (never the consent); reviews record a progress word
  per issue beside each target and its last value.
- **AI draft** (needs AI switched on): **Proceed with GPCCMP** saves, checks and drafts with the new
  workflow, with a model choice per draft. The AI writes only each issue's wording and the
  safety-netting; MedUI writes the history, targets, prevention, review and consent itself, checks
  the AI's text against the decisions (issues, services, no targets, judgements, consent or doses
  of its own) and opens an ordinary care plan draft.
- **Care plans**: BP → sends the plan to Best Practice as a PIT file in place, with a brief tick;
  the printed and sent plan leaves out blank lines and the draft's source tags; the header adds the
  emergency contact (else the next of kin) with phone numbers.
- **Disease Profile**: familial hypercholesterolaemia and revascularisation are new coded
  conditions, with badges.
- **Recipe AI assistance** can choose the model for a run.
- **AI-use policy** template: a paragraph on practice protocols.

## 0.55.1 — pre-release (November 2026)

**Upgrade from 0.55.0**; nothing to migrate or resync. A PATCH release.

- **HbA1c badge in %.** The optional HbA1c badge (My settings → Patient record) now shows its 3
  results in %. A result the laboratory reported in mmol/mol is converted with the IFCC–NGSP
  master equation (% = 0.09148 × mmol/mol + 2.152, one decimal), and the tooltip gives the
  laboratory's own value beside it. Whether the badge shows is still decided in each result's own
  unit, so rounding never changes it. Help: Patient record.

## 0.55.0 — pre-release (November 2026)

**Upgrade from 0.54.0**; nothing to migrate. Afterwards run `flask install resync-seeds --dry-run`,
then without `--dry-run`, for the renamed document-summary prompt (below). A MINOR release: the
intended purpose is reworded.

- **Intended purpose reworded** ([intended purpose](docs/intended_purpose.md); the same statement
  in the README, AGENTS.md and the About page):

  > MedUI is a workflow tool for appropriately registered health professionals working in a
  > medical practice. It helps them find, organise, present, summarise and document information
  > that is already in the patient record or was stated in the consultation, shows what named
  > published guidance says when they ask, and streamlines practice communication and
  > administration. AI features produce drafts for the health professional to review, edit and
  > approve. MedUI does not diagnose, recommend treatment or investigations, triage or monitor
  > patients; it provides information, and clinical judgement, decisions about a patient's care
  > and the record remain the health professional's.

  The full page now names what MedUI is for, including simple published calculations and
  schedules, record-quality audits and rules a user chooses to display (each shown with its
  values, rule and source), and what it is not for.
- **Results badges are each user's own choice.** The Disease Profile's HbA1c and eGFR badges
  are no longer switched on for the practice in Application Setup → General. Each user ticks
  them in **My settings → Patient record**; they are off until ticked, shown only to that user,
  and the practice can't set or lock them. Each tick box is worded as its rule:
  - HbA1c, for adults where diabetes isn't coded: the highest of the last 3 results is 6.5%
    (48 mmol/mol) or more. The badge shows the 3 results with their dates.
  - eGFR, where CKD isn't coded: the last result is below 59. A result of exactly 59 doesn't
    show it, although KDIGO's G3a (below 60) includes 59.
- **Criterion review** (Doctor Data, still off unless the practice switches it on) is worded as a
  record-coding audit: results that meet a published criterion where the condition isn't coded.
  Its criteria are unchanged and now differ from the badges'.
- **The NIP line** beside Immunisations is grey, gives each vaccine's last recorded dose, and its
  tooltip names the 2026 NIP schedule and its source. The Vaccine Eligibility data block carries
  the same schedule line.
- **FIB-4 is shown as MedUI's calculation.** The chart says it is calculated by MedUI, not the
  laboratory, with its formula, how its inputs are chosen and its source (Sterling et al., 2006);
  each point shows its age, AST, ALT and platelets. AI workflows receive it labelled the same way,
  with its inputs, and **without the 1.45 cut-off and flag** they carried before; the results
  trends no longer flag it either.
- **AI-use policy template:** new paragraphs on the questions users type, guideline content
  suggested by AI, prompts and care-plan recipes the practice writes, and medicolegally
  sensitive discussions, which the practitioner documents personally. A policy the practice
  has already saved keeps its own wording; compare it with the template.
- **Document summary label:** the prompt behind the **[EXP]** links is renamed *Summarise
  Clinical Document (with record context)* and its workflow is no longer described as
  explaining the document; the prompt text and the links are unchanged. The resync adds the
  renamed prompt, points the workflow at it if the practice hasn't edited it, and lists the old
  name as dropped (archive it with `--archive-dropped` once checked).

## 0.54.0 — pre-release (November 2026)

**Upgrade from 0.53.5**; nothing to migrate. `./upgrade.sh` rebuilds the OCR container, which
takes a few minutes longer than usual the first time.

- **OCR uses LiteParse 2.20.0** (was 2.4.0). Reference ranges in brackets, such as "(3.5-5.2)",
  are now kept when a scanned results table is read, and text in columns is laid out more
  cleanly. On invented test documents, every number was read the same as before or better.
  The OCR server and how MedUI talks to it are unchanged.

## 0.53.5 — pre-release (November 2026)

**Upgrade from 0.53.4**; nothing to migrate.

- **Scanned images are read more accurately.** Before OCR, MedUI turns an image (TIFF, JPEG, PNG)
  into a PDF. It made each page as if the image were 72 dpi, so a 200 dpi scan became a page
  nearly three times too large, and OCR read it worse. Pages now keep the scanner's resolution,
  or are taken as A4 wide when the image doesn't say (a phone photo). On an invented two-page
  TIFF, 55 of 57 numbers are now read right, against 52 before.

## 0.53.4 — pre-release (November 2026)

**Upgrade from 0.53.3**; nothing to migrate.

- **Glucose results with LOINC 14768-6 now reach the AI context and trends.** Labs send this
  code as plain "Glucose", usually fasting. Pathology and compact pathology in the patient
  summary, and pathology trends, listed only 14771-0 (fasting glucose), so these results were
  left out. Random glucose (14749-6) is still left out.

## 0.53.3 — pre-release (November 2026)

**Upgrade from 0.53.2**; nothing to migrate.

- **A second Ollama (or any second server of the same kind) can be added from its preset.**
  Adding it did nothing: it needed an internal key of its own, and the page didn't show the error.
  It now gets `ollama_2`, `ollama_3` and so on. Give each one its own display name, such as the
  server it runs on.
- When a provider can't be added (a display name or custom key already used, no preset chosen),
  Setup → AI Providers says why above the list.

## 0.53.2 — pre-release (November 2026)

**Upgrade from 0.53.1**; nothing to migrate.

- **A long practice name no longer covers the top of the page.** The name in the top bar takes at
  most two lines (smaller type for long names, ending in "…" if it still doesn't fit), and shows in
  full when you hover over it.

## 0.53.1 — pre-release (November 2026)

**Upgrade from 0.53.0**; nothing to migrate.

- **`./medui.sh pit` works with an account given without a domain.** It stopped at "Couldn't
  write …credentials" after writing the file, before making it readable by root only. The file
  is now created root-only from the start. If 0.53.0 stopped there, delete the file
  (`sudo rm -f /etc/medui/<installation>_pit.credentials`) and run `./medui.sh pit` again.

## 0.53.0 — pre-release (November 2026)

**Upgrade from 0.52.5**; nothing to migrate. If PIT export is on, run `./medui.sh pit` after
upgrading: sending to Best Practice needs its share connected as `/pit` (below).

- **`./medui.sh pit` connects Best Practice's PIT folder.** BP imports PIT files from a share on
  the practice network, but the app runs in a container that sees none of this computer's
  folders, so no folder setting could reach it. The command asks for the share and a Windows
  account, mounts the share (password in a root-only file; in `/etc/fstab`, so it is mounted again
  after a restart), passes it to the app as `/pit` (`PIT_HOST_DIR` in `.env`), sets Setup's PIT
  folder to `/pit` and checks MedUI can write there. `pit status`, `pit test` and `pit off` look
  after it later; `./medui.sh remove` disconnects it. A demo installation refuses: its files carry
  the demo's patient numbers.
- **MedUI never creates the PIT folder.** A Windows path (`\\SERVER\share`), a mistyped path or
  an unmounted share used to make a local folder, and PIT files went there, logged as written,
  where BP never read them. Now sending to BP fails with the reason, **Save** in Setup → Messaging
  says what is wrong, and the home page's installation status checks the folder.
- Setup's hint names `/pit` and `./medui.sh pit`; the Administrator setup guide has a section on
  the PIT folder, and troubleshooting a row.

## 0.52.5 — pre-release (November 2026)

**Upgrade from 0.52.4**; nothing to migrate.

- **SMS text goes to the gateway as plain text.** Some email-to-SMS gateways accept a message
  with characters outside plain ASCII and then never deliver it, without an error. Dashes, curly
  quotes, the ellipsis, bullets and special spaces now become their plain equivalents, and accented
  letters lose their accents, before every SMS is sent. The patient's message record keeps the text
  as written.
- Setup → Messaging → **Test SMS** sends a plain-text message, so it arrives through such a gateway.

## 0.52.4 — pre-release (November 2026)

**Upgrade from 0.52.3**; nothing to migrate.

- **Setup → Messaging → Save SMS Settings works.** It failed on every save, so the SMS gateway
  settings were never stored and the page showed no error. Email settings were not affected.

## 0.52.3 — pre-release (November 2026)

Documentation only. **Upgrade from 0.52.2**; nothing to migrate, and nothing in the app changes.

- The install recipes give the time to allow: about 30 minutes to install a live installation,
  and about 30 more to set it up for the practice if it already has its EDBA account; 30 to 40
  minutes for a demo.
- The Ubuntu demo recipe says the folder's name becomes the installation's name, and that only
  `medui_os` is refused for a demo.

## 0.52.2 — pre-release (November 2026)

Documentation only. **Upgrade from 0.52.1**; nothing to migrate, and nothing in the app changes.

- Each of the four install recipes now stands alone. It opens with a short box: when to use it,
  which recipe to use instead, the script (with a download link for the Windows script), what the
  computer needs, and the commands to run. The two demo recipes no longer send the reader to the
  live ones for the steps. A test keeps the commands the pages share the same.

## 0.52.1 — pre-release (November 2026)

Documentation only. **Upgrade from 0.52.0**; nothing to migrate, and nothing in the app changes.

- The changelog no longer names the private upstream application, and a test keeps every file
  that way.

## 0.52.0 — pre-release (November 2026)

**Upgrade from 0.51.1**; nothing to migrate.

- **Governance → AI-use Policy: the practice's own policy, in MedUI.** Everyone signed in can read
  it; administrators adapt it with **Edit** (Markdown), starting from the template, and can start
  again from the template. Its Appendix A lists the AI providers and models enabled at the moment
  it is opened, printed or downloaded. **Print or save as PDF** and **Download (.md)** keep dated
  copies for the practice's document management. The page shows who last changed it and when.
  Synced from upstream.
- The [AI-use policy template](docs/templates/practice-ai-use-policy.md) in the docs is the same
  text the Governance page starts from; the in-app guide still shows it with the live appendix.

## 0.51.1 — pre-release (November 2026)

**Upgrade from 0.51.0**; nothing to migrate.

- **The top menu reads Home, Daysheet, Patient Data, User Data, Doctor Data, Governance, Charts,
  Admin.** The Reception item, which did nothing yet, is gone. Synced from upstream.

## 0.51.0 — pre-release (November 2026)

**Upgrade from 0.50.2**; nothing to migrate.

- **A shorter, plainer [AI-use policy template](docs/templates/practice-ai-use-policy.md).** It
  states the principles: AI in MedUI is an administrative and research assistant for the
  clinician using it, and is not positioned to give diagnostic or management advice to
  clinicians, staff or patients; every output is a draft the clinician checks and is
  responsible for; no unredacted or identifiable patient information goes to a cloud AI service,
  and staff don't copy patient information into AI tools outside MedUI; no provider or model is
  enabled whose terms allow it to train on the practice's requests, or keep them beyond a limited
  period for abuse and safety monitoring; patients are told, and may decline the scribe; who may
  enable models and prompts, and who may use AI; what happens when something goes wrong; yearly
  review. The reference to a governance register is gone.
- **Its Appendix A lists what is enabled, live.** Opened in MedUI (Administrator setup guide →
  AI-use policy, now in the guide's menu), the appendix lists the enabled AI providers, whether
  each runs on the practice's computers or in the cloud, and their enabled models and what they
  are used for, with the date and time, the practice name and MedUI's version. Outside MedUI the
  file says where to see the list.
- **The installation status no longer asks for a "Recommended" model.** Its "AI provider and
  model" item counted only models ticked Recommended in Setup → Models, a label nothing else
  uses, so a working AI setup showed amber. It now counts any enabled model of an enabled
  provider, and its message says what to do ("there is no a model" is gone).
- **PIT export and email/SMS count towards the installation.** Switched off, they show amber
  (to do) with the command that turns them on, instead of grey (optional): sending results to
  Best Practice and messaging patients are part of how a practice uses MedUI. A demo
  installation still leaves them out.
- **The installation status shows what is left to do.** Items to do, needed or switched off are
  always listed; the ready ones fold away behind "Show the … ready items".
- **Print or save as PDF** on every guide page prints the page alone, so a snapshot of the
  policy can go into the practice's document management.

## 0.50.2 — pre-release (November 2026)

**Upgrade from 0.50.1**; nothing to migrate.

- **Every link in the in-app guide works.** The guide (Application Setup → Administrator setup
  guide) showed six pages, so a link from them to any other page, such as the installation
  recipes, went nowhere. It now shows every page of MedUI's documentation, and the top-level
  README, changelog, security policy and AGENTS.md, which are now copied into the app's image.
  A link to a file that isn't a page (a script, a CSV file) shows where the file is in the MedUI
  folder instead. The guide's menu adds the cheat sheet and the changelog. A test follows every
  link in every page.

## 0.50.1 — pre-release (November 2026)

**Upgrade from 0.50.0**; nothing to migrate. This upgrade adds the `OCR_ENABLED` line that the
upgrade to 0.50.0 should have added.

- **`./upgrade.sh` runs the new version's own upgrade steps.** It used to run the installed
  version's copy of itself, so a step added in a release only ran on the upgrade after it: the
  upgrade to 0.50.0 didn't add `OCR_ENABLED` to `.env`. Now, once it knows the new version and
  before changing anything, it hands over to the new version's `upgrade.sh` with the same
  options. This takes effect from the next upgrade on (the script doing this upgrade is the
  installed one).
- `OCR_ENABLED` is added to `.env` in step 6 (new default settings), after the backup, not before
  it.

## 0.50.0 — pre-release (November 2026)

**Upgrade from 0.49.2**; nothing to migrate. `./upgrade.sh` adds `OCR_ENABLED` to `.env` once:
`true` if the installation has the LiteParse container, `false` if it was installed with
`--no-ocr`.

- **OCR has an on/off switch, and nothing to set up.** `OCR_ENABLED` in `.env`, beside the other
  feature switches: on unless the installation was made with `--no-ocr`, and treated as on when
  the line is missing. `./medui.sh features` offers it with the others and removes or starts the
  LiteParse container to match; `./medui.sh status` lists it. Off turns OCR off completely.
- **The built-in LiteParse needs no Setup entry,** as before; now the screens say so.
  Application Setup → External Sources says which OCR is in use (the installation's own, a
  saved service instead, or switched off), and its status dot counts the built-in one. The
  setup guide's OCR step and the [OCR](docs/ocr.md) page say "nothing to do" and explain the
  switch; adding a service in Setup is only for a different OCR server.
- **If you use an OCR server of your own without the built-in container** (installed with
  `--no-ocr`), set `OCR_ENABLED=true` in `.env` and run `./medui.sh reload` after upgrading.

## 0.49.2 — pre-release (November 2026)

**Upgrade from 0.49.1**; nothing to migrate.

- The installation status checks OCR the way Setup's **Test** button does. LiteParse has no
  health address, so a working LiteParse was shown as "not answering". When no OCR service is
  saved in Setup, the status says the installation's own LiteParse is used automatically.

## 0.49.1 — pre-release (November 2026)

**Upgrade from 0.49.0**; nothing to migrate.

- A link to a section of the in-app guide (from the home page's installation status, or within
  the guide) shows the section's heading. It used to stop with the heading hidden behind the menu
  bar at the top of the page.
- The installation status's "Practice name and timezone" links to the part of the setup guide
  that explains the timezone.

## 0.49.0 — pre-release (November 2026)

**Upgrade from 0.48.11**; nothing to migrate.

- **The installation's status on the home page.** An administrator's home page lists what the
  installation has and what it still needs: the practice name and timezone, the Best Practice
  connection (the demo SQL Server in a demo installation), HTTPS, AI with a provider, a model and
  a voice model, OCR, the PIT folder, email and SMS, and a second administrator. Each item says
  what it is needed for (hover over its ⓘ) and links to the Setup tab that changes it and to the
  section of the setup guide that explains it. Optional features that are switched off show grey and don't count
  against the installation; when everything is ready the list folds to one line. The checks
  only read, and load after the page, so a Best Practice or OCR server that doesn't answer
  doesn't hold the home page up. Other users see no change.
- `/setup/?tab=<name>` opens that Setup tab (the home page's links use it).

## 0.48.11 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.10**; nothing to migrate, and nothing in the app changes.

- **A template for the practice's request to Best Practice for database access**
  ([bp-database-access-request.md](docs/templates/bp-database-access-request.md)): which databases
  to ask for and why, and suggested wording for the purpose and the use of the access (read-only,
  on site, for the practice's own patients, AI used as the practice's policy sets). Best Practice
  Software decides whether to grant access and on what terms. Linked from the setup guide, the
  installing page and the README.

## 0.48.10 — pre-release (November 2026)

Documentation, and one code comment. **Upgrade from 0.48.9**; nothing to migrate, and nothing in
the app changes.

- The [Ubuntu recipe](docs/install/ubuntu-live.md) clones into `~/medui_os` by name, so the folder
  stays the same whatever the repository is called.
- A code comment no longer names a person.

## 0.48.9 — pre-release (November 2026)

Clean-up before the public release. **Upgrade from 0.48.8**; nothing to migrate.

- **Screens no longer use the upstream application's name.** The Application Usage print-out, two
  of its failure reasons, and the Observation anomalies page now use the installation's own name
  (MedUI). The Setup warning for a missing encryption key named a folder from the upstream
  application; it now says to set `MEDUI_ENCRYPTION_KEY` in the installation's `.env` and run
  `./medui.sh reload`.
- Code comments, test and migration descriptions, the seed manifest's notes and this changelog
  refer to "upstream" instead of naming the private application.
- A seed test no longer contains a real practice's name and phone number; the maintainers'
  private release scan checks for those instead.
- [Releasing](docs/maintainers/releasing.md) lists what changes on the day the repository goes
  public: the new address in each script and doc, the token steps, the vulnerability reporting
  setting and re-pointing existing installations.

## 0.48.8 — pre-release (November 2026)

Documentation, and one installer message. **Upgrade from 0.48.7**; nothing to migrate.

- MedUI is tested on Ubuntu 24.04 and 26.10, and any recent Ubuntu should work: everything the
  installer adds comes from Ubuntu's own repositories, and the app runs in its own container.
  The Ubuntu recipes are now titled plain "Ubuntu", and the version is named only where it was
  tested. The recipe suggests a long-term support release for a practice server.
- `install.sh` no longer warns on an Ubuntu other than 24.04: on 24.04 or 26.10 it says nothing,
  and on any other version it notes which versions were tested and carries on.
- The Windows script still creates an Ubuntu 24.04 instance.

## 0.48.7 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.6**; nothing to migrate, and nothing in the app changes.

- The native Ubuntu Server guide (`docs/ubuntu-server-it-install.md`, MedUI without Docker) is
  gone. It was never rehearsed on a fresh server, had fallen behind the installer (practice
  timezone, the BP check, HTTPS with Caddy), and had no way to upgrade: `./upgrade.sh`,
  `./medui.sh` and the backup commands are for Docker. Every supported installation now uses
  Docker; on an Ubuntu Server, follow the [Ubuntu recipe](docs/install/ubuntu-live.md). If a
  practice's IT needs MedUI without Docker, ask the maintainers.
- Links to it are removed from [other ways to install](docs/install/other-ways.md), AGENTS.md and
  the architecture page, and its item from the release status.

## 0.48.6 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.5**; nothing to migrate, and nothing in the app changes.

- [Troubleshooting](docs/troubleshooting.md) drops three rows for faults that current releases
  can't have: files left unreadable by a `umask 077` pull (the image has reset permissions since
  0.10.1), workflow progress lost between gunicorn workers (one worker since 0.9.0), and the
  Windows script's step 7 failing (scripts before 2026-10-16). An upgrade fixes each. In their
  place, "First look" says to check the version and upgrade first when what you see doesn't
  match the docs.
- The day-sheet timezone row stays, without its version: a server set to UTC can still cause it.
- Troubleshooting's "Rebuild and restart the app" section is gone: it repeated, in part, upgrading
  by hand in [operations](docs/operations.md#upgrades), where the cheat sheet now points.

## 0.48.5 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.4**; nothing to migrate, and nothing in the app changes.

- The WSL2 step-by-step page (`docs/wsl2-step-1-clone.md`) is gone. Written for an early trial, it
  covered only downloading MedUI into a WSL2 instance you already have, which the
  [Ubuntu recipe](docs/install/ubuntu-live.md) covers. What it had that wasn't elsewhere has moved:
  clone into the instance's own filesystem, not `/mnt/c` (the recipe's WSL2 note), and the
  download errors, with systemd on WSL2, in a new
  [troubleshooting](docs/troubleshooting.md#downloading-medui-git-clone) section.
- [Other ways to install](docs/install/other-ways.md) and AGENTS.md now send an existing WSL2
  instance to the Ubuntu recipe.

## 0.48.4 — pre-release (November 2026)

Documentation and maintainer files only. **Upgrade from 0.48.3**; nothing to migrate, and nothing in the app changes.

- The tooling that carries changes over from the upstream MedUI application (the sync script, its
  manifest, its record of the sync point and its maintainer page) has moved upstream, since only
  the maintainers can run it.
- The Windows scripts' README no longer has its "Origin" note pointing to another repository.

## 0.48.3 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.2**; nothing to migrate, and nothing in the app changes.

- **[Release status](docs/release-status.md) brought up to date** (it still described 0.20.0),
  and the release checklist now includes keeping it current.
- **The README's privacy summary** says that a cloud speech-to-text service receives the scribe's
  audio as recorded.
- **[Redaction lists](docs/redaction-lists.md)** adds the `name_variants` list, which redaction
  already reads.
- **Less repetition:** the setup guide, troubleshooting and the cheat sheet each kept their own
  copy of the same diagnostic, recovery, upgrade and backup commands. Each now lives in one place
  ([troubleshooting](docs/troubleshooting.md), [operations](docs/operations.md)), and the others
  lead with the `./medui.sh` command and link to it.
- **[Windows scripts](scripts/windows/README.md):** "Afterwards" points to the Administrator setup
  guide, and "Removing it" also removes the HTTPS firewall rules.

## 0.48.2 — pre-release (November 2026)

Documentation, and one label in the app. **Upgrade from 0.48.1**; nothing to migrate.

- **One page per installation recipe:** [Windows PC, live](docs/install/windows-live.md),
  [Windows PC, demo](docs/install/windows-demo.md), [Ubuntu 24.04, live](docs/install/ubuntu-live.md)
  and [Ubuntu 24.04, demo](docs/install/ubuntu-demo.md). Each lists what to have ready, the one
  command, every question the script asks and how to choose, and how to check it worked.
  [Installing MedUI](docs/install/README.md) links to them, and the routes for IT staff (native
  Ubuntu without Docker, WSL2 step by step, Compose by hand) are on
  [other ways to install](docs/install/other-ways.md).
- **The Administrator setup guide** ([docs/setup-guide.md](docs/setup-guide.md), was "Setting up
  and maintaining MedUI") is the one page that follows every recipe: what the administrator needs
  (the EDBA password, AI provider keys), MedUI's menu, then Best Practice with `./medui.sh bp`,
  HTTPS for the workstations, OCR, AI, other features and backups, in order.
  It says plainly that a cloud speech-to-text provider receives the consultation audio
  unredacted, and how to keep audio inside the practice (local Whisper).
- **In the app:** Admin → Application Setup → Help now says **Administrator setup guide** (was
  "Installer guide").

## 0.48.1 — pre-release (November 2026)

Documentation only. **Upgrade from 0.48.0**; nothing to migrate, and nothing in the app changes.

- **The README is now a short landing page:** what MedUI is, an "I want to…" table, what it does,
  its intended purpose, privacy and security in brief, and the rules if you change it. The
  installing-by-hand, development and checks sections moved to [how it's built](docs/technical.md).
- **[Installing MedUI](docs/install/README.md):** two questions (Windows or Ubuntu, live or demo)
  and where to start for each.
- **New:** [SECURITY.md](SECURITY.md) (how to report a security problem privately),
  [getting help](docs/support.md), and a [LICENSE](LICENSE) file saying the code is not yet
  licensed for use.
- The release and upstream-sync guides moved to `docs/maintainers/`.

## 0.48.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.20. **Upgrade from 0.47.0**; nothing to
migrate.

- **Improved: a hyphenated name written with a space beside the hyphen is now removed**
  (`Smith- Jones`, `Smith -Jones` or `Smith - Jones` for a stored `Smith-Jones`), for the
  patient's and the next of kin's names. Both halves must be there, in order: one half on its own
  still stays.
- **The check before sending** looks for the same forms (pre-send check `pattern-v33`).

## 0.47.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.19. **Upgrade from 0.46.0**; nothing to
migrate.

- **Improved: two more ways a patient's own details are written are now removed.**
  - A home number written with a 0 in front but without its area digit (`05550 1234` for
    `5550 1234`). The area digit without its 0 was already covered.
  - One word of a surname of several words, where it stands beside the patient's name: the
    "Thistlewood" of "van der Thistlewood", or one half of a hyphenated surname. This catches a
    letter that misspells the rest of the surname. The word must have 5 or more letters, not be
    an everyday word, and be within three words of a name that has already been removed. On its
    own, away from a name, it stays.
- **The check before sending** looks for the same phone form (pre-send check `pattern-v32`).

## 0.46.0 — pre-release (November 2026)

Windows scripts only. **Upgrade from 0.45.0**; nothing to migrate, and existing installations
are not changed.

- **New: `create_medui_wsl2.ps1` asks whether to open MedUI to the practice's workstations over
  HTTPS.** The answer is **no** unless you say yes: MedUI then answers on its own PC only, as
  before, and `./medui.sh https` turns HTTPS on later. On a yes it asks the two ports (443, and
  80 for the setup page), the name workstations will type (this PC's name) and this PC's
  address (or `none`), and shows them in the plan.
  - HTTPS is set up last, after MedUI is installed and running. If it fails, the script says so
    and the installation stands.
  - The firewall rules for the two ports are created the same way as the SSH rule: the script
    explains what they permit (Private and Domain networks only), asks **Y/n**, and only then
    brings up the Windows administrator prompt. `open_medui_https_port.ps1` is no longer a
    separate step for a new installation; it still works, and uses the same rule names.
  - The summary ends with the address each workstation opens once to be set up.
  - Not offered on Windows builds without mirrored networking, where other PCs can't reach the
    instance.

## 0.45.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.18. **Upgrade from 0.44.0**; nothing to
migrate.

- **Improved: three more ways a patient's own details are written are now removed.**
  - A home number written with its area digit but no leading 0 (`75550 1234` for `5550 1234`).
  - The date of birth with day and month the other way round (`07/03/1950` for 3 July 1950),
    only when that is a real date and not the birth date itself. Other dates are left.
  - The patient's Medicare number in any grouping (`2953 7015 61`), or cut short to its first
    7 to 9 digits. Before, only the usual 4-5-1 grouping was removed.
- **The check before sending** looks for the same three (pre-send check `pattern-v31`).

## 0.44.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.17. **Upgrade from 0.43.1.**

- **Improved: a patient's phone number is removed when a document lays it out in columns.**
  Letters and forms often spread a number's groups across columns with wide gaps
  (`5550        1234`, `07    5550    1234`). Redaction allowed up to three spaces between the
  digits, so these were left whole. It now also allows a run of 4 to 12 spaces or tabs between
  the patient's or next of kin's own digits; never a line break. Other people's numbers are
  treated as before.
- **The check before sending** looks for the same, and for an 8-digit landline written without
  its area code (pre-send check `pattern-v30`).

## 0.43.1 — pre-release (November 2026)

A fix, synced from upstream. **Upgrade from 0.43.0**; nothing to migrate.

- **Fixed: Scribe's ✦ Recompose during the first chunk.** The button stayed greyed out until the
  first chunk's text came back, so pressing it then did nothing and recording ran on into the
  next chunk. It is now available as soon as recording starts (with a pipeline chosen): it stops
  the recording, waits for the last chunk's text, then writes the note. If that last chunk had no
  speech, it says there is nothing to recompose. Stopping with no audio left to send no longer
  waits 15 seconds on "Stopping…".

## 0.43.0 — pre-release (November 2026)

Synced from upstream. **Upgrade from 0.42.0**; the upgrade adds one column to the AI
models table (`flask db upgrade`).

- **New: speaker turns from Deepgram.** On a Deepgram speech-to-text model, Application Setup →
  Models now has **Speaker turns** (Off, latest, v2, v1). When it is on, Deepgram separates the
  speakers in each Scribe and Quick Scribe chunk, and the transcript shows **[Speaker 1]** /
  **[Speaker 2]** turns. A practice with no local AI now gets who-said-what: before, speaker
  labels came only from a local model, and without one the transcript had none. Deepgram
  numbers the speakers afresh in each chunk and doesn't say which is the doctor. Dictation never
  asks for it, and every other model works as before, with labels from a local model.
- **New: Deepgram's Australian region.** A Deepgram provider's **Base URL** is now used:
  `https://api.au.deepgram.com` keeps the audio in Deepgram's Australian region. Blank, or the
  address saved before, is Deepgram's global service, as before.
- **New: extra parameters on speech-to-text models.** A model's extra request parameters now go
  with every transcription request: query parameters for Deepgram (for example
  `{"numerals": true}`), form fields for a Whisper server.
- **Scribe and Quick Scribe** say under **ASR Model** how speakers will be labelled for the
  model chosen, or why there will be no labels (the labelling prompt missing, or not set to a
  local model).
- **Fixed:** the Deepgram connection test now works with the Australian address.

## 0.42.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.16. **Upgrade from 0.41.0.**

- **Improved: a patient's address is removed when a document writes only part of it.** Scanned
  letters often write the address in pieces: the unit and number with one or two of the street
  words, a word as its initial or misspelt, the line in capitals or spaced out with tabs. These
  were left in the text, because redaction looked for the address as it is stored in Best
  Practice. MedUI now looks for the patient's own address parts in their usual order on one line.
  The suburb on its own still stays, since it is often the practice's suburb too.
- **Help, Privacy Review:** what happens when a patient's details can't be read from Best
  Practice. A request to a cloud model stops; a request to a local model goes ahead, and the
  patient's own details may not be removed from it.

## 0.41.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.15. **Upgrade from 0.40.0.**

- **Fixed: one badly typed height or weight no longer stops redaction for a patient.** When a
  patient's latest weight or height in Best Practice was not a plain number (for example a value
  typed with its unit, "80kg"), the core could not load that patient's details. Every run for
  them on a cloud model was then stopped ("redaction unavailable"), and a local run went without
  the patient's own details redacted, until the entry was corrected. Such a value is now
  ignored, and the patient's name, address and other details load as usual. No redaction result
  changes for any other patient, and stored results need no re-run.

## 0.40.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.14. **Upgrade from 0.39.0.**

- **New: common short forms of a patient's name are redacted without a list entry.** MedUI now
  comes with a list of about 270 common Australian short forms and spellings (Mick for Michael,
  Libby for Elizabeth, Sara for Sarah). Each is removed for every patient with that first or
  middle name, as a name token. Before, a short form was removed only when enough of the
  practice's patients had it recorded as a preferred name, or an administrator had added it to
  the name-variant list, and the privacy check reported it as something the rules don't cover.
  Short forms that are also everyday words (Will, Bill, Rose) or clinical abbreviations (reg,
  cath) are not on the list; a practice can still add them to its own list.
- **Changed: a surname beside a short form is removed with it** ("Mick Thornbury" becomes one
  token, "Mick rang" keeps "rang"), for every short form, the practice's own included.
- **Fixed: a short form written as a dash bullet** ("-Mick" at the start of a line) was left in
  the text. A hyphen now stops a match only when it joins a word ("X-Ray").
- **Redaction core 0.2.14** (checker `pattern-v29`, unchanged).
- Help: Privacy Review → Add to future redactions.

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.39.0 — pre-release (November 2026)

Synced from upstream. **Upgrade from 0.38.4.**

- **Fixed: the population chart's condition filters used their own short code lists.** A patient
  with the Disease Profile badge could be missing from the chart's filter (paroxysmal AF, for
  one). The filters now use the practice's condition codes list, active conditions only, the same
  rule as the badges. Sleep apnoea, osteoarthritis of weight-bearing joints and depression or
  anxiety join the list, with the codes the chart used before; edit them in Admin like the others.
  An inactive or deleted condition no longer counts.
- **New: the chart says who isn't plotted.** The count shows how many are plotted and how many
  have no value for an axis. An optional "Show patients with no value" strip shows them along the
  edge of the chart.
- **New: a patient list below the chart**, with all matching patients or only those missing a
  value. It can be downloaded as CSV or Markdown when it has 500 patients or fewer; narrow the
  filters to get there. Each download is recorded in usage as `patient_list.export`. The file
  holds patient names: keep it within the practice.
- **Changed: ages are exact (one decimal place)**, so patients of the same age in years no longer
  sit on top of one another, and the adult cut-off uses the birthday.
- **Fixed: a moved slider now filters.** A patient with no value passed every slider; once a
  slider is moved, only patients with a value in its range count.
- Help: The patient record → Population chart.

Upgrade: `./upgrade.sh` as usual (one migration: it adds the three new conditions' codes to an
existing condition codes list, and leaves a condition that already has rows as it is).

## 0.38.4 — pre-release (November 2026)

Synced from upstream. **Upgrade from 0.38.3.**

- **Fixed: social history was missing for patients with no alcohol or smoking record.** The
  patient record and the Social History data block need both; a patient without one lost the
  whole section, including marital status, occupation and the chart flag. At the practice where
  this was found, about a quarter of active patients were affected. Alcohol now shows "No Data"
  for them.
- **Fixed: weight was rounded to whole kilograms**, and BMI worked out from the rounded weight. It
  now keeps one decimal place. A malformed weight or height in Best Practice is now read as blank
  instead of stopping the patient's demographics from loading.
- **Changed: a coded *Reason for visit* copied to past history counts as active.** Best Practice
  can copy a visit's reason to Past History (a doctor's preference); it saves these with status 0,
  which MedUI didn't count. A coded one now counts as an active condition, in the past history
  list, the data block and the Disease Profile badges. An uncoded one is left out. The Medical
  History data block gains a Status field (Active / Inactive).

Upgrade: pull and build. No migration.

## 0.38.3 — pre-release (November 2026)

Synced from upstream. **Upgrade from 0.38.2.**

- **Changed: BMI isn't worked out from a childhood height for an adult.** BMI still uses the
  latest weight and the latest height, even when they were measured on different days (Best
  Practice's own BMI needs both on the same day). But a height measured before 18 is no longer
  used for a patient who is now 18 or older: before, an adult's weight over a height from
  childhood gave a BMI that was far too high. The weight and height are still shown, with their
  dates, at any age; the weight chart's caption says why there is no BMI, and the care plan
  `bmi` and `weight_excess` tokens are left out. Record a current height to get a BMI again.
  Patients under 18 keep their latest height.
- **Fixed:** the patient panel showed the weight only when there was a BMI; it now shows the
  weight and height without one.

Upgrade: pull and build. No migration.

## 0.38.2 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.13. **Upgrade from 0.38.1.**

- **Fixed: part of an address was left when a road is named for the patient's surname + s and
  has words before "Rd".** In 0.38.1, "123 Quillfeathers Gully Creek Rd" (for a patient surnamed
  Quillfeather) could come out as a patient token with the number, "Gully Creek" and "Rd" beside
  it. The whole address is removed again, as before 0.38.0. A name + s straight after a house
  number is now always left for the address step to take. Names with an s after them ("Marigolds'
  daughter", "Marigolds wife at St Vincent's") are still removed.
- **Redaction core 0.2.13** (checker `pattern-v29`, unchanged).

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.38.1 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.12. **Upgrade from 0.38.0.**

- **Fixed: part of the patient's address was left when their street is named for their
  surname + s.** In 0.38.0, "12 Quillfeathers Road" for a patient surnamed Quillfeather could come
  out as a patient token with the house number and "Road" beside it, when the street was written
  differently from Best Practice's record (an extra space, or the street without its number).
  The whole street is removed again, as before 0.38.0. Names with an s after them ("Marigolds'
  daughter") are still removed.
- **Redaction core 0.2.12** (checker `pattern-v29`, unchanged).

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.38.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.11:

- **A patient's name with an s straight after it is removed.** A possessive written with the
  apostrophe after the s ("Marigolds' daughter") or with no apostrophe ("Marigolds daughter",
  "the Quillfeathers") left the patient's name in the text sent to the AI, and the pre-send check
  did not report it. Now the name is removed and the s stays after the token, as with "Marigold's".
  This covers the patient's first, middle, surname and preferred names, their next of kin, and
  nicknames. Lower-case ordinary words are left as they are ("marigolds tea").
- **The pre-send check finds the patient's name glued to other characters.** A first name,
  surname or preferred name joined to a letter or digit ("xQuillfeather", "Quillfeather2") now
  pauses the request, so you can remove it or allow it. Redaction does not remove these forms.
  Only names of 5 or more letters that are not ordinary words are checked this way.
- **Redaction core 0.2.11** (checker `pattern-v29`).

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.37.1 — pre-release (November 2026)

- `./install.sh --https --dry-run` (and `./medui.sh https`, which runs it first) now runs to
  the end. It stopped at its last step with `CHECK_NAME: unbound variable`: the name MedUI
  answers on was worked out only on a real run, but printed in the dry run too. A real
  `--https` run was not affected.

## 0.37.0 — pre-release (November 2026)

- **`./medui.sh remove`: remove an installation, with checks.** It shows the installation
  (name, folder, ports, live or demo, whether it reads Best Practice) and the other MedUI
  installations on the computer, which it leaves alone. Then it:
  - offers a backup first (yes by default, except for a demo), and moves it and any earlier
    backups out of the folder, to `~/medui_removed/<name>-<date>/`;
  - asks you to type the installation's name;
  - removes its containers, database, stored files, images and network, every part included
    (OCR, HTTPS, a demo's SQL Server), and checks nothing of it is left in Docker;
  - deletes the folder last, so a failure earlier leaves the folder in place to try again;
  - on WSL2, prints the Windows commands that remain: closing the HTTPS firewall rules, and
    removing the whole instance when no other MedUI is in it.

  It refuses when Docker says the installation runs from another folder, and it needs a
  terminal. In the menu it is the last item.

## 0.36.0 — pre-release (November 2026)

- **Demo installations: `./install.sh --demo`.** For demonstrations, training and screen
  recordings, in a folder of its own (for example `~/medui_demo`). Besides an ordinary
  installation, it:
  - runs SQL Server 2022 Express in a container of its own (compose service `bpsql`, profile
    `demo`), with no port on the computer and its usage reports to Microsoft turned off. It
    asks you to accept Microsoft's licence terms first (`--accept-sql-licence` without a
    terminal);
  - restores MedUI's invented demo databases (medui_demodata, every row made up) and creates
    a read-only login, written to `.env` (`BPSDB_HOST=bpsql`);
  - asks for the demo users' password (Dr Imogen Thistlewood and the rest of the fictional
    practice), and brings the data's dates up to today.

  A new installation without `--demo` asks whether it is live or a demo; with `--yes` (the
  Windows script, agents, scripts) it is live unless `--demo` is given, and a re-run keeps
  what `.env` says. `MEDUI_INSTANCE=demo` in `.env` marks it. A live installation can't become a demo, a demo
  can't take the name `medui_os`, and on a demo `./medui.sh bp` and `bp-clear` refuse: MedUI
  keeps BP patient and user numbers in its own database, so demo records would attach to
  real patients with the same numbers.
- `./medui.sh demo` (`status`, `refresh [--dry-run]`, `password`): the demo data, its dates
  and the demo users' password. `status`, `start` and `stop --all` include the demo SQL
  Server, and `use` stops another installation's one too.
- **Windows:** `create_medui_wsl2.ps1` asks first whether the installation is live or a demo.
  A demo gets its own instance (`medui_demo`), folder and ports (5006, 55433, 5708), the
  GitHub token is checked against medui_demodata too, and the demo data is cloned with MedUI.
- The removal command in the docs now includes `--profile demo`, so it also removes a demo's SQL
  Server and its databases (left out, they stayed behind and kept the network in use).
- `scripts/demo_data.sh` does the demo data's steps for `install.sh` and the menu. It works
  only on a demo installation and only on its own SQL Server. Passwords travel in the
  environment or a mode-600 file deleted afterwards, never on a command line.

## 0.35.1 — pre-release (November 2026)

- **A second installation can't take over the first by mistake.** Without `--name`, a new
  installation is now named after its folder (`~/medui_demo` becomes project `medui_demo`)
  instead of always `medui_os`. Before, a second folder installed without `--name` shared the
  first one's containers and data, and its new `.env` couldn't open the database. An
  installation keeps the name in its `.env`, so existing ones are unchanged.
- `install.sh` stops, saying where, when the name is already installed from another folder, or
  when Docker still holds data under that name from a removed installation.
- On a new installation, a default port that is taken (by a running service, or by another
  installation even while stopped) moves to the next free one, with a note. A port given on the
  command line, or kept in `.env`, never moves; a clash names the installation holding it.

## 0.35.0 — pre-release (November 2026)

- **`./medui.sh`: a menu for running an installed MedUI** (native Ubuntu or WSL2). Each item
  also works as one command (`./medui.sh status`, `./medui.sh help` lists them), for IT,
  scripts and coding agents. Every action prints the command it runs, and nothing in it prints
  `.env`'s secrets. It covers:
  - status (containers, health, BP set or not, HTTPS, features, last backup);
  - start and stop (`stop --all` also stops the database and OCR);
  - `reload`, which recreates the app after a `.env` change;
  - the Best Practice connection: `bp` asks for it, writes `.env` (one backslash for a named
    instance, single quotes where a password needs them), reloads and checks that the login is
    read-only; `bp-check` and `bp-clear`;
  - optional features (AI, messaging, PIT export);
  - HTTPS for workstations (`./install.sh --https`);
  - backup now and list backups;
  - upgrade (the dry run first);
  - logs;
  - add a local administrator, or set a new password for one;
  - seeded prompt and workflow updates;
  - OCR start and stop;
  - the installations on this computer, and `use` to make this one the running one;
  - the Windows-side commands on WSL2 (keep-alive task, firewall);
  - a support summary with no data or secrets.

  It uses whiptail where present, and a numbered list otherwise.
- **Test and demo installations:** the setup guide, cheat sheet and `./medui.sh bp` now name
  MedUI's own demo databases ([medui_demodata](https://github.com/medui-au/medui_demodata),
  every row invented) beside BP's sample databases.
- **`scripts/env_edit.py`** changes `.env` for it. It writes values passed in environment
  variables, never on the command line, keeps the previous file as `.env.bak`, and keeps both
  files at mode 600.
- Not in the menu, on purpose:
  - Opening MedUI's own port 5005 to the network: it is plain HTTP. Workstations use HTTPS.
  - Switching one installation between the practice's BP and sample data: MedUI's database
    keeps users and history tied to one BP. Sample data gets its own installation (`--name`).
  - The WSL2 keep-alive task: it runs on Windows, which the instance can't reach. The menu
    shows the PowerShell commands instead.

## 0.34.1 — pre-release (November 2026)

Windows scripts only:

- **`create_medui_wsl2.ps1` waits before asking for administrator approval.** At the SSH
  firewall step it explains why approval is needed and what it permits: one inbound rule for the
  SSH port, Private and Domain networks only, created by a run that does nothing else. Then it
  asks **Y/n**. The Windows prompt appears only after a yes, not straight after the
  explanation. A no keeps SSH to this PC only and prints the command to add the rule later.

## 0.34.0 — pre-release (November 2026)

Synced from upstream:

- **A login without Best Practice opens Setup → Database.** When an administrator logs in and the
  Best Practice connection isn't set in `.env`, MedUI opens **Application Setup → Database**
  with a notice saying what to add, not the home page. It happens at login only, so it can't
  loop. A `?next=` that already goes to a Setup page is kept. Other users log in as usual.
- **Best Practice counts as set only when `BPSDB_HOST`, `BPSDB_USER` and `BPSDB_PASSWORD` are all
  filled in** (or `BPSDB_URI` is given whole). Before, a host alone counted, and the connection
  then failed. With one of them blank, MedUI now treats BP as not set: Setup → Database says
  "Not configured", not a connection error.
- **`/setup/?tab=database`** opens Setup on the Database tab.
- **The login follows `?next=` only to MedUI's own pages.** An address on another site goes to the
  home page instead.

## 0.33.5 — pre-release (November 2026)

Windows scripts only, after a review of `create_medui_wsl2.ps1` and an end-to-end test on a new
WSL2 from a standard Windows account:

- **No longer run as administrator.** `create_medui_wsl2.ps1` runs from an ordinary PowerShell
  window. Elevating with another account's password used to build the instance, `.wslconfig` and
  the keep-alive task for that account, so MedUI didn't appear or start for the person who uses
  it. Only the SSH firewall rule needs an administrator now: the script asks for it with a Windows
  prompt, and the install still completes if it is cancelled (SSH then works from this PC only).
  Elevated under another account than the one signed in, the script says so and stops unless you
  confirm.
- **SSH: key only when a key is installed.** Password login is refused when a public key was
  given (the Linux password also gives sudo); without a key, password login as before. Reverse
  tunnels are refused (`AllowTcpForwarding local`); `ssh -L` still works.
- **Firewall: the Hyper-V rule is limited to Private and Domain networks**, like the Windows rule,
  in both `create_medui_wsl2.ps1` (SSH) and `open_medui_https_port.ps1` (443 and 80). Where
  Windows can't limit it, the script says the port is open on all networks.
- **The instance can't reach this PC's files** (new question, default yes): Windows drives
  (`/mnt/c`) and starting Windows programs are turned off in the instance. MedUI uses neither.
- **Keep-alive comes back.** The task starts the instance again within about 10 seconds if it
  stops, and is checked every 5 minutes. To stop MedUI on purpose, end the task first (the
  summary and the Windows README show how). `upgrade_medui_wsl2.ps1` ends it before writing a
  snapshot, so the snapshot is taken with the instance stopped.

Upgrade: nothing to do inside MedUI. For an existing Windows instance, the new keep-alive and
firewall behaviour come with a new instance; re-running `open_medui_https_port.ps1` as
administrator applies the Hyper-V limit to the HTTPS rule.

## 0.33.4 — pre-release (November 2026)

Synced from upstream:

- **Application Usage no longer shows another practice's dates.** Its notes and two help pages
  (Application Usage, My Settings) named the dates when the upstream practice's own usage history
  was imported. The notes now take their dates from this installation's usage record and appear
  only when history was imported (`flask usage import-history`). A new installation has none, so
  it shows none of them.

Upgrade: `./upgrade.sh`. No migration.

## 0.33.3 — pre-release (November 2026)

- **Cheat sheet** ([docs/cheatsheet.md](docs/cheatsheet.md)): every `install.sh` and `upgrade.sh`
  switch, the everyday Docker commands, backup and restore, MedUI's own `flask` commands, the
  Best Practice settings, the Windows scripts and removal, on one page with links to the full
  docs. Linked from the README and AGENTS.md.

Upgrade: `./upgrade.sh`. No migration; documentation only.

## 0.33.2 — pre-release (November 2026)

Synced from upstream:

- **No scripts from a CDN.** Chart.js, its moment adapter and Moment.js are served by MedUI
  (`app/static/vendor/`, each with its licence), so a workstation never loads code from a
  third-party server, and the charts work without internet access.
  - Chart.js 4.6.1 and the adapter 1.0.1 are the versions the pages already loaded; the CDN
    URLs weren't pinned to a version before.
  - Moment.js goes from 2.29.1 to 2.29.4, which fixes CVE-2022-31129.
  - A test fails if a template loads a script or stylesheet from another server.
- **Upgrade docs:** `--dry-run` fetches too, so at git's prompt the token is typed twice. Set
  `MEDUI_GIT_TOKEN` to type it once. The comment in `upgrade.sh` now says the token can be set
  by hand as well as by the Windows wrapper.

Upgrade: `./upgrade.sh`. No migration.

## 0.33.1 — pre-release (November 2026)

From the demo install's upgrade to 0.33.0:

- **The Best Practice login check is now always in the log.** The startup result was logged at
  INFO, which this edition's log doesn't show, so a read-only login left no line at all. It is
  now logged at WARNING whatever it is: one `bp_login:` line per start (synced from
  upstream).
- **Upgrade docs: the GitHub token.** While the repository is private, `upgrade.sh`'s fetch needs
  a token with read access. Git asks for it, or you can give it for the one run as
  `MEDUI_GIT_TOKEN`.
- The 0.32.3 entry's upgrade line no longer says "no build", because `upgrade.sh` always builds.

Upgrade: `./upgrade.sh`. No migration.

## 0.33.0 — pre-release (November 2026)

Synced from upstream:

- **MedUI checks that its Best Practice login can't write**. MedUI only reads
  Best Practice, but the SQL Server login decides what could be changed. MedUI asks the server
  what its login may do, without trying a change: server administrator, write roles, write
  permission on any table, or creating and altering tables, in every database it can open.
  - **Application Setup → Database** shows "Read-only" or lists what the login could do.
    Stored procedures it may run are listed for information.
  - The check runs once at startup and is logged.
  - If the login can write, administrators see a notice on every page, and SQL written in
    **Query Manager** or **Best Practice data sources** is refused until the login is changed.
    MedUI's own screens keep working.
  - The setup guide now says to use the read-only account BP supplies for database access.
- **An unreadable ZIP in a report or document** (for example Deflate64, found in BP's sample
  databases) shows a message instead of an error page.

Upgrade: pull and build. No migration. A test or demo install that connects with a broader login
(for example `sa`) will show the notice, and its Query Manager stops until it uses a read-only login.

## 0.32.3 — pre-release (November 2026)

From the first demo install on BP's sample databases:

- **Install docs: which BP server.** The setup guide said the installer asks for the BP
  connection; it doesn't. It now says to add `BPSDB_*` to `.env` afterwards, and warns that the
  BP login reads every database it can open on that server, so a test, demo or training install
  must point at a server with only test data. The same caution is in README, AGENTS.md and, for
  an install with a `--name` other than `medui_os`, the installer's closing notes.
- **Installer dry run** now says when the real run would add you to the `docker` group, which
  takes effect at your next login.

Upgrade: `./upgrade.sh` as usual. The release changes only docs and the installer, but the script always rebuilds the image and checks the schema, which is harmless.

## 0.32.2 — pre-release (November 2026)

- Docs: **removing an installation** ([operations](docs/operations.md#removing-an-installation)):
  the commands that delete MedUI's containers, data and folder, and what is left behind (Docker,
  workstations' trust in the MedUI root, Windows firewall rules). No change in behaviour.

Upgrade: pull and build. No migration.

## 0.32.1 — pre-release (November 2026)

Synced from upstream:

- **Fix: lab reports sent as a web page copy as plain text.** Some laboratories send a result
  as an HTML file that puts the whole report in one pre-formatted block, with a line-break tag
  for every line. Copying it from Results Rollup gave the markup as one long line. Now the
  tags are removed and each line break becomes a new line; column spacing is kept. Reports
  that already copied correctly are unchanged. The viewer's text and the patient data given
  to AI get the same plain text.

Upgrade: pull and build. No migration.

## 0.32.0 — pre-release (November 2026)

Synced from upstream:

- **Application Usage in two tabs, AI and Non-AI** (Doctor Data, administrators only). Each tab
  has a few headline figures; click one to see it broken down, click a row to look inside it
  (it becomes a filter you can remove), then see the records themselves. Every filter applies
  to every figure, the chart and the table. Exports export what is on screen. Before this, the
  "AI runs" figure ignored the provider filter; it now follows it.
- **Staff names on screen by default** on that page, for administrators. *Show names* switches
  to permanent labels ("Doctor 2"), for example while sharing the screen. Exports still use
  labels unless names are confirmed.
- **My Usage** (User Data → My Usage), for everyone: your own use under your own name, with the
  practice's total for the same period under each figure. Practice figures are totals only,
  never broken down by person or role. With AI switched off, it opens on the Non-AI tab.
- New help: *Application Usage*, and *My usage* in My settings.

Upgrade: pull and build. No migration.

## 0.31.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.10:

- **A practice user's 4-letter first name is removed in lower case too.** Speech-to-text often
  writes names without a capital ("how's paul going"). A doctor's or staff member's first name of
  4 letters is now removed whatever its capitals, as names of 5 or more letters already were.
  These names are never ordinary words (0.30.0 leaves those out). Patients' 4-letter first names,
  and 3-letter names, are still removed only with a capital.
- **Redaction core 0.2.10.** Programs that leave `practice_first_names` off see no change.

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.30.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.9:

- **Your practice's users' first names are removed on their own.** A doctor's or staff member's
  first name without the surname ("Thanks, Sam", "Sam will ring next week") is now removed from
  text sent to a cloud model, for every user in Best Practice, current or former. As before for
  other first names, a name in lower case is removed only when it has 5 or more letters. Two kinds
  are left in: a first name that is also an ordinary word (Rose, Grace), and the first word of an
  account named for a service rather than a person ("Telehealth Bookings"). To have an
  ordinary-word name removed, add it to the **first_names** list (Admin → Mapping Tables) with
  *include* ticked.
- **Redaction core 0.2.9:** the `practice_first_names` option. Programs that leave it off get
  exactly 0.2.8's output.
- Help: Application Setup → Users.

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.29.0 — pre-release (November 2026)

Synced from upstream, with redaction core 0.2.8:

- **Scribe: your own first name is removed in any case.** Speech-to-text often writes a
  transcript without capitals ("thanks sam"), and a first name alone, without the surname, was
  only removed when it had a capital and was on the first-name list. Now, when you send a
  transcript to a cloud model, your own first name (your MedUI preferred name and your Best
  Practice first name) becomes one `[Redacted Name]` token, whatever its capitals. A first name
  that is also an everyday word (Will, Mark, May…) is removed only with a capital, so "we will
  see" is left alone. Other clinicians' first names are unchanged.
- **Redaction core 0.2.8:** a filler word before a name ("Yeah, Sam", "Okay, Sam") and a
  contraction after it ("Sam I've…") no longer go into the name token.
- Help: The scribe → Writing the note.

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.28.2 — pre-release (November 2026)

- Housekeeping: removed `app/data/nicknames.csv` and its provenance note. Nothing has read them
  since the redaction core took over the checker; the core carries its own copy. No change in
  behaviour.

Upgrade: pull and build. No migration.

## 0.28.1 — pre-release (November 2026)

Synced from upstream:

- **Fix: percentages and counts are no longer charted together.** Laboratories often give a
  blood count's percentage and its count the same name ("Monocytes" as % and as ×10⁹/L). The
  results charts treated both as one test, so percentages were plotted as counts. Now:
  - **Results Outside Range** keeps them as separate tests.
  - **Atomized Pathology** draws a separate chart for each, e.g. "Monocytes (%)" beside "Monocytes".
  - The link from one page to the other opens the right chart.
- Help: Results Outside Range → The charts page.

Upgrade: pull and build. No migration.

## 0.28.0 — pre-release (November 2026)

Synced from upstream:

- **The redaction core moves from 0.2.4 to 0.2.7:**
  - **The practice's own name** becomes `[Redacted UsualPractice: …]` in records, in what you type
    and in prompts, so a town in the practice's name is no longer taken for a patient's suburb or a
    contact's surname. Scanned forms of the name, such as stray letters, superscripts and run-together
    endings, are caught too. A system prompt can say what the token means, e.g. "refer to it as
    'this practice'".
  - **A phone number glued to its label** (`ph0491 570 156`, `mob(07) 5550 1234`) is redacted. The
    label stays in the text. Codes such as `AB0412345678` are left alone, and the pre-send check
    sees the glued form too.
  - A practitioner's name after an initial ("Dr J Smith") is taken whole.
- **Care Plan moves to the top menu:** Patient Data → Care Plan (doctors and administrators).
  Care Plan Recipes stays under Doctor Data and leaves the patient's tools.
- **Care plan layout:** each issue is now a bold heading row above its goals, management and
  providers, so Goals and Management get more room. An issue is kept together across a page
  break. This applies to print, view, Email and BP →. Plans filed earlier keep their old layout.
- **Archive a pipeline:** Archive beside Activate in the pipeline editor (administrators). All
  Pipelines hides archived pipelines, and **View archived (n)** shows them. An archived pipeline
  never runs. Unarchive returns it to draft.
- **Fix:** the pipeline editor's buttons did nothing for a pipeline without a classifier.
- Help: Prompts (Archive), Care plans and Privacy Review updated.

Upgrade: pull and build (the new core wheel installs in the build). No migration.

## 0.27.0 — pre-release (November 2026)

Synced from upstream:

- **Care plans (patient tools → Care Plan):** write and file a GP Chronic Condition Management Plan.
  The medical history starts from Best Practice's coded history, medications and allergies. Each
  row is an issue with its goals, management and providers, and you choose every issue, recipe,
  variant and target. Tokens such as `{ldl.last}` are filled from Best Practice results by LOINC
  code, and from the record (blood pressure, weight, height, BMI, weight above or below the BMI 20–25
  range, age, sex, alcohol, smoking). You confirm each value before it's used, and nothing says
  whether a target has been met. The draft saves itself. **Print preview** shows the draft as it will
  print, and **Copy**, **Email** and **BP →** (through Comms) work from the draft or from the filed
  plan. **File plan** freezes the plan and its values, keeps an exact copy, and can be voided later
  but not edited. One 🎤 dictates into whichever box you last clicked in.
- **Care Plan Recipes (Doctor Data):** reusable wording per issue and variant, with one target per
  result and its guideline, edition, section and quoted passage. Recipes are versioned and approved.
  Doctors have personal recipes; administrators keep practice recipes, which every doctor is
  offered once approved. Administrators also set up result tokens: **Pick…** lists every LOINC code
  in the practice's results from the last 5 years, and a code used in two tokens is flagged.
- **Recipe AI assistance (optional):** any active pipeline whose classifier contains `[recipe]`
  shows **Draft with AI** on the recipe page. No patient information is involved. None is seeded.
  To set one up, give the user prompt `{{input.user_prompt}}` and ask for one fenced JSON block
  with `issue`, `variant`, `goals`, `management`, `providers` (strings or lists) and `targets`
  (`token`, `target`, `guideline`, `edition`, `section`, `quote`, `url`). Use scope `general`
  and about 4,000 max tokens.
- Help: a new Care plans page.

Upgrade: pull, build, `flask db upgrade` (ten new tables; `./upgrade.sh` runs it).

## 0.26.0 — pre-release (October 2026)

Synced from upstream:

- **Your details card:** point at your name at the top right (or tab to it) to see your details as
  Best Practice holds them: qualifications, AHPRA registration, HPI-I, provider numbers by site,
  prescriber number, first patient visit, patient visits and patients seen (every visit type except
  "Non visit"). It's read from Best Practice the first time it opens and again after an hour. Lines
  with nothing recorded are left out. Clicking your name still opens My settings. It replaces the old
  tooltip, which always said "Reg: N/A".
- **A doctor's details for administrators:** on Application Setup → Users, a doctor's name (marked ⓘ)
  opens the same card for that doctor. A doctor is a Best Practice user with a provider or prescriber
  number. Only administrators see it.
- Help: "Your details card" in My settings, and a paragraph in Setup → Users.

Upgrade: pull and build. No migration.

## 0.25.0 — pre-release (October 2026)

Synced from upstream:

- **Privacy Review (Admin → Privacy Review):** a list of the AI requests in which the pre-send
  privacy check found something, or that a user reported from the Sent to AI tab. Filters by tier
  (tier 0–1 or reported by default; tier 2; anything), whether it has been reviewed, workflow and
  dates. **Outcome** says whether the request went to the AI or was stopped at review. A key on the
  page and a new help topic explain the tiers, the columns and the choices.
- **Recording a review:** each request's Privacy hits page has previous / next within the list
  and a **Your review** form: real leak, false alarm or acceptable, an optional severity and a
  comment (stored encrypted). A review is removed with its request's record when old records are
  purged.
- **Off by default:** switch it on in Application Setup → Maintenance → Privacy Review. The check
  itself always runs, and tier 0 and 1 hits still stop a request, whether the page is on or off.
- The Privacy hits page now shows the hits for a request that was stopped at review (it used to
  say "not checked").

Upgrade: pull, build, `flask db upgrade` (one new table; `./upgrade.sh` runs it).

## 0.24.0 — pre-release (October 2026)

Synced from upstream:

- **Extra request parameters for a model:** Setup → Models has an "Extra request parameters" box
  under each model, a JSON object sent with every request to it. The usual use is a local
  reasoning model's thinking: with Ollama, `{"reasoning_effort": "none"}` turns it off (Ollama's
  `"think"` has no effect at the OpenAI-compatible address MedUI uses), or `"low"`, `"medium"`,
  `"high"`. A workflow's Inference step can override them for that workflow only; a key set to
  `null` there removes the model's value. MedUI refuses what it sets itself (model, messages,
  temperature, maximum length), and these settings never change redaction or the privacy checks.
  Not sent to Anthropic's own API.
- **Debug tab:** the AI assistant shows the parameters sent, and each AI response notes how much
  the model reasoned (the length of its reasoning, and reasoning tokens where the provider counts
  them; the reasoning text is not kept).
- The Anthropic provider takes the reply's first text block, so a reply that starts with a
  thinking block is no longer empty.

Upgrade: pull, build, `flask db upgrade` (one new column; `./upgrade.sh` runs it).

## 0.23.0 — pre-release (October 2026)

Synced from upstream:

- **Redaction core 0.2.4:**
  - A shortened first name the practice knows (a listed variant or the practice's nickname
    table) is now redacted in single quotes and before a possessive 's, as well as in double
    quotes. Data blocks written into a prompt carry their values in single quotes, so this is
    where most of the gain is.
  - When a patient's name or short form is also a month (May, June, Jan), the month in a date
    ("12 Jan 2026", "in May", "since June 2025") is now kept instead of being taken out as the
    name; the privacy check no longer reports it either. A possessive or a month word with no
    date around it is still treated as the name. The privacy check is `pattern-v24`.

Upgrade: pull, build. No migration.

## 0.22.0 — pre-release (October 2026)

Synced from upstream:

- **Redaction core 0.2.2:** a line break or tab written out as text (`\n`, `\t`, `\r`, as data
  blocks carry them when written into a prompt) now separates words for redaction and the privacy
  check. Before, a name straight after one was read as part of another word and could be sent: on
  MedUI's history since September this adds redactions after such escapes (names, patient
  identifiers, phone numbers, labelled identifiers) and removes none. The privacy check is
  `pattern-v23`.

Upgrade: pull, build. No migration.

## 0.21.1 — pre-release (October 2026)

- **Fix:** the AI assistant page failed with an internal server error after 0.21.0: it asked for the
  document summariser's status, which this edition doesn't include. Two tests now catch this: every
  link a page builds must name a route the app has, and the AI assistant page must render.

## 0.21.0 — pre-release (October 2026)

Synced from upstream:

- **Redaction core:** the redaction rules, the token vault, the pre-send privacy check and
  de-redaction now come from the **bps-redaction** core (0.2.1, Apache-2.0), a pinned wheel in
  `vendor/wheels/` installed with the image. Behaviour is unchanged: the core matched MedUI on its
  whole run history before the switch. The code's own copies and 12 Best Practice queries only they
  used are removed.
- **Sent to AI** shows what was sent for a local model too, saying it stayed inside the practice.
  After a cloud request it shows what the privacy check found, with its marks in the prompt, and
  **Report something that got through**: select text in the prompt to report it to the
  administrators.
- **Admin:** the privacy card (Debug, administrators), the run's **Privacy hits** page (add a hit
  to the always-redact or name-variant list) and users' reports there; **Flagged AI Requests**
  lists runs with open reports. Migration `b6d1f4a8c2e3` adds the reports table
  (`flask db upgrade`).
- **Practitioners' preferred names** for tools that read only Best Practice: an inactive "shadow"
  user under the preferred name is redacted and checked (the practitioner queries keep inactive
  users on purpose).

Upgrade: pull, build, `flask db upgrade`, then install defaults and resync seeds as usual.

## 0.20.0 — pre-release (October 2026)

Synced from upstream:

- **Charts** (patient charts and atomised results) shade the **laboratory's range**, from the most
  recent result that has one, named in the caption; MedUI's own target bands and captions are gone.
  Labels read *Range*, *Above range*, *Below range*. The quality report heading and a stale
  provider note were reworded (the last wording-audit items).
- **Preferred names:** a Best Practice user can set the name MedUI shows for them (My settings, or
  Setup → Users), used everywhere in MedUI; redaction catches both names. Migration
  `f3a9c2d7b815` adds the columns (`flask db upgrade`).
- **Disease Profile:** recorded CKD and diabetes show the recorded stage or type, the year and the
  latest eGFR or HbA1c (HbA1c as %), with the KDIGO categories and Australian HbA1c targets as
  reference in their tooltips. Diabetes no longer counts borderline or gestational items.
- **Admin → Mapping Tables:** *condition_codes* (which Best Practice history codes count as each
  condition, with Best Practice's names) and *influences* (what a recorded condition means for
  reading a result), both created on first use and editable by the practice.
- **NIP eligibility** notes state the schedule and the record, without advice to the patient; the
  patient-screen flag reads "NIP funded, none recorded in interval". **COVID-19** follows the NIP
  criteria (health.gov.au, 1 October 2026): 75+ twice a year; 65–74, Aboriginal and Torres Strait
  Islander people 50–74 and adults 18–64 with severe immunocompromise once a year; Medicare needed.
- **Included but off:** two results badges ("eGFR < 60 for 3+ months", "HbA1c ≥ 6.5% on 2
  occasions") and **Doctor Data → Criterion Review** (patients whose results meet the eGFR or
  HbA1c criterion without the diagnosis recorded). They state that results meet a diagnostic
  criterion, which goes beyond this edition's intended purpose (no alerts of its own), so
  `install defaults` writes them off on new installations and upgrades. Switching them on
  (Application Setup → General → Patient Record) is the practice's decision and responsibility,
  as with its own prompts; see the AI-use policy template.

## 0.19.0 — pre-release (October 2026)

Seeded prompts confined after a wording audit:

- **Default Info Sheet Prompt** (the system prompt behind the AI assistant's record prompts):
  keeps its writing rules (do the task asked, plain clinical language, no hyperbole, related
  results grouped with dates, social history units, identifiers left out). It now reports
  results with the laboratory's own flag and range, and doesn't diagnose, classify risk, compare
  results with targets or recommend tests, treatments, screening or vaccinations for the
  patient; general information about a condition or medicine is still fine. Removed: the
  result-grading rules, the clinical alert policies (diabetes thresholds, cholesterol risk
  categories and targets, FIB-4, PSA, blood pressure and weight categories), the preventive
  health and immunisation advice, the advice on urgency, and the assumptions that filled in
  missing social history. A practice that wants its own clinical policies writes them into its
  own prompts, which is its responsibility (Prompt Manager help).
- **Health Timeline 7/10 detail:** the chronological history is unchanged; the other sections
  now describe what is recorded (current measurements with dates, recent results with the
  laboratory's flags and values over time, immunisations, care team, actions and recalls)
  without grading, targets, "gaps" or screening rules.
- **Clinical Assistant** (a system prompt no seeded prompt used) dropped from the starter pack.
  **Library Assistant:** two typos fixed.

Existing installations: `install resync-seeds --dry-run`, then `install resync-seeds` brings the
new texts in where the practice hasn't edited them; `--archive-dropped` makes Clinical Assistant
inactive.

## 0.18.0 — pre-release (October 2026)

Synced from upstream, and the general chatbot guard:

- **General chatbot prompt** (seeded *Chatbot Generic*, from upstream's version 6): written for a
  health professional, not a patient; questions outside medicine answered as fully as needed; a
  question with a particular patient's details gets a one-line notice and general information
  about the topic at the level of the question, without restating or interpreting the patient's
  findings; replies that draw on evidence end with **Sources** (title, organisation, year;
  Australian where possible; links only for stable official addresses; marked as AI-suggested).
  Existing installations: `install resync-seeds` brings it in unless the practice has edited it.
- **Guardrail instructions** (added before every system prompt when scope instructions are on):
  - the out-of-scope mark now applies only to a diagnosis, treatment, medicine, dose, prognosis or
    other clinical opinion **about a particular patient**; unrelated questions are answered
    unmarked (before, harmless questions could be refused);
  - a new, non-blocking **legality** mark: when a request asks for help to do something unlawful,
    a neutral line, *"This request touched on questions of legality."*, shows above the reply.
    Questions about the law, legal and medicolegal duties, mandatory reporting, ethics and the
    regulation of medicines aren't marked.
- **Admin → Flagged AI Requests** (managers and owners): the marked requests by user, workflow,
  dates and kind of mark, each with its request and reply, under a statement of the practice's
  responsibility (including ARTG inclusion if MedUI is used or configured for diagnosis,
  treatment or patient advice). Help topic included.
- General chatbot page: general reference questions only, no patient details. Application Setup →
  AI scope: the wordings are headed **System prompt guardrail injections**.
- Practice AI-use policy template: the practice's responsibility for use and configuration outside
  the intended purpose, and an optional look at Flagged AI Requests.
- `scripts/build_seed_history.py` also refreshes `starter.json`'s checksum.
- No database changes.

## 0.17.0 — pre-release (October 2026)

Synced from upstream:

- **In-app help.** A **Help** link at the top right opens a help centre with search, showing
  the topics each person's role can use; small **?** buttons beside parts of the main screens
  open the relevant help in a side panel without leaving the page. 14 topics: logging in and
  access, finding a patient, the day sheet, results outside range, AI drafts and the
  Sending/Sent review, the AI assistant, the scribe, the chatbots, the Library, Comms,
  complaints and adverse events, My settings, prompts and workflows (including the practice's
  responsibility for prompts it writes), and every Application Setup tab.
- AI topics are hidden while AI is off (`AI_ENABLED`).
- `flask --app wsgi help check` checks the help files and that every **?** points to a
  section; `test_help_check` runs it.
- No database or seed changes.

## 0.16.0 — pre-release (October 2026)

Synced from upstream:

- **Practice timezone in Application Setup → General**: Brisbane, Sydney, Melbourne, Hobart,
  Adelaide, Darwin, Perth, another zone, or the installation's (`PRACTICE_TIMEZONE`). Applied
  at once, without a restart: MedUI's local time ("today" on the day sheet), dates shown and
  usage reports all follow it. Setup shows the zone in effect and the time there now.
- Usage reports take the practice's zone (they read the container's own, UTC, before).
- No database or seed changes.

## 0.15.1 — pre-release (October 2026)

- **The practice's timezone** is MedUI's local time: the app container takes `TZ` from
  `PRACTICE_TIMEZONE`. Before, it ran on UTC, so the day sheet opened on yesterday until
  10 am in Brisbane.
- The installers ask for the practice's timezone from a short menu (Brisbane, Sydney,
  Melbourne, Hobart, Adelaide, Darwin, Perth, or another zone), with Windows' own timezone
  pre-selected (`create_medui_wsl2.ps1`, and `install.sh` on a new installation). Enter
  accepts it; a city, a state or a zone name in any capitals also works (`vic`, `melbourne`,
  `australia/melbourne`), and anything unknown is asked again. `install.sh --timezone` takes
  the same forms; an installation otherwise keeps its own; unattended runs use the detected
  zone. Always a place, never an offset, so daylight saving changes by itself.

## 0.15.0 — pre-release (October 2026)

- **HTTPS for workstations** (`./install.sh --https`, [docs/https.md](docs/https.md)): Caddy
  on port 443 in front of MedUI, so other PCs can use it, including the microphone. Either
  the practice's own certificate (`--https-cert`, `--https-key`), or a MedUI root that may
  only vouch for MedUI's names and addresses (X.509 name constraints, checked at every run),
  from which Caddy issues and renews MedUI's certificate. Remembered on later runs; a new
  name needs `--https-new-root`. MedUI's own ports stay on 127.0.0.1.
- `TRUSTED_PROXIES=1` (set with HTTPS): MedUI takes the workstation's address and https
  from the proxy, so runs and usage record each PC, not the proxy. Also on the native route.
- Windows: `open_medui_https_port.ps1` (port 443, Private and Domain networks only) and
  `install_medui_root.ps1` (shows the root and its restriction, refuses an unrestricted
  root). Group Policy and Intune steps in the docs.
- `upgrade.sh` backs up the `https` folder and restarts Caddy.
- **Setup page for workstations**: with `--https`, Caddy also serves `http://<name>` (port 80,
  `--http-port` to move it). A PC that already trusts MedUI goes straight on to HTTPS; one
  that doesn't gets the root's thumbprint and a one-file `setup-medui.cmd` (root built in,
  asks for administrator approval, shows the restriction, refuses an unrestricted root, then
  opens MedUI). No files to copy between PCs. Everything else on port 80 redirects to HTTPS.
  `open_medui_https_port.ps1` opens port 80 too (`-HttpPort 0` to leave it closed).
- Installers: where IPv6 resolves but doesn't connect (seen on WSL2 with mirrored
  networking), `apt` crawled for many minutes with no output. `create_medui_wsl2.ps1` and
  `install.sh` now test IPv6 and use IPv4 for package downloads when it fails, show `apt`'s
  progress, and wait up to 10 minutes for the package lock instead of failing or hanging.

## 0.14.0 — pre-release (October 2026)

Synced from upstream:

- **General chatbot without a local model**: with the PII Erasure workflow left as draft,
  the chatbot now works instead of refusing every message. On the first message in each
  chat the user confirms a warning that there is no AI erasure step; a banner stays on the
  page; questions get rule-based redaction, the pre-send check and review. Replies are
  marked "Rule-based redaction only", and each such message is counted in the usage
  record. Setup → AI scope → "General chatbot without the PII Erasure workflow": allowed
  with a warning (default) or not allowed. An active PII Erasure workflow always runs
  first, and a failure refuses the message.
- **Deactivate** beside a pipeline's status in its editor (back to draft); Activate and
  Deactivate update the top menu at once.
- **General chatbot replies to a patient**: BP → and Email buttons hand a reply to Comms,
  where the patient is chosen, as from the Library.
- Docs: generic chatbot setup without a local model; the `first_names` redaction list.
- **`upgrade.sh`**: upgrades an installation in place. It shows what's new, takes a
  verified backup (database, `.env`, app data), builds the new image while the current
  one runs, upgrades the database, lists the seed changes to accept, starts MedUI, and
  prints the commands to go back if a step fails. **`scripts/windows/upgrade_medui_wsl2.ps1`**
  runs it in a WSL2 instance, optionally after a snapshot of the whole instance. An
  installation from before 0.14.0 gets the script from the new release.
- No database or seed changes.

## 0.13.0 — pre-release (October 2026)

Synced from upstream:

- **Results outside range** (inbox): a result is listed only when the laboratory flagged it or
  it lies outside the laboratory's stated reference range — no thresholds, multipliers or
  trend rules of MedUI's own. The list shows value, range and the lab's flag, sorted by date
  then patient; the "critical" count is gone. Each row opens a new page per patient
  (`/inbox/outliers/patient/<id>`): charts of the clicked test, the other results outside range
  in the latest batch, and tests that were outside range when last tested (older than five
  years behind a toggle), each with the latest value, range and previous values as data.
  With this, the inbox no longer raises alerts of its own, as the intended purpose states.
- **Pre-send review**: the AI assistant now uses the same Sending/Sent review as the chatbots
  and scribe; Sending/Sent also show the AI's instructions, and the scribe has an
  "Instructions" link under its pipeline choice.
- No database or seed changes.

## 0.12.0 — pre-release (October 2026)

- **Intended purpose** stated: MedUI is a workflow tool for appropriately registered health
  professionals in a medical practice; AI output is a draft they review; it does not diagnose,
  recommend treatment or investigations, triage or monitor patients. Full statement in
  [docs/intended_purpose.md](docs/intended_purpose.md), quoted in the README and AGENTS.md.
- **About page** (`/about`, open without signing in): the intended purpose and version. The
  version at the foot of every page links to it.
- Releasing: checklist items for the intended purpose, and the wording to avoid in the app,
  prompts, docs and website.
- Note: the inbox outlier flags still use their own thresholds until the matching upstream change is synced;
  that sync is needed before the statement's "no alerts of its own" holds in this edition.

## 0.11.0 — pre-release (October 2026)

Synced from upstream:

- **AI guardrails, on by default here** (Application Setup → AI scope): a scope instruction
  before every workflow's system prompt (record / scribe / correspondence / general / none),
  out-of-scope replies flagged and recorded; a request check on what users type (recorded
  only); editable one-line notices above AI output, chosen per workflow.
- **Pre-send review**: before a cloud call, the prompt is checked for the patient's or a
  practitioner's identifiers; a hit holds it on a **Sending** tab (AI assistant, both chatbots,
  scribe) to remove or edit; **Sent** shows what went. Users may review every request.
- **My settings** for each user, with practice defaults and locks (Application Setup → User
  defaults). The chatbots remember the last model chosen.
- The AI assistant shows the AI's instructions, read-only.
- The Library is not linked to patients; Comms chooses the patient and files to Best Practice.
- A clinical-phrase guard in redaction looks on the same line only.
- Removed: the unused inline AI assist (`/ai/scan`, `/ai/submit`).
- Seed format 4: each seeded system prompt names its scope; summary and scribe workflows
  choose their notice. Existing installs: `db upgrade`, `install defaults` (turns the
  guardrails on where never set), then `install resync-seeds` (fills scopes and notices).
- Database: `user_preferences`, `scope_wordings`, `system_prompts.scope_key`.
- `.gitignore`: `.venv` and `venv` match a symlink as well as a folder.

## 0.10.1 — pre-release (October 2026)

- The app image makes its files readable to the app user whatever the checkout's permissions.
  A `git pull` run with a restrictive umask (left over from the backup command) made changed
  files unreadable and every `flask` command failed with `PermissionError`.
- The backup command in [operations](docs/operations.md) keeps `umask 077` to the dump alone.

## 0.10.0 — pre-release (October 2026)

- **Seed resync** (`flask install resync-seeds`): after an upgrade, brings seeded system
  prompts, prompts and workflows up to the release. Only items still exactly as an earlier
  release seeded them are updated; edited ones are listed and left alone (`--replace` to
  override). Each workflow keeps its model, data bundle and status; items the practice
  created are never touched. Dropped items are listed, and archived with `--archive-dropped`
  (never deleted). Replaced prompt text is kept as an earlier version. `--dry-run` lists
  the changes first. See [seed data](docs/seed-data.md#after-an-upgrade-seed-resync).
- Database: new table `user_prompt_versions` (run `db upgrade`).
- `app/seed_assets/seed_history.json`: fingerprints of every released seed, rebuilt by
  `scripts/build_seed_history.py` when the starter pack changes.

## 0.9.0 — pre-release (October 2026)

### Fixed after first trials

- Setup → External services → Test failed with "name 'current_app' is not defined" instead of
  testing the LiteParse connection. Two similar missing imports fixed (an error path of the data
  bundle test, and BP user sync), and a test now checks the app for undefined names.
- The OCR address hint in Setup shows the address configured for this installation
  (`http://liteparse:5707` under Compose) instead of `127.0.0.1`, which doesn't reach
  LiteParse from inside the app container. The upgrade steps give the rebuild commands.
- A setup guide for IT providers (`docs/setup-guide.md`): OCR address, turning on AI, providers,
  activating workflows, updating, applying `.env` changes and reconnecting the database.
  Administrators can open it, with troubleshooting, operations, OCR and seed data, from
  **Application Setup → Installer guide**; the docs are now included in the app image.

The first versioned build, for trial installations before the first public release (1.0.0).

- Practice-hosted installation with Docker on Ubuntu or WSL2 (`install.sh`), and a Windows script
  that creates the WSL2 instance and checks the GitHub token before installing.
- Redaction for cloud AI requests, identical to upstream's rules at the time: patient, practitioner
  and staff identifiers, other people's contact details and addresses, labelled identifiers
  (`[ID Removed]`), with requests refused if a patient's details can't be loaded.
- Seeded draft workflows and prompts, the generic chatbot, and the identifier-label list (seed format 3).
- Starter seeds: **Life Expectancy Discussion removed**; **Second Opinion replaced by Case Summary**, a
  factual summary of what is recorded (active conditions, medications, allergies, recent results with
  the laboratory's own flags, recent visits, outstanding items recorded, clinicians involved), with its
  own system prompt and no diagnoses, differentials or recommendations. Seed installation only adds,
  so an existing installation keeps Life Expectancy Discussion and Second Opinion until an
  administrator deletes them in the Pipeline Designer and Prompt Manager.
- AI output is marked as a draft: a notice above the AI assistant's output, the scribe's note and both
  chatbots says the content is AI-drafted and must be checked. The notice is on screen only; it isn't
  copied, printed or filed with the draft.
- Starter seeds reduced to functions the manufacturer considers not to be medical devices. Removed,
  pending advice from the TGA: Interaction Checker, Medication Review, Developmental Milestones, the
  pathology result explainers and SMS, Report Explainer, the GP chronic conditions and mental health
  care plans, Health Status Report, and the prompts that personalise lifestyle advice from a patient's
  record (exercise, hypertension, travel, meal planner, Mind Gymnasium). As for every seed change,
  existing installations keep their copies until an administrator deletes them.
- Remaining AI prompts confined to their purposes:
  - Scribe: the consultation is organised into the issues discussed, whether or not they are existing
    diagnoses, optionally grouped under a heading where they overlap. Each is headed by a diagnosis the
    doctor stated or the record holds, or else a plain description of the problem. No added diagnoses,
    inferred management, inferred examination findings, or actions that weren't discussed.
  - Consultation To-Do List: only items the record shows as outstanding (referrals, results, recalls,
    documented actions), plus recent issues; no suggestions.
  - Document summary: summary only, as stated in the document. The patient-explanation mode is removed;
    the workflow is now Summarise Document, and its buttons read "Summarise with AI".
  - The [SUM] document button now works on a fresh install: a Document Summary workflow (classifier
    `[SUM]`) is seeded. [EXP] runs the same summary under its existing label.
  - User Query: its own system prompt, Record Questions (factual): answers about what is recorded,
    without diagnosis or management advice.
- Chatbot system prompts confined to their purposes: the patient chatbot answers only about what is
  recorded, with no diagnoses, risk assessment or management recommendations; the general chatbot is a
  medical reference for registered practitioners, for general questions rather than a specific patient.
- Optional provenance footer on AI drafts filed to Best Practice from the AI assistant or the scribe
  (Setup → Messaging, off by default): `AI-assisted draft · filed by … · date and time · MedUI ref …`,
  with the model name as a further option.
- Default Info Sheet Prompt (the system prompt most seeded prompts use) no longer tells the model to
  hide that it is AI; it asks for plain, natural clinical language instead. Existing installations keep
  their copy until an administrator edits it in the Prompt Manager.
- Observation Anomalies report for administrators.
- One gunicorn worker (pipeline progress queues are per process).
- Troubleshooting guide; templates for a practice AI-use policy and a process for patient concerns.

Before 1.0.0: an AI information sheet will be published with the release.
