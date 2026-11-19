---
title: Privacy Review
area: Administration
roles: [admin]
requires_ai: true
reviewed: 2026-11-17
related: [flagged-requests, ai-drafts, setup]
---

**Admin → Privacy Review** is where an administrator checks how well redaction is working. It
lists the AI requests in which MedUI's pre-send privacy check found something identifying, and the
ones a user reported, so each one can be looked at and recorded. Nothing on these pages is sent
anywhere.

## What this page is for {#overview}

Before a request goes to a cloud AI, MedUI redacts it: names, dates of birth, addresses and other
identifiers are replaced with placeholders. The patient's address is removed even when a document
writes only part of it, as scanned letters often do: the unit and number with one or two of the
street words, a word as its initial, the line in capitals or spaced out with tabs. The suburb on
its own stays, since it is often the practice's suburb too. The patient's phone number is removed
when a letter or form lays it out in columns, with wide gaps between its groups, too, or writes
the area code without its 0, or the 0 without the area digit. So are the date of birth written with day and month the other way
round, and the Medicare number in any grouping or cut short to its first 7 digits. One word of a
surname of several words (the "Thistlewood" of "van der Thistlewood", or one half of a hyphenated
surname) is removed where it stands beside the patient's name, which catches a letter that
misspells the rest of the surname; on its own, away from a name, it stays. A hyphenated name is
removed when written with a space beside the hyphen ("Smith- Jones") too. The practice's own name becomes
`[Redacted UsualPractice: …]`, so the AI can still tell it is your practice, and the answer shows
the name again. Then it **checks the text it is about to send** for
anything redaction missed. The check looks for:

- the patient's own details, in the forms they are written in the record and the common variants
  (a shortened first name, a date written another way);
- the names and details of practice contacts: practitioners in the address book, practice users,
  the practice itself;
- anything shaped like an identifier that could belong to anyone: phone numbers, email
  addresses, street addresses, Medicare, DVA and provider numbers, names with a title.

Each thing it finds is a **hit**. The check records where each hit sits in the text and what type
it is, never the text itself; the text stays in the run's own record.

This page lists the requests with hits, and those a user reported from the **Sent to AI** tab
("this should have been redacted"). Requests where the check found nothing are not listed. For
each request you can:

1. see each hit in the words around it;
2. add it to future redactions, so the same thing is removed from then on;
3. record what it was (a real leak, a false alarm, or acceptable), so the practice has a record of
   how redaction is performing.

Requests answered by a local model (on the practice's own computers) aren't checked, because
nothing leaves the practice.

If a patient's details (name, address, phone numbers and so on) can't be read from Best Practice
when a request is made, a request to a cloud model is stopped ("redaction unavailable") and
nothing is sent. A request to a local model goes ahead, and the patient's own details may not be
removed from what it receives or from the stored request. Try again once Best Practice can be
reached; if it keeps happening for one patient, an entry in their record may need correcting.

## Tiers: how serious a hit is {#tiers}

Every hit has a tier. The lower the number, the more certain it is to identify someone.

- **Tier 0: the patient's own details.** Something from this patient's record, such as their name
  or a short form of it, date of birth, address, phone, email, Medicare number or next of kin. MedUI
  **stops the request** before sending and shows the user what was found; the user removes it or
  cancels.
- **Tier 1: a practice contact.** A practitioner from the address book, a practice user, or the
  practice's own details. Also **stops the request** for the user to review.
- **Tier 2: looks like an identifier.** The *shape* of a phone number, email, address, Medicare
  number or titled name (Dr, Mrs…) that isn't on any list, so it may be anyone's, or nobody's (a
  drug name after "Dr" can look like a name). Tier 2 doesn't stop the request; it is recorded so
  it can be looked at here. Many tier 2 hits are harmless.

## Reading the list {#reading}

The counts at the top show what is waiting: tier 0–1 or reported requests not yet reviewed, tier 2
requests not yet reviewed, and how many requests have been checked in all.

The list opens on **tier 0–1, or reported**, the ones that matter most. Use **Found** to see tier 2,
or everything; **Reviewed** to see only what is still to do; and **Workflow**, **From** and **To** to
narrow it down. **Latest →** opens the newest request in the list as filtered.

The columns:

- **Run:** the request's number in MedUI, also shown on its Debug tab.
- **When**, **User**, **Workflow:** when it was made, by whom, and with which workflow, and whether
  that workflow used a cloud or a local model.
- **Found:** the most serious tier, how many hits, and their types in plain words. *Reported by a
  user* means someone selected text on the Sent to AI tab; *open* means no administrator has dealt
  with the report yet.
- **Outcome:** whether the request went to the AI. *Sent*: it did. *Stopped at review*: MedUI paused
  it for the user, who cancelled or let the pause time out, so nothing was sent. *Cancelled* or
  *Failed*: it ended for another reason before or during sending.
- **Review:** what an administrator recorded, and the severity if one was given.

## A request's page {#run-page}

**Open →** shows one request. From the list, **← Previous** and **Next →** move through the list in
the same order and with the same filters, and **← Back to the list** returns to it.

- **Reported by users:** text a user selected as something that should have been redacted, with
  their note. Add it to a list, or **Dismiss** it if it isn't identifying.
- **Found by the privacy check:** each hit, its tier and type, and the words around it as they were
  sent, with redaction's placeholders where it removed something.
- **Add to future redactions:** a shortened name goes on the *name-variant* list and is then
  redacted for every patient with the name it is short for. Another person's name, an address or a
  contact detail goes on the *always-redact* list and is redacted for everyone. Both lists are in
  **Admin → Mappings**, where an entry can be switched off. Adding changes future requests only,
  never what was already sent. Common short forms and spellings (Mick for Michael, Libby for
  Elizabeth, Sara for Sarah) are already redacted for every patient with the name, from a list
  that comes with MedUI; add the ones it doesn't have. Short forms that are also everyday words
  (Will, Bill, Rose) are never on that list, so a practice adds them only if it wants them.

Hit types that have no list (for example the patient's own date of birth) are already redacted by
rule; one getting through is worth noting in the review so it can be followed up.

## Recording a review {#reviewing}

At the bottom of a request's page, **Your review** records what the hits were:

- **Real leak:** it identifies a person and got through to the AI, or would have if the user had
  not stopped it.
- **False alarm:** not identifying: an ordinary word, a drug or place name, an invented example.
- **Acceptable:** identifying, but appropriate for this request, such as the name of a hospital
  or a public body.
- **Not reviewed:** clears a saved review.

**Severity** (none, minor, serious) is optional and mostly useful for real leaks. The **comment**
is optional and stored encrypted; describe the pattern ("a nickname in a referral letter"), not
the patient. **Save review** stays on the same request; then use **Next →**.

A review is the practice's own record. It doesn't change anything that was sent, and it doesn't
add anything to the redaction lists: use **Add** for that. A review is removed with the request's
record when old records are purged (Application Setup → Maintenance → Data retention).

## Switching the page on or off {#switch}

**Application Setup → Maintenance → Privacy Review** shows or hides this page for administrators.
When it is off, the menu item, the list and the review form are hidden; reviews already saved are
kept and come back when it is switched on. The privacy check itself always runs, and tier 0 and 1
hits still stop a request, whichever way this is set. Each request's Privacy hits page (linked
from the privacy card on the Debug tab and from Flagged AI Requests) stays available either way.
