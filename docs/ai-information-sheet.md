# MedUI — AI information sheet

**For:** practices deciding whether to use MedUI's AI functions, the clinicians who use them, and
anyone reviewing them. **You'll know:** every AI function MedUI ships, what each is for, what it
reads, where it can run, its limits, and where it sits against MedUI's intended purpose.

**Version:** MedUI 0.59 (pre-release, November 2026). This sheet changes with any release that adds,
removes or rewords a shipped AI function; see the [changelog](../CHANGELOG.md).
**Support:** [getting help](support.md), or an issue at
[github.com/medui-au/medui/issues](https://github.com/medui-au/medui/issues), without patient details.
A security problem goes privately: [SECURITY.md](../SECURITY.md).

## In brief

- MedUI's AI functions **draft**: summaries, notes, answers about the record, letters and plan
  wording. Every output is a draft for a health professional to review, edit and approve before it
  is filed or sent. Nothing acts on its own.
- AI is **off until the practice sets it up**: it chooses the AI providers and models, and switches
  on each workflow. The seeded workflows arrive as drafts with no model.
- **Local or cloud.** A local model runs on the practice's own equipment, and nothing leaves the
  practice. Before anything goes to a cloud model, MedUI removes the patient's identifiers and
  practitioners' names, and puts them back in the reply on screen. No redaction method is perfect.
- **Audio is not redacted.** With a cloud speech-to-text service, the consultation recording goes
  to that service as it is. A local speech-to-text server keeps it in the practice.
- The practice sees what is sent: the Sending and Sent tabs show the request as the AI service
  receives it, and the instructions it was given.

## Intended purpose and regulatory status

MedUI is a workflow tool for appropriately registered health professionals working in a medical
practice. It helps them find, organise, present, summarise and document information that is already
in the patient record or was stated in the consultation, shows what named published guidance says
when they ask, and streamlines practice communication and administration. AI features produce
drafts for the health professional to review, edit and approve. MedUI does not diagnose, recommend
treatment or investigations, triage or monitor patients; it provides information, and clinical
judgement, decisions about a patient's care and the record remain the health professional's.

The full statement, including what MedUI is not for, is in [intended purpose](intended_purpose.md).
MedUI has not been assessed by the Therapeutic Goods Administration and is not included in the
Australian Register of Therapeutic Goods. It is supplied for the purpose above. A practice that
writes its own prompts or workflows to diagnose, recommend treatment, triage or advise patients is
using MedUI outside that purpose, is responsible for that use, and may become the manufacturer of
a medical device.

## The AI functions

Each function runs one of the practice's AI workflows (the seeded workflow names are given in
*italics*). "Reads" is what the workflow gives the AI; for a cloud model it is redacted first.

### AI assistant (from a patient)

| Workflow | What it is for | Reads |
|---|---|---|
| *Case Summary* | A factual summary of the recorded patient data, for the clinician to review | The patient's record (a data bundle the practice can change) |
| *Consultation To-Do List* | Items the record shows as outstanding, and recent issues, for the next doctor | The patient's record |
| *User Query* | An answer to a question the clinician types about this patient's record | The patient's record and the question |
| *Diabetes Education - Medication* | A draft information sheet on the groups of diabetes medicines, in the order the Australian diabetes algorithm introduces them, for the clinician to check before giving it | The patient's record, as context |

The assistant also offers the practice's other prompts (for example a results grid or a health
timeline) as requests the clinician can choose. **Limits:** a summary can leave things out, add
things that aren't recorded, or misread a date or value: check it against the record.

### Document summary (beside a document or result)

| Workflow | What it is for | Reads |
|---|---|---|
| *Document Summary* (the **[SUM]** link) | A summary of one clinical document or report, for the clinician | The document's text |
| *Summarise Document* | A document summary with the patient's record for orientation only | The document's text and the record |

*Summarise Document* is the workflow behind the **[EXP]** link, which is hidden in this release and
starts nothing. **Limits:** the text of a scanned document comes from text recognition (OCR), which
can misread; check the summary against the document.

### Chatbots

| Workflow | What it is for | Reads |
|---|---|---|
| *Patient Chatbot* | Questions about what is recorded for a patient, answered only from the record, one run per question | The patient's record and the conversation |
| *PII Erasure* | The general chatbot's first step: a **local** model removes identifying details from the question. Local models only; nothing is sent out | The question |
| *Chatbot Generic* | Reference questions with no patient (a medicine, a guideline, a form), with sources | The question, after rule-based redaction |

**Limits:** the general chatbot has no patient record and is not for a particular patient's
presentation. If a question includes a patient's details, the reply says so and gives general
information only. Sources are suggested by the AI and can be wrong: check them. Without a local
model there is no erasure step, and the chat says so.

### Scribe

| Step | What it is for | Reads |
|---|---|---|
| Speech-to-text (the practice's ASR model) | Turning the consultation's audio into a transcript | The recording, **not redacted** |
| Speaker labels (a local model) | Marking who said what, where the speech-to-text service doesn't | The transcript; local models only |
| *[SCRIBE] Cloud Normal*, *[SCRIBE] Cloud Issues List* | A draft consultation note, in prose or as an issues list, from the transcript | The transcript |

**Limits:** the note is written from what was said: check it against the consultation and what was
examined. Names spoken differently from how they are recorded can get past redaction; the Sending
tab shows what will go. Follow the practice's policy on telling patients and asking their consent
before recording.

### Writing and planning

| Workflow | What it is for | Reads |
|---|---|---|
| *[LIB] Library Pipeline* | Drafting or changing a practice document in the Library (an information sheet, a letter template) | The request and the document; no patient |
| *GP Chronic Condition Management Plan (draft)* | Wording each issue of a care plan from the doctor's recorded decisions and the practice's own protocol | The decisions, the protocol and the record |

For the care plan, MedUI itself writes the targets, prevention lines, review and consent, and checks
the AI's draft against the doctor's decisions. The AI may not change or add to the decisions. The
care-plan **recipe assistant** and the population chart's **analysis** use workflows the practice
creates itself; none is shipped.

## Limits that apply to every function

- **Drafts only.** AI can leave things out, add things that aren't there, or get a number, date or
  name wrong. The health professional checks every draft against the record, the document or the
  consultation before using it, and remains responsible for what is filed or sent.
- **The seeded wording is a starting point.** The seeded prompts and workflows come from MedUI's
  earlier versions, written for one practice. They have not been clinically validated for others. A practice
  reviews each one, and the data it reads, before switching it on.
- **Redaction is not perfect.** It recognises identifiers by their pattern and from the practice's
  own lists. Something written unusually can get through, so check the Sending tab when it appears.
- **Models differ, and change.** Output depends on the model the practice chooses. A provider can
  change a model without notice. The practice's AI-use policy records which providers and models
  are in use.
- **No clinical decisions.** No AI function diagnoses, recommends treatment, ranks options, triages,
  monitors or raises alerts.

## What is not AI

These work the same with AI switched off, and each shows its rule, inputs and source:

- the eGFR and HbA1c badges a user switches on, the criterion review, FIB-4 and NIP funding
  eligibility;
- the protocol preselection of a patient's target, and the care plan's targets, prevention and
  review lines;
- rule-based redaction;
- text recognition of scanned documents (OCR).

## For the practice

- Adopt an AI-use policy before switching AI on: MedUI includes a template (Governance → AI-use
  policy). MedUI keeps every saved version, who approved it and when, with the list of providers
  and models in use when it was saved.
- Choose local or cloud models for each workflow. Cloud models get redacted requests only, under
  the practice's obligations under the *Privacy Act 1988*.
- Report a problem with an AI output through the practice's own process, and to the MedUI
  maintainers without patient details ([getting help](support.md)).

[Back to MedUI](../README.md)
