# MedUI — Intended purpose

This is MedUI's intended purpose: what it is for, who it is for and what it does not do. The same
statement appears in the README, AGENTS.md, the About page in the app (linked from the version
number at the foot of every page) and the release notes. Change it here first; see
[releasing](maintainers/releasing.md).

## Statement

MedUI is a workflow tool for appropriately registered health professionals working in a medical
practice. It helps them find, organise, present, summarise and document information that is already
in the patient record or was stated in the consultation, and it streamlines practice communication
and administration. AI features produce drafts for the health professional to review, edit and
approve. MedUI does not diagnose, recommend treatment or investigations, triage or monitor patients;
clinical judgement and the record remain the health professional's.

## Intended users

- **Appropriately registered health professionals** (for example doctors and nurses) working in a
  medical practice, within their own scope of practice. The practice decides which of them may use
  the AI features.
- **Other practice staff** (reception, practice managers) use the non-AI record, communication and
  administration functions.

MedUI is not intended for use by patients or the public, and nothing it produces is sent to a
patient without a health professional or staff member reviewing and sending it.

## What MedUI does

- **Flexible handling and presentation of the patient record:** finding, organising and displaying
  recorded information, including results charted against the laboratory's own reference ranges,
  without interpreting it.
- **Clinical documentation:** drafting consultation notes from what was said in the consultation,
  and summarising documents and the record, without adding new clinical content.
- **Streamlining practitioner–patient communication:** drafting letters and messages for the health
  professional to review, edit and send.
- **Practice administration:** appointments, recalls, inbox handling and similar tasks.
- **General reference for health professionals:** a general chatbot that answers reference questions
  from registered health professionals. It is not for entering a patient's presentation to obtain a
  diagnosis.
- **Privacy protection:** removing identifying details before any text is sent to an AI service, and
  restoring them in the returned draft.

## How AI output is handled

Every AI output is a draft, marked as such. The health professional reviews, edits and approves it
before it is filed or sent. The practice can see what was sent to the AI service and the
instructions it was given.

## What MedUI does not do

- Diagnose, or suggest diagnoses.
- Recommend treatment, medicines, doses or investigations.
- Triage, prioritise or rank patients or results.
- Monitor patients or raise alerts of its own; results are shown with the laboratory's own flags and
  reference ranges.
- Act on its output without a person reviewing it.

## Practice-configured prompts

Practices can write their own AI prompts and workflows. MedUI's intended purpose covers the prompts
it ships with. A practice that configures a prompt for a therapeutic or diagnostic purpose is using
MedUI outside this intended purpose and is responsible for that use.
