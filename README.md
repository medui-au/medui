# MedUI

**A workflow tool for general practices that use Best Practice.** MedUI runs on the practice's own
computer, beside Best Practice (BP). It reads the BP record (read-only) and presents it in clinical
views, a document viewer, an inbox, the day's appointments, reports and charts. With AI switched
on, it prepares summaries, letters and consultation notes as drafts for the clinician to check,
and removes patient identifiers before any text leaves the practice.

<!-- Hero screenshot (demo data) goes here: docs/images/patient-view.png -->

> **Pre-release.** MedUI is not a validated clinical product. See [release status](docs/release-status.md)
> for what is done and what is not.

## I want to…

| | |
|---|---|
| **See what it does** | [What it does](#what-it-does), below; each screen's own help is in [app/help](app/help/) |
| **Install it** | [Choose how to install](docs/install/README.md): one script, a few questions |
| **Know how it keeps patient data safe** | [Privacy and security in brief](#privacy-and-security-in-brief), below |
| **Know what it is for, and the rules if I change it** | [Intended purpose](docs/intended_purpose.md) · [AI information sheet](docs/ai-information-sheet.md) · [If you change MedUI](#if-you-change-medui) |
| **Read the technical detail** | [How it's built](docs/technical.md) |
| **Get help** | [Troubleshooting](docs/troubleshooting.md) · [Support](docs/support.md) · [Report a security problem](SECURITY.md) |

What's new: [changelog](CHANGELOG.md). Licence: [GNU AGPL v3](LICENSE); copyright, third-party
components and what the licence asks of you if you change MedUI: [NOTICE](NOTICE).

## What it does

- **The patient record, arranged for a consultation:** summary, history, medicines, results with
  their charts, documents and correspondence, care plans.
- **The practice's work:** the inbox, the day's appointments, results outside their range, reports
  and the practice's own queries.
- **AI drafts, when the practice switches them on:** document and record summaries, letters, care
  plans, a scribe for consultation notes, and chatbots. Every draft is for a clinician to review,
  edit and approve.
- **Governance:** a usage record, a privacy review of what was sent, and the practice's own prompts
  and workflows under its control.

Nothing optional is on until the practice turns it on, and the AI workflows arrive as drafts with
no model chosen.

## Intended purpose

> MedUI is a workflow tool for appropriately registered health professionals working in a medical
> practice. It helps them find, organise, present, summarise and document information that is already
> in the patient record or was stated in the consultation, shows what named published guidance says
> when they ask, and streamlines practice communication and administration. AI features produce
> drafts for the health professional to review, edit and approve. MedUI does not diagnose, recommend
> treatment or investigations, triage or monitor patients; it provides information, and clinical
> judgement, decisions about a patient's care and the record remain the health professional's.

Who it is for, and what it does and does not do: [intended purpose](docs/intended_purpose.md).

## Privacy and security in brief

- **It reads BP and never writes to it.** It uses the read-only login BP supplies under an
  Elevated Database Access Agreement, and checks that the login is read-only.
- **It runs on the practice's computer.** It is reached only from that computer until the practice
  sets up HTTPS for its workstations ([HTTPS](docs/https.md)). It should never be opened to the
  internet.
- **Identifiers come out before any cloud AI.** Patient and practitioner identifiers are replaced
  with placeholders, the text is checked again before it is sent, and the names are put back in
  the answer. A run that isn't fully redacted can only go to a model the practice runs itself.
  Audio for the scribe is the exception: a cloud speech-to-text service receives the recording as
  it is, and a local Whisper keeps it inside the practice.
- **Redaction is an aid, not a guarantee.** It is rule-based and improves with each release; a
  local model is always an option.
- **The practice stays in charge:** who may use AI (by BP group), which provider and model, which
  prompts. Templates for an [AI-use policy](docs/templates/practice-ai-use-policy.md), an
  [AI concerns process](docs/templates/ai-concerns-process.md) and the
  [request to BP for database access](docs/templates/bp-database-access-request.md) are included.

## If you change MedUI

You can adapt prompts, workflows, lists and settings in the app; they are the practice's to
review and its responsibility. If you change the code, keep the safeguards: the check before
anything is sent to a cloud model, redaction (which comes from a separate library and is never
edited in the app), the read-only BP connection, and the login and form protections. Changing what
MedUI does, for example to diagnose, triage or recommend, takes it outside its intended purpose.

MedUI is under the GNU Affero General Public License v3. If you change the code and let others use
your version over a network (a practice's staff count), the licence asks you to offer them your
version's source code. See [NOTICE](NOTICE).

Using a coding agent (Claude Code, Codex or similar)? Have it read [AGENTS.md](AGENTS.md) first: it
sets out the rules an agent must keep to.
