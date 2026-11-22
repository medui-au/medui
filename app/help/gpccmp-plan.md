---
title: GPCCMP plan decisions
area: Patients
roles: [doctor]
reviewed: 2026-11-22
related: [patient-targets, care-plans, practice-protocols]
---

**Patient Data → GPCCMP: Targets & Plan → Continue to plan decisions** is where you record what
you decided for a GP Chronic Condition Management Plan, before any AI step. Everything on the page
is your decision. MedUI keeps it as a structured record; the AI (a later step) only organises and
words the plan from it and from the record, and may not change or add to it.

## The steps, and what each button saves {#flow}

```text
 1. TARGETS  (Patient Data → GPCCMP: Targets & Plan)
    ├─ choose or change targets
    ├─ [Save targets] ─────────────────────── saves, stays on this page
    └─ [Save and continue to plan decisions →] saves, then step 2
                     │
                     ▼
 2. PLAN DECISIONS
    ├─ tick issues, write directions, services, modifiers, review, consent
    ├─ [Save decisions] ──────── saves, stays (come back to it later)
    └─ [Proceed with GPCCMP →] ── saves, checks, confirms, drafts with AI: step 3
                     │
                     ▼
 3. AI DRAFT  (MedUI's checks, then the care plan)
    ├─ [Open the draft care plan] → edit · File plan… · Print · Copy · Email · BP →
    └─ [Draft again] ─ voids this draft, drafts again from the confirmed decisions
```

**Every button saves first**, so nothing typed on a page is lost by moving on with a button. If you
try to leave a page another way (a menu, a link, closing the tab) with changes not yet saved, the
browser asks whether to leave. On the Targets page, a measure showing a preselected option is saved
with it when you press either Save button; choose **No target for now** to leave one unset.

## Recording the decisions {#overview}

- **Plan type**: prepare a new plan (965) or review the current one (967). The billing record's
  eligibility is shown as a fact; the choice is yours.
- **Targets**: the patient's current targets, set on the Targets page.
- **Issues**: the practice protocol's condition modules, ticked where a condition is **coded** in
  the record. Untick any you aren't planning for, tick others, and add issues of your own. For each
  issue you can write the goal in the patient's words, your directions (what was agreed, including
  medicine decisions), and the services or referrals with their purpose. The protocol's standard
  services are offered as ticks.
- **Modifiers**: aged 80+ or frail, palliative, cognitive impairment (name the carer or substitute
  decision-maker), conditions limiting adherence, and anything the patient declined.
- **Review and consent**: the review interval (3 months unless you choose otherwise) and the
  consent ticks. Tick consent only once it is given; anything unticked appears in the plan as "not
  recorded", for you to complete with the patient.

## The next plan or review {#carry-forward}

When you start a new plan for a patient who already has one, MedUI starts it from the **last
confirmed plan** (by any doctor) and says which one. Carried over, all for you to check and edit:
the issues, goals, your directions, services and purposes, modifiers, review interval and notes.
**Consent is never carried**: it is recorded afresh for every plan and review. The plan type starts
from the billing record. Conditions coded since the last plan are added and marked *new since the
last plan*; an issue whose protocol module no longer exists becomes one of your own issues.

**Save decisions** keeps them to finish later. **Proceed with GPCCMP** saves them, checks they are
complete (at least one issue; a named carer with cognitive impairment; a progress word for each
issue on a review), confirms them and drafts the plan with AI from exactly what is on the page.
**Discard decisions** starts again.

The **preview** shows your decisions exactly as MedUI will give them to the AI. It carries no
names or identifiers.

## Reviews (967) {#review}

When you choose **Review the current plan**, the page adds what MBS asks a review to record,
"progress against goals":

- **Progress since the last plan**: each of the patient's targets beside the last recorded value,
  in one fixed sentence ("Your target LDL cholesterol is … ; your last recorded value was 1.9
  mmol/L on 03/10/2026"). MedUI never says whether a target is met.
- For each issue, the **previous goal** (from the last filed plan) and a **progress** word you
  choose: improved, stable, worse, achieved or not assessed, with an optional note. A review needs a
  progress word for every issue before you can proceed.

The draft opens with a **Progress since the last plan (recorded by the GP)** row, which MedUI writes
from your words and the target sentences; the AI doesn't write or judge progress. Progress is never
carried into the next plan.

## The AI draft {#draft}

**Proceed with GPCCMP** saves and confirms the decisions, then asks the practice's GPCCMP drafting
model to word the plan. The list beside the button lets you choose another model for this draft
(the same models the AI Assistant offers); otherwise the pipeline's own model is used. Every model
gets only the redacted record, and the draft page says which model drafted it. **Draft again** can
use a different model, to compare. MedUI writes these parts itself, from the record and your decisions:

- the medical-history header;
- the targets;
- the prevention lines (worked out from age, sex, coded history and smoking);
- the review date;
- the consent lines (from your ticks);
- the "For the GP" protocol reference.

The AI writes only the wording for each issue (goal, measure, your and the team's actions,
services, review aim) and the safety-netting. Every line it writes ends with where it came from:
*[Discussed]* (your decisions), *[Record]* or *[Protocol]* (proposed, for the patient to agree).
It is told to do no arithmetic and to judge no result: values are quoted with their date and the
laboratory's own flag.

Before you see the draft, MedUI **checks** the AI's text against your decisions:

- exactly your issues and services;
- no target numbers, consent or doses it wasn't given;
- no judgement of results;
- a source on every line;
- the MBS parts complete.

Anything to look at is listed. The draft then opens as an ordinary **care plan draft**: edit it,
file it, print it or send it to Best Practice from there. The source tags and the draft line are
there for your review in the editor only; the printed, sent and filed plan leaves them out. MedUI
keeps your decisions, targets and the AI's tagged reply on record. **Draft again** voids the draft and
asks again.

A patient can have only one open care plan draft. If one is already open, file or void it first.
