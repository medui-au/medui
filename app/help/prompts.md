---
title: Prompts and workflows
area: Administration
roles: [admin]
requires_ai: true
reviewed: 2026-11-03
related: [ai-drafts]
---

**Prompt Manager** and **Pipeline Designer** (practice managers and owners) set what the AI
functions do: the instructions each one gives the AI, and how a request is put together.

## Prompts {#overview}

- **System prompts** are standing instructions: how the AI should behave and what it may do.
  When the practice has switched it on (Application Setup → AI scope), MedUI adds its
  **scope** wording before each one, which keeps answers to the record and to drafting.
- **User prompts** are the request itself, often with the patient's record or a question put
  into it. Each is bound to a system prompt, and has a temperature and a length limit.
- Every change keeps a **version**, so you can see what changed and when. Users can read the
  instructions a workflow gives the AI on the AI pages.

The prompts MedUI ships with are reviewed against its intended purpose. When MedUI is updated,
prompts the practice has edited are kept as the practice left them.

## Workflows {#workflows}

**Pipeline Designer** builds each AI function (a *workflow* or *pipeline*) from steps:
**Data Assembly** (which parts of the record), **Prompt Assembly** (which prompt),
**Inference** (which model, which notice is shown above the output, and any extra request
parameters that replace the model's own for this workflow, such as `{"reasoning_effort": "low"}`;
a key set to `null` removes the model's value) and **De-redaction** (putting the real details back
into the reply). Each model's own parameters are set in Setup → Models.

- Its **classifier** decides where it appears: the AI assistant, a chatbot, the scribe, the
  Library.
- Its **redaction policy** decides what is removed before the AI sees it. Only a workflow that
  removes all identifiers may use a cloud model; MedUI refuses anything else.
- **Activate** makes it available; **Deactivate** puts it back to draft, and anything that
  looks for it by its classifier stops finding it.
- **Archive** puts away a workflow you no longer use: it is hidden from All Pipelines and
  can't be run, even as a test. **View archived** at the top of the list shows it again;
  **Unarchive** brings it back as a draft.

## Your practice's responsibility {#responsibility}

MedUI's intended purpose is documentation and workflow: finding, organising, summarising and
drafting from the record, with a health professional reviewing every draft. It covers the
prompts and workflows MedUI ships with.

**If the practice writes or changes a prompt so that it diagnoses, recommends treatment or
investigations, triages patients, or advises patients, that use is outside MedUI's intended
purpose, and the practice is responsible for it.** Under the TGA's rules the practice may
then be the manufacturer of a medical device. Keep prompts to organising, summarising and
drafting from what is recorded or was said, and test a changed prompt before activating it.
