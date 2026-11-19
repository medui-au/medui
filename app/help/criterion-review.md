---
title: Criterion review
area: Administration
roles: [doctor, admin]
reviewed: 2026-10-24
related: [patient-record]
---

**Doctor Data → Criterion Review** lists patients whose results meet a diagnostic criterion where
the diagnosis isn't recorded in Best Practice, for a doctor to review. A doctor sees the patients
whose last visit was with them; a practice manager sees everyone, or chooses a doctor.

## What it lists {#overview}

Active patients seen in the last 24 months, checked with the same rules and codes as the
Disease Profile badges (see [the Disease Profile](help:patient-record.disease-profile)):

- **HbA1c ≥ 6.5% on 2 occasions, diabetes not recorded** (adults): two results at or above
  6.5% (48 mmol/mol) on different days. Recorded conditions that affect how HbA1c reads are
  shown beneath, with the latest relevant results (Admin → Mapping Tables → influences).
- **eGFR < 60 for 3+ months, CKD not recorded**: at least two results below 60, first and last
  90 days or more apart, none of 60 or more between. *Previously* means the latest eGFR is now 60
  or more.

Each row gives the results that met the criterion, the latest result, and the last visit with
its doctor. The patient's name opens their record in a new tab. The list is worked out when the
page opens; it isn't stored.

What you stay responsible for: a criterion met is not a diagnosis. Whether the patient has the
condition, any further test, and recording it in Best Practice are the doctor's decisions.
Once it's recorded (with a code counted in condition_codes), the patient leaves the list. A
practice manager can switch the page off in Application Setup → General → Patient Record.
