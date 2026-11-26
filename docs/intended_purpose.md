# MedUI — Intended purpose

This is MedUI's intended purpose: what it is for, who it is for and what it does not do. The same
statement appears in the README, AGENTS.md, the [AI information sheet](ai-information-sheet.md), the
About page in the app (linked from the version number at the foot of every page) and the release
notes. Change it here first; see
[releasing](maintainers/releasing.md).

## Statement

MedUI is a workflow tool for appropriately registered health professionals working in a medical
practice. It helps them find, organise, present, summarise and document information that is already
in the patient record or was stated in the consultation, shows what named, published guidance says,
with its source, when they ask, and streamlines practice communication and administration. AI
features produce drafts for the health professional to review, edit and approve.
MedUI does not diagnose, recommend treatment or investigations, triage or monitor patients. It
provides information. Clinical judgement, decisions about a patient's care and the record remain
with the health professional.

## What it is

Workflow software for appropriately registered health professionals and staff in a general
practice. It runs on the practice's own systems beside Best Practice, which it reads but never
changes.

## What it is for

- **Finding and presenting what is recorded:** the patient record, results charted with the
  laboratory's own flags and reference ranges, documents and correspondence, organised and searched
  for the health professional.
- **Documentation:** drafting consultation notes from what was said in the consultation, and
  summaries of documents and the record, without adding clinical content that wasn't said or
  recorded.
- **Reference:** on request, showing what named, published guidelines and medicine references say
  about topics the health professional names or that are recorded, with the source, for the health
  professional to read and weigh.
- **Communication and administration:** drafting letters and messages for a person to review and
  send; appointments, recalls, inbox handling, billing reports, practice governance.
- **Privacy protection:** removing identifying details before text is sent to an AI service, and
  restoring them in the draft returned.
- **Simple published calculations and schedules** (for example FIB-4, NIP funding eligibility),
  shown with their formula or rule, inputs and source.
- **Record-quality audits:** audits of record completeness against published criteria (for example
  results that meet a published criterion where the condition isn't coded in the record), shown with
  the results, rule and source, for a doctor to review. A criterion met is not a diagnosis.
- **Rules a user chooses to display:** a user can switch on, for the patients they view, badges that
  apply a stated rule to recorded results (for example "no diabetes coded; the highest of the last 3
  HbA1c results is 6.5% (48 mmol/mol) or more"). Each is shown with the values, dates, rule and
  source.

## Who it is for

- **Appropriately registered health professionals** (for example doctors and nurses) working in a
  medical practice, within their own scope of practice. The practice decides which of them may use
  the AI features.
- **Other practice staff** (reception, practice managers) use the non-AI record, communication and
  administration functions.

MedUI is not intended for use by patients or the public: nothing reaches a patient unless a health
professional or staff member reviews and sends it.

## How AI output is handled

Every AI output is a draft, marked as such, for the health professional to review, edit and approve
before it is filed or sent. The practice can see what was sent to the AI service and the
instructions it was given.

## What it is not for

MedUI does not:

- diagnose, or suggest diagnoses or differentials;
- recommend or rank treatments, medicines, doses, tests or referrals for a patient;
- assess or classify a patient's risk, or tell the health professional what a patient's results
  mean for their diagnosis or treatment; where it shows that results meet a published criterion or
  a rule a user has chosen to display (above), it shows the values, rule and source and leaves the
  conclusion to the health professional;
- triage, prioritise, monitor patients or raise clinical alerts of its own;
- act on its output without a person reviewing it.

It provides information; decisions about a patient's care are the health professional's.

## Practice configuration

Practices can write their own prompts, workflows and care-plan recipes. This intended purpose
covers what MedUI ships with. A practice that configures MedUI to diagnose, recommend treatment,
triage or advise patients is using it outside this purpose, is responsible for that use, and may
become the manufacturer of a medical device.
