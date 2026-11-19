# [Practice name] — policy on the use of AI in MedUI

*Template from the MedUI release. Adapt it to your practice, have it approved by the practice
principal, review it yearly, and keep it with your other policies. Replace everything in square
brackets.*

**Approved by:** [name, role] · **Date:** [date] · **Next review:** [date]

## 1. Purpose

This policy sets out how [practice name] uses the AI functions in MedUI: which are allowed, who may
use them, and the checks that apply. It supports our obligations under the *Privacy Act 1988*,
AHPRA's expectations of practitioners using AI, and the RACGP Standards.

## 2. What is allowed

- AI in MedUI may be used to prepare **drafts** from a patient's record or a consultation: notes,
  summaries, letters, task lists and answers to questions about what is recorded.
- Only the AI functions and models listed in Appendix A are enabled.
- AI must not be used to make a diagnosis, choose a treatment or give advice to a patient without the
  clinician's own assessment.

## 3. Who may use it

- AI functions are available to [doctors / nurses / named roles] once they have read this policy and
  the MedUI AI information sheet.
- Reception and administrative staff [do / do not] have access to AI functions.

## 4. Checking every output

- The clinician who runs an AI function reads the whole draft, checks it against the record, and edits
  it before it is saved, sent or acted on.
- The clinician remains responsible for anything they file, send or act on.
- AI output is not used in emergencies.

## 5. Patient information and models

- Requests to cloud models are redacted by MedUI. Staff must not paste identifying details into
  free-text questions sent to a cloud model.
- Our enabled models, where they process data, and whether they use it for training are listed in
  Appendix A.
- Scribe: we use [local speech-to-text / a cloud speech-to-text provider, which receives the
  consultation audio]. Patients are told before a consultation is recorded, and may decline.
- Patients are told, through [our privacy policy / a notice / verbal consent], that AI may be used to
  help prepare notes and documents.

## 6. Changes and problems

- Only [the practice principal / named person] may enable a model or provider, or change a prompt.
  Changes are recorded in [the governance register].
- Prompts and workflows are kept within MedUI's intended purpose (documentation and workflow). If
  MedUI is used, or configured through its prompts and workflows, for diagnosis, treatment
  recommendations or advice to patients, that use is the practice's responsibility, and configuring
  it that way may make the practice the manufacturer of a medical device that must be included in
  the ARTG (or meet an exemption) first. We seek advice before any such use.
- The results badges and **Doctor Data → Criterion Review** (Application Setup → General → Patient
  Record) are off unless the practice switches them on. They state that a patient's results meet a
  diagnostic criterion; switching them on is the same kind of decision, made by [the practice
  principal / named person], recorded in [the governance register], with the same advice first.
- [Optional] [Named person] looks at **Admin → Flagged AI Requests** from time to time: requests the
  checks marked as asking for a diagnosis, treatment or similar, replies the AI marked out of
  scope, and requests that touched on questions of legality.
- Any wrong or harmful output, or an identifier seen in a request, is recorded in MedUI's adverse
  event register and reported to [named person] and to the MedUI maintainers.
- Patient concerns about AI are handled under our process for concerns about AI (see the separate
  template) and our complaints policy.

## Appendix A — enabled AI functions and models

| Function | Model / provider | Local or cloud | Data location | Used for training? |
|---|---|---|---|---|
| [e.g. Scribe write-up] | [e.g. local Whisper + local model] | [Local] | [Practice] | [No] |
| | | | | |
