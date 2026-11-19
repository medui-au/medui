---
title: Care plans
area: Patients
roles: [doctor, admin]
reviewed: 2026-11-13
related: [patient-record, ai-drafts]
---

The care plan builder helps you write and file a GP chronic condition management plan. You
choose every issue, recipe, variant and target; MedUI fills in facts from Best Practice and keeps
the record. It doesn't suggest issues, choose a variant or target for the patient, or say whether
a target has been met.

## A patient's care plan {#patient}

Open **Care Plan** from **Patient Data** in the top menu (with a patient open). The page shows the current filed plan and
every earlier one. **New plan** starts a draft; when the patient already has a plan, the draft
starts as a copy of it, so you update rather than retype. Only one draft per patient is open at
a time; **Continue draft** returns to it.

## Writing the plan {#compose}

- **Medical history:** filled from Best Practice's coded history, medications and allergies when
  the plan is started. Edit it as you need. A heading at the start of a line, such as
  `History:` or `Social history:`, prints in bold.
- **Rows:** each row is an **Issue**, **Goals**, **Management** and **Providers**. Choose the issue
  from the patient's coded history, the practice's standing issues (such as preventive health),
  issues that have a recipe, or type your own.
- **Recipes:** if an issue has recipes, choose one (or a variant) to fill the row, then edit it.
  Where variants are grouped by age, sex or similar, the patient's recorded age and sex are shown
  beside them; you make the choice.
- **Results in the text:** under Management, **+ insert a result…** adds a token such as
  `{urate.last}`. The line under the issue shows each result's value, the target your recipe set,
  and the value in the previous plan, side by side without a judgement.
- **Fetch values…** reads the latest result for every token from Best Practice and lists them for
  you to confirm, with the previous plan's value and any warning (no result, older than the set
  age, a different unit). Untick a value you don't want, or type one Best Practice doesn't have.
  Values are as the laboratory reported them; nothing is converted.
- **Save as recipe** keeps a row you wrote for reuse: it goes to your recipes as a draft, with
  tokens rather than this patient's values. Check the text has nothing about the patient in it.
- **Dictation:** the 🎤 at the top of the draft dictates into whichever box you last clicked in,
  at the cursor. Click once to start and again to stop; check the wording it typed.
- **Print preview** opens the draft as it would print, so you can see how it fits the page and
  adjust the wording before filing. It prints exactly like a filed plan (without the filing date),
  so you can hand it over, but it isn't filed: file the plan without changing it afterwards, so
  the record holds what the patient has. Each preview is noted in the plan's record.
- **Copy**, **Email** and **BP →** (on the draft and on the filed plan): **Copy** puts the plan on
  the clipboard, formatted for Word or an email and as plain text elsewhere. **Email** and **BP →**
  open Comms for this patient with the plan filled in, one section per issue; you send or file it
  there, and Comms keeps the record. The copy filed in Best Practice is the lasting one, so send
  the version you're happy with, then file the plan here unchanged.
- The draft saves itself every few seconds; if it was saved from another window you're asked to
  reload. **Check** lists anything a row is missing and results with no value.
- **File plan…** freezes the plan as it is, with the values shown, and keeps an exact copy. A filed
  plan can't be edited: start a new plan to update it, or **Void** it with a reason. **Print**
  opens the filed copy.

You remain responsible for the plan's content and for agreeing it with the patient.

## Recipes {#recipes}

**Doctor Data → Care Plan Recipes** lists your recipes and the
practice's approved ones.

- A recipe is an issue, optionally a **variant** (such as "with CKD") with **modifiers** that group
  variants, and its goals, management and provider roles. **Standing** recipes are offered for
  every patient.
- **Targets:** one per result in a recipe. Each names its guideline, edition, section and the
  quoted passage, so the source is on record. A different situation needs a different variant.
- **Approve…** fixes a version: you confirm you checked each quoted passage against its source.
  Editing an approved recipe makes a new draft version; plans keep the version they used.
- **Copy to my recipes** makes your own editable copy of a practice or colleague's recipe.
  Administrators can save practice recipes, which every doctor is offered once approved.
- **AI assistance** (if your practice has set up a recipe assistant): describe the recipe or paste
  guideline wording and choose **Draft with AI**. No patient information is involved. The reply
  fills the form for you to check; models can misquote or invent sources, so open each source
  before approving. Versions written with AI help are marked.
- **Record tokens** are filled from the patient's record as recorded: `bp` (the latest reading,
  systolic and diastolic together), `weight`, `height`, `bmi` (from the latest weight and height),
  `weight_excess` (kg above the weight for BMI 25, or below BMI 20; it and `bmi` are left out
  for an adult whose latest height was measured before 18), `age`, `sex`, `alcohol` and
  `smoking` (from social history). Administrators can relabel them, set an age after which a
  reading is shown as older, or turn one off.
- **Result tokens** (administrators) name a result and the LOINC codes that match it in Best
  Practice, with the expected unit and an age after which a value is shown as older. A code used
  in two tokens is flagged, since one result would fill both. **Pick…** lists
  every code in the practice's results from the last 5 years, with the names and units laboratories
  used; type to filter, and **Add** a code. If Expected unit is empty, it takes that code's main unit;
  change it if needed. Codes reported under a name and unit shared with one
  already in the token are marked *same name and unit*: they may be the same test, and you decide.
  A result with no unit recorded isn't treated as a different unit.
