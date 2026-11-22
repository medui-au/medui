---
title: Patient record
area: Patients
roles: [doctor, nurse]
reviewed: 2026-11-22
related: [results-outside-range, setup]
---

The patient record screen brings together what Best Practice holds about a patient. MedUI
reads it from Best Practice and doesn't change it.

## Disease Profile {#disease-profile}

The **Disease Profile** panel, at the bottom of the left-hand column, shows badges for
conditions **recorded** in the patient's past history, from Best Practice's coded items
(active items only, including a coded *Reason for visit* that Best Practice copied to past history): diabetes (type 1, type 2 or unspecified; not borderline or gestational), IHD, hypertension, atrial fibrillation, stroke, CKD,
vasculopathy, COVID-19, a pacemaker, familial hypercholesterolaemia and revascularisation (CABG,
coronary angioplasty or stent, carotid endarterectomy, iliac stent). A BMI over 30 is shown with the weight and its date.

Which Best Practice item codes count as each condition is the practice's list: **Admin →
Mapping Tables → condition_codes**, one row per condition and code (diabetes, ckd, ihd and so
on, conditions that affect how results read, such as iron_deficiency, and the
[population chart](#population-chart)'s filters). Delete a row to stop a code counting,
add one to make it count; changes show within five minutes. It starts with the codes MedUI has
always used. Two columns name each code, for reading only; MedUI fills them in where they are
blank and never uses them to decide anything:

- **bp_item**: Best Practice's own dictionary name(s) for the code, synonyms separated by " / ".
  It needs read access to BP's BPSDrugs database; without it the column stays blank.
- **practice_item**: the wording most often recorded for the code in this practice's past
  history. Wording used by fewer than 3 entries is never used, so one patient's own text can't
  become a name. Codes nobody at the practice has used stay blank.

Recorded CKD shows the stage only if one was recorded, the year it was recorded, and the
latest eGFR: *CKD stage 3B (recorded 2021) · eGFR 24, Mar 2026*. A recorded stage can fall
out of date as the eGFR changes; the two side by side let you see whether the record needs
updating. A recorded stage 1 or 2 (kidney damage with a normal eGFR) correctly sits beside an
eGFR over 60.

**Results badges you choose to show.** Two badges describe results, not a recorded
diagnosis. They are **your own choice**, in **My settings → Patient record**: off until you tick
them, shown only to you, on the patients you view. Each tick box is worded as the rule itself,
and the badge appears only when the patient meets it:

- **HbA1c**, for adults where diabetes isn't coded: *the highest of the last 3 HbA1c results is
  6.5% (48 mmol/mol) or more*. The badge shows those 3 results with their dates, in %,
  for example *HbA1c 6.1% (Jan 2026) · 6.8% (Jun 2026) · 6.4% (Oct 2026)*. A result the
  laboratory reported in mmol/mol is converted to % for the badge with the IFCC–NGSP master
  equation (% = 0.09148 × mmol/mol + 2.152, to one decimal), and the tooltip gives the
  laboratory's own mmol/mol value beside it. A sample reported in both units counts once; a result
  that can't be read is skipped, so the 3 are the last 3 readable ones. Each result is compared
  with the threshold in its own unit. 6.5% (48 mmol/mol) is the diagnostic threshold in the RACGP handbook and the
  Australian Diabetes Society's 2015 statement, which ask for confirmation on a different day.
- **eGFR**, where CKD isn't coded: *the last eGFR is below 59*. The badge shows that result and
  its date, for example *eGFR 54 (Oct 2026)*. Laboratories report whole numbers, so a result of
  exactly 59 doesn't show the badge, although KDIGO's category G3a (below 60) includes 59. Values
  are read as the laboratory wrote them: *>90* is not below 59, and a value that can't be placed
  either side of 59 shows no badge.

Where the record has a condition that affects how HbA1c reads, the HbA1c badge is still shown,
and its tooltip says which way the condition pushes HbA1c, with the relevant latest results:
- **may raise it** (the result may overstate glucose): iron deficiency (with ferritin and
  haemoglobin), B12 or folate deficiency (B12, folate, haemoglobin), asplenia;
- **may lower it** (glucose may be higher than the result suggests): haemolysis, pregnancy
  recorded near the time of the results;
- **either way**: a haemoglobin variant (depends on the laboratory's method), advanced CKD
  (recorded, or a latest eGFR below 30).

What each condition means here, its wording, its source and the results shown with it are the
practice's list: **Admin → Mapping Tables → influences** (situation *hba1c_interpretation*).
Transfusions and iron infusions are rarely recorded, so the tooltip mentions them.

Recorded diabetes shows its type (if recorded), the year and the latest HbA1c. Both diabetes
tooltips list the Australian HbA1c targets for reference, and both CKD tooltips the KDIGO 2024
categories (eGFR G1–G5, urine albumin/creatinine A1–A3); MedUI doesn't compare them with the
patient's results or pick out a category.

The **Criterion review** page (Doctor Data) uses the published criteria instead: two HbA1c
results of 6.5% or more on different days, and eGFR below 60 for more than 3 months. So a
patient can be on that list without a badge, or the other way round.

What you stay responsible for: a badge is a rule you chose, applied to the results; it doesn't
diagnose diabetes or CKD, MedUI doesn't stage CKD, and the eGFR badge doesn't use urine albumin.
Whether the patient has diabetes or CKD, and recording it, is your decision.

## Charts {#charts}

**Patient Charts** draws each curated test over time: glucose, cholesterol (total, HDL, LDL),
eGFR, urine albumin, HbA1c, TSH, PSA, ferritin, FIB-4, weight and blood pressure.

- The shaded band is the **laboratory's range**, from the most recent result that has one;
  the caption says which result. A laboratory's range can change over time (for PSA, with
  age), so earlier results may have been reported against a different range.
- Points above or below the band are labelled *Above range* and *Below range*. MedUI doesn't
  draw targets of its own: practice targets will come with the practice-policy work.
- Tests the laboratory reports without a range (FIB-4, which MedUI calculates from the
  results; weight; blood pressure) have no band.
- **FIB-4** is calculated by MedUI, not reported by the laboratory: (age × AST) / (platelets ×
  √ALT) (Sterling et al., Hepatology 2006), from AST and ALT on the same day and the platelet
  count nearest to that day (within 30 days), with the age on that day. The chart's caption says
  so; hover over a point to see the age, AST, ALT and platelets it came from. MedUI shows no
  cut-off or flag for it, and AI workflows receive it labelled as calculated, with the same
  inputs and formula. The weight caption gives the BMI and the
  weights that correspond to BMI 20 to 25 for the recorded height.
- **BMI** is worked out from the latest weight and the latest height, even when they were
  measured on different days (Best Practice's own BMI needs both on the same day). A height
  measured before 18 is not used for a patient who is now 18 or older: the weight and height
  are still shown, without a BMI, until a height is recorded again.
- Weight is shown as recorded, to one decimal place (it was rounded to whole kilograms
  before MedUI 0.38.4, BMI included).
- The eGFR caption lists the KDIGO categories for reference.

What you stay responsible for: reading the results against the patient's circumstances,
including any target that applies to them.

## Population chart {#population-chart}

**Charts → Patient Scatter** in the top menu draws one point per patient. Its
**Conditions** filters (diabetic, atrial fibrillation, hypertension, sleep apnoea,
osteoarthritis of weight-bearing joints, depression or anxiety) use the same condition list and
the same rule as the Disease Profile: active past history items, coded. So a patient with the
badge is also in the chart's filter. Sleep apnoea, osteoarthritis of weight-bearing joints and
depression or anxiety have no badge; their codes are rows *osa*, *wboa* and
*depression_anxiety* in condition_codes. A condition with no rows at all uses MedUI's
built-in codes. Height and weight measured before 18 aren't used.

- **Sliders.** A slider left at its full range filters nothing. Once you move it, only patients
  with a value inside the range count, so narrowing BMI leaves out patients with no BMI.
- **Who is plotted.** A patient is drawn only if they have a value for both axes. The count
  above the chart says how many are plotted of those matching the filters, and how many have
  no value for each axis (*1,240 plotted of 5,300 matching the filters · 3,900 have no BMI*).
- **Show patients with no value** draws them in grey strips: along the bottom for those with no
  value on the vertical axis (at their place on the horizontal one), and down the left side for
  the reverse. Their height within a strip means nothing; it only spreads them out. Patients
  with neither value are counted in the corner and are in the list.
- **Ages** are exact, to one decimal, so patients of the same age in years don't sit on top of
  one another.
- **The list** below the chart shows the patients matching the filters, or only those with no
  value for an axis, with the two axis values and their next appointment. It, and its **CSV**
  and **Markdown** downloads, are available for 500 patients or fewer: narrow the filters (sex,
  age, conditions) for a larger group. Each download is recorded in Application Usage
  (*patient_list.export*). A download holds patients' names: keep it within the practice and
  delete it when you're done.

What you stay responsible for: the chart shows what is recorded, coded and active; a patient
whose condition is recorded only as free text, or as inactive, isn't in the filter.

## Vaccine eligibility (NIP) {#nip}

For patients aged 50 and over (and Aboriginal and Torres Strait Islander people for influenza),
MedUI works out funded eligibility under the National Immunisation Program for influenza,
COVID-19, pneumococcal, shingles (Shingrix) and RSV, from age, Aboriginal and Torres Strait
Islander status (as recorded; *not recorded* counts as no), the at-risk conditions listed in
Admin → Mapping Tables (nip_risk_mapping), and the doses recorded at this practice.

- **COVID-19** follows the NIP criteria (health.gov.au, updated 1 October 2026): free for adults 75+
  (two doses a year, about 6 months apart), 65–74 (one a year), Aboriginal and Torres Strait
  Islander people 50–74 (one a year), and adults 18–64 with severe immunocompromise (one a year;
  a recorded condition from the immunocompromise list, which you confirm). A Medicare card or
  eligibility is needed. Others aren't funded; the Australian Immunisation Handbook has
  recommendations for other groups.
- Beside Immunisations, a small grey line, **"NIP-funded for this age or risk group; no dose
  recorded within the schedule's interval: …"**, names those vaccines, each with the last dose
  recorded here (or *none recorded*). Hover over it for the schedule it follows (the 2026 NIP
  schedule, from 1 July 2026, with COVID-19 as updated 1 October 2026) and its source
  (health.gov.au). It states the schedule and the record; it isn't a reminder.
- The **Vaccine Eligibility (NIP)** data block (for AI workflows) gives, per vaccine, the basis, the
  last recorded dose, a note stating what the schedule says and what is recorded, and the
  schedule's version and source. The notes don't advise the patient.

What you stay responsible for: vaccines given elsewhere may not be recorded here (check the
Australian Immunisation Register), and an at-risk condition counts only if it meets the NIP
criteria, which you confirm.
