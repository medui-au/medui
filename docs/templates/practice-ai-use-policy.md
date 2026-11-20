# [Practice name]: policy on the use of AI in MedUI

*A starting point from MedUI. An administrator adapts it in MedUI (Governance → AI-use policy →
Edit), replacing everything in square brackets, and has it approved. Appendix A lists the AI
providers and models enabled at the moment the policy is opened, printed or downloaded: keep a copy
in the practice's document management whenever the policy is approved or a provider or model
changes. Delete this paragraph once the policy is adapted.*

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

## 2. The clinician is responsible

- Everything AI produces is a **draft**. The clinician who runs the function reads it all, checks it
  against the record, and corrects it before it is saved, sent or acted on.
- The clinician remains responsible for anything they file, send or act on, as for any other
  document they write.

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

This policy is reviewed every year, and whenever a provider or model is added or changed. Each
approved version is kept, with its Appendix A, in the practice's document management.

## Appendix A: AI providers and models enabled

<!-- medui:enabled-ai -->
*Filled in by MedUI (Governance → AI-use policy) with the providers and models enabled at that
moment. Keep these two marker lines where the list should go.*
<!-- /medui:enabled-ai -->

**Checked by the practice principal or AI coordinator:** none of the providers above is permitted to
train on the practice's requests, or to keep them beyond a limited period for abuse and safety
monitoring. Name: [name] · Date: [date]
