---
title: Criterion review
area: Administration
roles: [doctor, admin]
reviewed: 2026-11-21
related: [patient-record]
---

**Doctor Data → Criterion Review** is a record-coding audit: it lists patients whose results meet
a published criterion where the condition isn't coded in Best Practice, for a doctor to review.
A doctor sees the patients whose last visit was with them; a practice manager sees everyone, or
chooses a doctor.

## What it lists {#overview}

Active patients seen in the last 24 months, checked against the published criteria below, with
the same condition codes as the Disease Profile. The Disease Profile's results badges are rules
each user chooses and differ from these (see [the Disease Profile](help:patient-record.disease-profile)):

- **HbA1c ≥ 6.5% on 2 occasions, diabetes not coded** (adults): two results at or above
  6.5% (48 mmol/mol) on different days. Recorded conditions that affect how HbA1c reads are
  shown beneath, with the latest relevant results (Admin → Mapping Tables → influences).
- **eGFR < 60 for 3+ months, CKD not coded**: at least two results below 60, first and last
  90 days or more apart, none of 60 or more between. *Previously* means the latest eGFR is now 60
  or more.

Each row gives the results that met the criterion with their dates, the latest result, and the
last visit with its doctor; each section states its rule and source (RACGP and ADS for HbA1c,
KDIGO for eGFR). Rows are in order of patient name: nothing is ranked. The patient's name opens
their record in a new tab. The list is worked out when the page opens; it isn't stored.

What you stay responsible for: a criterion met is not a diagnosis. Whether the patient has the
condition, any further test, and recording it in Best Practice are the doctor's decisions.
Once it's recorded (with a code counted in condition_codes), the patient leaves the list. A
practice manager can switch the page on or off in Application Setup → General → Patient Record.
