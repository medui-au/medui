*The practice's AI-use policy is an essential underpinning of responsible and compliant AI use in
a medical practice.*

*This template is best read and edited within MedUI: Governance → AI-use policy. Each time the policy
is saved, MedUI keeps it as a new version, with the inventory of AI providers and models in use at
that moment (Appendix A), and records who approved each version and when.*

*Below is the default template before editing.*

---

# [Practice name]: policy on the use of AI in MedUI

*A starting point from MedUI. An administrator adapts it in MedUI (Governance → AI-use policy →
Edit), replacing everything in square brackets, and approves it there. MedUI keeps every saved
version with Appendix A as it was when that version was saved (Governance → AI-use policy →
Versions); on screen, Appendix A shows the AI providers and models enabled now. Delete this
paragraph once the policy is adapted.*

**Approved by:** [name, role] · **Date:** [date] · **Next review:** [date, at most a year away]

## 1. What AI is for

AI in MedUI is an **administrative and research assistant for the clinician using it**. It may:

- summarise and organise what is already in a patient's record: documents, results, history;
- draft notes from a consultation, letters, summaries, care plan wording and task lists;
- find and summarise information the clinician asks about, from the record or from published
  sources, for the clinician to weigh.

AI is **not** positioned to give diagnostic or management advice to clinicians, practice staff or
patients. It does not diagnose, recommend treatment, triage, or replace the clinician's own
assessment, and it is not used in emergencies.

**Questions you type.** You may ask AI to find and organise what is in a patient's record, and to
tell you what named guidelines say, with sources. Don't ask it to decide for you: which diagnosis,
which treatment or dose, whether to refer, or how urgent. Its prompts are written to answer such
questions with the record and the guidance only, and MedUI notes requests like these for the
practice (Admin → Flagged AI Requests).

**Guideline content is AI-suggested.** Check it against the source before relying on it.

**Prompts and care-plan recipes the practice writes** are the practice's responsibility. One that
asks AI to diagnose, recommend treatment, triage or advise patients takes MedUI outside its
intended purpose, and may make the practice the manufacturer of a medical device.

**Practice protocols for care plans.** The practice's protocol (Admin → Practice Protocols) holds
its target options, its wording for each condition and its prevention lines, with the guidelines
behind them. It is the practice's content: an administrator approves each version, and it is
reviewed at least every 12 months and whenever a guideline it cites changes. Where a condition is
coded in the record, MedUI preselects the protocol's option for it; the doctor confirms or changes
every target and makes every decision in the plan. AI only words the care plan from those
decisions: it does not choose targets, issues, services or treatment, and MedUI checks its draft
against the decisions before the doctor sees it.

## 2. The clinician is responsible

- Everything AI produces is a **draft**. The clinician who runs the function reads it all, checks it
  against the record, and corrects it before it is saved, sent or acted on.
- The clinician remains responsible for anything they file, send or act on, as for any other
  document they write.

**Medicolegally sensitive discussions.** AI must not be used to document a consultation, or any
part of one, that is medicolegally contentious. Examples include an adverse outcome or error, open
disclosure, a complaint or dispute about care, or anything the practitioner expects may lead to a
complaint, claim or regulatory inquiry. The practitioner documents these personally, in line with
accepted ethical conduct, the Medical Board's code of conduct and the advice of their medical
indemnity insurer. If the scribe was running, its draft for that part is discarded. The scribe's
instruction to avoid wording that could read as an admission governs phrasing only. It never
permits leaving out facts, and the practitioner remains responsible for the record being complete
and accurate.

## 3. Patient information

- **No unredacted or identifiable patient information goes to a cloud AI service.**
- Staff do not type or paste identifying details into a question for a cloud model, and do not copy
  patient information into AI tools outside MedUI.
- Patients are told, by [the practice's privacy policy / a notice / discussion at the consultation],
  that AI may be used to help prepare notes and documents. Before a consultation is recorded for the
  scribe, the patient is asked and may decline.

## 4. Providers and models

- Only the practice principal or the practice's named AI coordinator(s) may enable or change an AI
  provider, a model or a prompt. Changes are made only in MedUI: providers and models in Application
  Setup, prompts in Prompt Manager and Pipeline Designer, which keep earlier versions of prompts.
- **No provider or model is enabled whose terms allow it to train on the practice's requests, or to
  keep them beyond a limited period for abuse and safety monitoring.** Before enabling one, the
  practice principal or AI coordinator checks the provider's terms and data settings (for example
  zero data retention) and records the check in Appendix A.
- MedUI's prompts and workflows stay within the limits in section 1.

## 5. Who may use AI

AI functions are available to doctors[, registered nurses] and practice managers, at the discretion
of the practice principal. Reading this policy is a condition of being given access to AI functions.

## 6. When something goes wrong

- Wrong or harmful output, or an identifier seen in a request to a cloud model, is reported to the
  practice principal or AI coordinator, recorded in MedUI (Governance → Adverse events), and reported
  to the MedUI maintainers without patient details.
- A patient's concern about AI is handled under the practice's process for concerns about AI and
  its complaints policy.

## 7. Review

This policy is reviewed every year, and whenever a provider or model is added or changed. MedUI
keeps each saved version, who approved it and when, and its Appendix A as it was when it was saved
(Governance → AI-use policy → Versions).

## Appendix A: AI providers and models enabled

<!-- medui:enabled-ai -->
*Filled in by MedUI (Governance → AI-use policy) with the providers and models enabled at that
moment. Keep these two marker lines where the list should go.*
<!-- /medui:enabled-ai -->

**Checked by the practice principal or AI coordinator:** none of the providers above is permitted to
train on the practice's requests, or to keep them beyond a limited period for abuse and safety
monitoring. Name: [name] · Date: [date]
