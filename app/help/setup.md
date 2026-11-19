---
title: Application Setup
area: Administration
roles: [admin]
reviewed: 2026-11-15
related: [prompts, my-settings, ai-drafts]
---

**Application Setup** (Admin → Application Setup) is where practice managers set MedUI up for
the practice. A coloured dot beside each tab shows whether it is complete. Connection details
and secrets (Best Practice, the encryption key) are set when MedUI is installed, in its
settings file, not here.

## General {#general}

- **Practice name** (shown in the top bar and on generated documents) and **phone**.
- **Practice timezone:** MedUI's local time, so "today" on the day sheet is the practice's
  today. *The installation's* uses the zone set at installation; choose another only if that
  is wrong. A place, so daylight saving changes by itself.
- **Encryption key:** whether the key that protects stored transcripts, messages and keys is
  set. Keep a copy of it with the backups: data encrypted under it can't be read without it.

## Patient record {#patient-record}

- **Disease Profile: show "eGFR < 60 for 3+ months"** (on unless switched off). Where CKD
  isn't recorded, the patient's Disease Profile shows this when their eGFR results meet the
  eGFR criterion for chronic kidney disease. It describes the results; the doctor decides
  whether to record CKD. Off: recorded CKD only. See the patient record help for the rule.
- **Disease Profile: show "HbA1c ≥ 6.5% on 2 occasions"** (on unless switched off): the same for
  diabetes, for adults whose HbA1c results meet the diagnostic criterion where diabetes isn't
  recorded.
- **Doctor Data: Criterion Review** (on unless switched off): the review list of patients whose
  results meet one of these criteria without the diagnosis recorded. Off removes the page and its
  menu item. See [Criterion review](help:criterion-review.overview).

## Database {#database}

Whether MedUI can reach Best Practice's database, with the error if it can't. The connection
(server, database, a **read-only** login) is set in the installation's settings file; MedUI
never writes to Best Practice. Until the connection is set, an administrator's login opens this
tab.

Use the read-only account BP supplies for database access. Each time the tab opens, MedUI asks
the database server what its login may do, without trying a change: whether it is a server
administrator, has a write role or a write permission on any table, or can create or alter
tables, in every database it can open. **Read-only** means none of these. If the login could
write, the tab lists what it could do, administrators see a notice on every page, and MedUI
won't run SQL written in Query Manager or Best Practice data sources until the login is
changed. MedUI's own screens keep working. Stored procedures the login may run are listed for
information.

## AI providers {#providers}

- **AI Providers:** the AI services MedUI may use, local (on the practice's equipment) or cloud,
  with their address and key. **Fetch Models** lists what a provider offers.
- **Default models:** used where a workflow doesn't name its own; the **default local model**
  is used where only a local model is allowed. **Default chatbot models** are separate.

## Models {#models}

Turn models on or off, give each a tier (Fast, Balanced, Quality), and mark speech-to-text
models as **ASR** so the scribe can use them.

**Extra request parameters** (under each model's name) are sent with every request to that model,
written as a JSON object. The usual use is a local reasoning model's thinking: with Ollama, MedUI
sends `{"reasoning_effort": "none"}` to turn it off, or `"low"`, `"medium"`, `"high"`. Ollama's
`"think"` setting has no effect here, because MedUI uses Ollama's OpenAI-compatible address. A
workflow's Inference step can override these for that workflow only. MedUI refuses anything it
sets itself (the model, the messages, temperature, maximum length); these settings never change
what is removed before the AI sees the text. Not used for Anthropic's own API.

On a speech-to-text (ASR) model the extra parameters go with every transcription request: as
query parameters for Deepgram (for example `{"numerals": true}`), as form fields for a Whisper
server. MedUI sets the model, the language and speaker turns itself.

**Speaker turns** (Deepgram ASR models only): Off, `latest`, `v2` or `v1`. When on, Deepgram
separates the speakers in each Scribe and Quick Scribe chunk, and the transcript shows
**[Speaker 1]** / **[Speaker 2]** turns. MedUI's own labelling step, which needs a local model,
is then skipped, so a practice with no local AI still gets turns. Deepgram numbers the speakers
afresh in every chunk, and doesn't say which one is the doctor; the note-writing workflow works
that out from what was said. Dictation never asks for it. `latest` follows Deepgram's newest
version; `v2` keeps it fixed.

A Deepgram provider's **Base URL** chooses where the audio is sent: `https://api.au.deepgram.com`
keeps it in Deepgram's Australian region; `https://api.deepgram.com`, or blank, is its global
service.

## Tasks {#tasks}

- **Voice transcription (ASR):** the speech-to-text model the scribe uses.
- **AI Assistant models** and **Chatbot models:** which models doctors may choose from on those
  pages. Each list says which models are local and which are cloud.

## External sources {#external}

Outside services MedUI calls, each with its address and a health check: mainly the **OCR**
service that reads scanned documents. A practice that runs its own compatible document server
can register it here too; most practices won't have one. (This isn't the summaries MedUI's AI
functions write.)

## Data sources {#datasources}

Data feeds for the **Charts** pages: a Best Practice query (from Query Manager), a web address
or a file.

## Users {#users}

Everyone who has logged in, with their level and type: **BPSDB Shadow** (a Best Practice user's
MedUI account, refreshed at each login) or **Local Admin**. **Edit** sets a title (Dr) and the
**BPS Patient ID** of a staff member's own patient record, which staff privacy (Maintenance)
uses, and a Best Practice user's **name in MedUI**: the name MedUI shows instead of their Best
Practice name (blank = the BP name; they can also set it in My settings). MedUI's redaction catches both.
A practice user's first name on its own ("Thanks, Sam") is also removed from text sent to a cloud
model, for every doctor and staff member in Best Practice, current or former. Two kinds are left in:
a first name that is also an ordinary word (Rose, Grace), and the first word of an account named for a
service rather than a person ("Telehealth Bookings"). To have an ordinary-word name removed, add it to
the **first_names** list (Admin → Mapping Tables) with *include* ticked; untick *include* to stop a
name being removed.
**App Admin** is for local accounts: a Best Practice user's administrator access comes
from their Best Practice group (see [logging in and access](help:logging-in.access)).

**A doctor's details.** Point at a doctor's name (marked ⓘ), or tab to it, to see their details as
Best Practice holds them: qualifications, AHPRA registration, HPI-I, provider numbers by site,
prescriber number, first patient visit, patient visits and patients seen. It's the same card each
doctor sees on their own name ([your details card](help:my-settings.details-card)). A doctor here is a
Best Practice user with a provider or prescriber number. Only administrators see this lookup.

**Preferred names outside MedUI.** Best Practice has no field for a preferred name, so tools that read
only Best Practice (such as a document summariser) don't know it. To cover them, add an **inactive**
user in Best Practice, in the same group as the practitioner (a doctor's group for a doctor), with the
preferred first name and surname. Inactive users can't log in, but every practitioner list MedUI and
those tools build from Best Practice includes them, so the preferred name is redacted and checked there
too. Keep it in step with the name set here.

## AI scope {#ai-scope}

Keeps the AI functions within MedUI's purpose: organising, summarising and drafting.

- **Scope instructions** (the wordings under *System prompt guardrail injections*): a short
  instruction placed before every workflow's system prompt; a
  reply the AI marks as out of scope is shown under a warning and recorded. The wording comes
  from the workflow, else its system prompt, else the **default** here.
- **Request check:** notes requests that ask for a dose, a second opinion, a prognosis and the
  like, on the run record.
- **General chatbot without the PII Erasure workflow:** *allowed with a privacy warning* or
  *not allowed* (see [the chatbots](help:chatbots.no-erasure)).
- **Notices above AI output:** the one-line "AI draft" notices, and their wording.

Every change of wording keeps a version, and each run records the version it used.

## User defaults {#user-defaults}

What each user starts with on **My settings**. Untick **Users may change** to fix a setting for
everyone: users then see it marked *Set by your practice*.

## Messaging {#messaging}

- **Outbound email (SMTP):** the mail server for emails to patients. **Test Connection** checks it.
- **SMS gateway:** SMS is sent by emailing a gateway that turns the message into an SMS.
- **Best Practice PIT export:** the shared folder Best Practice reads incoming reports from,
  used by **BP →** and **File to BP**.

## Maintenance {#maintenance}

- **Data retention:** how many days MedUI keeps scribe transcripts, sent messages and AI run
  records, and whether it removes older ones automatically each day. **Purge** removes them
  now (it can't be undone; keep backups).
- **Staff privacy:** hides staff members' own patient records from colleagues; only that staff
  member can open their own record. It matches staff by their Best Practice user ID.
- **Privacy Review:** shows administrators the **Admin → Privacy Review** page, a list of the AI
  requests in which the pre-send privacy check found something, for review. Switching it off
  hides the page and keeps the reviews already saved; the check itself always runs. See
  [Privacy Review](help:privacy-review.overview).
