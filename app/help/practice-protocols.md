---
title: Practice protocols
area: Administration
roles: [admin]
reviewed: 2026-11-22
related: [care-plans, patient-record, patient-targets]
---

**Admin → Practice Protocols** holds the practice's own protocol for GP Chronic Condition
Management Plans: the target options for each measure, the guidelines behind them, the wording
for each condition, and the prevention lines. It is the practice's content, not MedUI's. A GP
sees these options for each patient and makes every choice; MedUI only preselects an option where
the protocol's rule matches a condition coded in the patient's record, and the GP confirms or
changes it.

## What the screen shows {#overview}

Anyone who sees the Admin menu can read every version. Only an administrator can change a
draft, approve it, or edit the guideline library.

- **Measures and targets**: one card per measure (blood pressure, LDL cholesterol, HbA1c and so
  on), each with its options. An option has its label, the patient group it suits, the wording a
  plan uses, why the practice chose it, the guidelines it cites (section and a short quote), and
  its **preselect rule**. Measures marked *Individual patients only* (such as uACR, urate and
  waist) aren't part of the GPCCMP protocol: a GP sets them for one patient.
- **Condition modules**: the practice's wording for each condition (goals, measures, monitoring,
  standard services, patient information, safety-netting and "For the GP" reference text). No
  targets here, and no named medicines or doses in patient text.
- **Prevention lines**: screening and prevention wording that MedUI works out from recorded age,
  sex, coded history and smoking. The AI never decides which lines apply.
- **Guidelines**: the library, shared with care-plan recipes.
- **Versions**: the version in use, the draft, and earlier versions.

Each measure also shows the care-plan **result token** its latest value comes from (Admin → Care
Plan Recipes → Result tokens). An administrator can relink it with **Edit measure**. Only tokens
that measure the same thing are offered:
- blood pressure, alcohol and weight take their own record value;
- LDL cholesterol, HbA1c, urate and urine ACR take only tokens whose LOINC codes are all known for
  that test, in the same unit;
- a measure with no known codes takes no token.

A link that no longer matches is flagged, and its latest value isn't shown to GPs. Measures aren't
versioned, and changing one never changes a patient's target.

## Preselect rules {#rules}

A rule says when an option is preselected for a patient, using the Disease Profile's coded
conditions (for example `isDiabetes`, `isIHD`, `isCVA`, `isVasculopathy`, `isRevascularisation`,
`isCKDRecorded`, `isFH`, `isHT`). It is written as a short JSON object:

- `{"any": ["isIHD", "isCVA"]}`: at least one is coded;
- `{"all": [...]}`: all are coded; `{"none": [...]}`: none is coded (parts combine);
- `{"always": true}`: the fallback for everyone else.

Options are tried in order of priority (lowest number first); the first whose rule matches is
preselected. An option with no rule is never preselected: the GP chooses it. Which Best Practice
codes count as each condition is **Admin → Mapping Tables → condition_codes**.

The rule only chooses what is shown first. The GP confirms or changes every target, and MedUI
records which they did.

## Drafts and approval {#versions}

The version in use is never edited. To change the protocol, start a **draft** (a copy of the
version in use), change it, then **approve** it with the next review date (normally 12 months).
Approving retires the previous version; retired versions stay readable, so every target set
under them can be traced to the exact option and wording. Discarding a draft loses its changes.

Review the protocol at least yearly, and whenever a guideline it cites changes: mark the old
guideline superseded on the Guidelines tab, then update the options that cite it in a new draft.

## Decision record {#record}

**Versions → Decision record (print)** shows a version as a printable record: each measure's
options, who each suits, when it is preselected (in words), why the practice chose it and the
guidelines it cites; the condition modules; the prevention lines and who they apply to; and the
guidelines cited. MedUI builds it from the protocol itself, so it always matches what MedUI uses.
Keep a printed or saved copy with each approved version for the practice's records.

## Targets to review {#review}

**Versions → Targets to review** lists patients' current targets that need a look:

- set under an option the protocol in use no longer has, or now words differently;
- set under an option citing a guideline since marked superseded.

Nothing changes by itself: each patient's GP reviews the target at the next plan or review (open
the patient's targets from the list). Individual targets are the GP's own and aren't listed. Use it
at the 12-monthly protocol review and after marking a guideline superseded.
