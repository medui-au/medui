---
title: Flagged AI requests
area: Administration
roles: [admin]
requires_ai: true
reviewed: 2026-10-25
related: [prompts, ai-drafts, chatbots]
---

**Admin → Flagged AI Requests** lists the AI requests that MedUI's scope checks marked, for the
practice's own oversight. MedUI sends nothing about them anywhere else.

## What is listed {#overview}

Four kinds of mark, recorded with each request; none stops it:

- **The request:** what the user typed asked for something outside MedUI's purpose, such as a
  diagnosis, a dose, a second opinion or a prognosis (Application Setup → AI scope → Request
  check).
- **The reply:** the AI marked its reply as out of scope and answered only the part within
  MedUI's purpose; the user saw it under a warning. This needs the scope instructions on.
- **Questions of legality:** the AI judged that the request asked for help to do something
  unlawful. The user saw only a neutral line, *"This request touched on questions of
  legality"*, and the reply as usual. Questions about the law, legal and medicolegal duties,
  mandatory reporting, ethics and the regulation of medicines aren't marked. It is the AI's
  judgement, not a legal ruling, and what is lawful varies between states.
- **Reported: possible identifier:** the user selected text on the request's **Sent to AI** tab
  that should have been redacted. The page says how many reports are open. An administrator opens
  **Review →** (the run's privacy hits) to add each one to the always-redact or name-variant list,
  so it is removed from future requests, or to dismiss it as not identifying.

Filter by user, workflow, dates and kind of mark. **Show** opens the request as typed (when
there was one) and the reply. A request is marked by matching words and by the AI's own
judgement, so some marks will be harmless.

## The practice's responsibility {#responsibility}

MedUI's intended purpose is documentation and workflow; it excludes diagnosis, treatment
recommendations and advice to patients, and its prompts answer such requests in general terms.
If MedUI is being used, or configured through its prompts and workflows, for diagnosis,
treatment or patient advice, that use is the practice's responsibility. Configuring it that way
may make the practice the manufacturer of a medical device, which must be included in the ARTG
(or meet an exemption) before it is used: seek advice before relying on MedUI for such use. See
also [your practice's responsibility for prompts](help:prompts.responsibility).
