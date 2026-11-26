---
title: The chatbots
area: AI functions
roles: [doctor]
requires_ai: true
reviewed: 2026-11-26
related: [ai-drafts, ai-assistant]
---

There are two chatbots: one about **a patient's record**, opened from the patient, and a
**general** one for reference questions with no patient.

## The patient chatbot {#patient}

Ask questions about what is **recorded** for this patient (results, letters, history): it is
set up to answer only from the record. It doesn't give clinical advice, and a reply is a draft
to check against the record.

- Each reply has **Raw**, **Rendered** and **Edit** views; edit before you use it.
- **Copy**, **Download**, **Print**, **BP →** (file in the patient's record), **SMS** and
  **Email** (open Comms for this patient).
- **💾 Save** keeps a question you ask often; **📋 Insert** puts a saved one back.
- **New Conversation** starts afresh; earlier conversations can be opened again from the list.
  Conversations aren't kept for ever: the practice sets how long (Application Setup →
  Maintenance), counted from the last message, and then they are deleted. Keep anything you
  need by putting it in Best Practice (**BP →**, or copy it into the record).

## The general chatbot {#general}

For general reference questions, such as about a medicine, a guideline or a form. It has no
patient's record. **Don't enter a patient's details or presentation to get a diagnosis:**
that isn't what it is for, and it can't be checked against a record.

- If a question includes a particular patient's details, the reply says so on its first line
  and gives **general information** about the condition, medicine or guideline instead,
  without working from that patient's findings. Apply it with your own judgement.
- Replies that draw on guidelines or evidence end with **Sources** (title, organisation and
  year, Australian where possible). They are suggested by the AI: check a source before
  relying on it, as a title or link can be wrong.

Before your question goes to a cloud AI, MedUI removes identifiers from it. Where the
practice has a local model, that model finds and removes private details first (the **AI
erasure step**); otherwise rule-based redaction applies, which recognises details by their
pattern and from the practice's own lists. **No redaction method is perfect**, so keep
patients' details out of general questions (see [local and cloud models](help:ai-drafts.local-cloud)).

## Without the AI erasure step {#no-erasure}

Where the practice has a local model, an **AI erasure step** removes names and other details
from your question first. Without it, a banner says so, and the first message in each chat asks
you to confirm: questions then get rule-based redaction only, which can miss names typed in
free text. Replies are marked *Rule-based redaction only*. Keep questions general.

## Sending a reply to a patient {#to-comms}

**BP →** and **Email** under a general chatbot reply open **Comms**, where you choose the
patient, review and edit the text, then file it in their record or email it. Nothing is
filed or sent until you do it there.
