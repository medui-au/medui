---
title: The AI assistant
area: AI functions
roles: [doctor]
requires_ai: true
reviewed: 2026-10-23
related: [ai-drafts, scribe]
---

The **AI assistant**, opened from a patient, runs the practice's AI workflows on that patient's
record (for example a summary of the record) or answers a question you type about it. It
gives you a draft to review.

## Choosing what to run {#choosing}

- **Function / Pipeline:** the workflows the practice has switched on; ★ marks the default.
  Choosing one shows what it does.
- **Model:** the workflow's own model, unless you choose **Override model** and pick another.
  Each says *(local)* or *(cloud)*; see [local and cloud models](help:ai-drafts.local-cloud).
- **Prompt / Query:** type a question about the patient, or add to the workflow's request.
  🎤 dictates into the box.
- **Instructions given to the AI:** the standing instructions this workflow gives the AI,
  read-only, folded until you open them.

Press **▶ Run**. **Progress** shows each step; a cloud request may stop on the **Sending** tab
first (see [the Sending tab](help:ai-drafts.sending)).

## The draft {#output}

The **Output** tab holds the draft, under the reminder that it is a draft (see [AI drafts](help:ai-drafts.drafts)).
Give it a **Title / Label** and **Date**, edit it, then:

- **Print View**, **Print**, **Copy**;
- **Tidy Up**: an AI pass that tidies the text's layout and wording (check it again after);
- **BP →**: file it in the patient's Best Practice record;
- **SMS**, **Email**: open Comms for this patient with the text filled in, to review and send.

**Sent to AI** shows what went to a cloud AI (see [the Sent tab](help:ai-drafts.sent)).
