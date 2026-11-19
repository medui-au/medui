---
title: AI drafts and what is sent to the AI
area: AI functions
roles: [doctor]
requires_ai: true
reviewed: 2026-10-25
related: [ai-assistant, scribe, chatbots]
---

The AI functions (AI assistant, scribe, chatbots) write **drafts** for you to review, edit
and approve. Before anything goes to a cloud AI service, MedUI removes identifiers and can show
you exactly what will be sent.

## Every AI output is a draft {#drafts}

A short notice above AI output reminds you it is a draft. The notice stays on screen only: it
isn't copied, printed or filed with the text.

If a request touched on questions of legality, a short line above the reply says so. It doesn't
stop or change anything; questions about the law, your duties or ethics are not marked.

- **Check it against the record** before you use it: AI can leave things out, add things that
  aren't there, or mix details up.
- **Edit it** as you would your own notes; what you file, print or send is yours.
- MedUI's AI functions organise, summarise and draft from what is recorded or was said. They
  don't diagnose or recommend treatment, and their output isn't advice. Clinical decisions stay
  with you.

## Local and cloud models {#local-cloud}

- A **local** model runs on the practice's own equipment: nothing leaves the practice.
- A **cloud** model runs at an AI service on the internet. Before a request goes, MedUI
  replaces the patient's identifiers and practitioners' names with placeholders such as
  `[Redacted Phone: …]`, and puts the real details back into the reply on your screen. The
  service sees the placeholders only.

Which model a workflow uses is set by the practice; where a page lets you choose, the list
says *(local)* or *(cloud)*.

## The Sending tab {#sending}

Before a request goes to a cloud model, a privacy check reads it as it will be sent. The
request stops on a **Sending** tab when:

- the check finds the patient's or a practitioner's identifier that redaction missed (it
  always stops then), or
- you have turned on **Review every request before sending to cloud AI** in My settings.

The tab shows exactly what will be sent; nothing has gone yet.

- Identifiers the check found are marked in red. **Remove** replaces one with `[Redacted]`,
  everywhere the same text appears in the request.
- **Edit text** lets you change the request yourself.
- **Send to AI** sends it once nothing marked in red is left; **Cancel** sends nothing.

## The Sent tab {#sent}

After a request has gone, **Sent to AI** shows what was sent, exactly as the AI received it,
with the **Instructions given to the AI** (the workflow's standing instructions) folded
underneath. For a local model it shows the same, and says the model runs inside the practice, so
nothing was sent outside it.

For a cloud model, a line above the prompt says what MedUI's privacy check found in it: an
identifier it recognises is marked in red, and something that only looks like one (a phone-number
shape, a titled name) in yellow, for you to look at. The check knows the patient's details, the
practice's people and the address book; it cannot know every name. A nickname, a relative or a
local business can get through with nothing marked.

If you see something identifying, **select it in the prompt** and choose **Report something that
got through** (a short note on what it is helps). The report goes to the practice's
administrators, who can add it to the redactions so it is removed from future requests. It does
not recall the request: what was sent has gone.
