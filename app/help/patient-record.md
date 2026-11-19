---
title: Patient record
area: Patients
roles: [doctor, nurse]
reviewed: 2026-11-14
related: [results-outside-range, setup]
---

The patient record screen brings together what Best Practice holds about a patient. MedUI
reads it from Best Practice and doesn't change it.

## Disease Profile {#disease-profile}

The **Disease Profile** panel, at the bottom of the left-hand column, shows badges for
conditions **recorded** in the patient's past history, from Best Practice's coded items
(active items only, including a coded *Reason for visit* that Best Practice copied to past history): diabetes (type 1, type 2 or unspecified; not borderline or gestational), IHD, hypertension, atrial fibrillation, stroke, CKD,
vasculopathy, COVID-19 and a pacemaker. A BMI over 30 is shown with the weight and its date.

Which Best Practice item codes count as each condition is the practice's list: **Admin →
Mapping Tables → condition_codes**, one row per condition and code (diabetes, ckd, ihd and so
on, conditions that affect how results read, such as iron_deficiency, and the
[population chart](#population-chart)'s filters). Delete a row to stop a code counting,
add one to make it count; changes show within five minutes. It starts with the codes MedUI has
always used. The bp_item column shows Best Practice's own name for each code, filled in
automatically.

Recorded CKD shows the stage only if one was recorded, the year it was recorded, and the
latest eGFR: *CKD stage 3B (recorded 2021) · eGFR 24, Mar 2026*. A recorded stage can fall
out of date as the eGFR changes; the two side by side let you see whether the record needs
updating. A recorded stage 1 or 2 (kidney damage with a normal eGFR) correctly sits beside an
eGFR over 60.

**"eGFR < 60 for 3+ months"** is different: it describes the results, not a recorded
diagnosis. It appears only where CKD isn't recorded, when:

- at least two eGFR results are below 60,
- the first and last of them are at least 90 days apart, and
- no eGFR of 60 or more lies between them.

This is the eGFR part of the KDIGO definition of chronic kidney disease (below 60 for more
than 3 months). Hover over the badge to see the dates and values. If the latest eGFR is now
60 or more, the badge says *(to Mar 2025)*, for example, and the latest result is in the
detail. Values are read as the laboratory wrote them: *>90* counts as 60 or more, and a value
that can't be placed either side of 60 is left out.

Both CKD badges' tooltips include the KDIGO 2024 categories for reference: the eGFR
categories G1–G5 and the urine albumin/creatinine categories A1–A3. They're there to save
looking them up; MedUI doesn't pick out a category for the patient.

**"HbA1c ≥ 6.5% on 2 occasions"** works the same way for diabetes. It appears only for adults
where diabetes isn't recorded, when HbA1c has been 6.5% (48 mmol/mol) or more on two different
days (a sample reported in both units counts once). HbA1c is shown as %: a result the laboratory
reported in mmol/mol is converted with the IFCC–NGSP master equation (% = 0.09148 × mmol/mol +
2.152), with the laboratory's mmol/mol figure beside it in the tooltip. This is the diagnostic criterion in the RACGP
handbook and the Australian Diabetes Society's 2015 statement. Later, lower results don't remove
it. Where the record has a condition that affects how HbA1c reads, the badge is still shown,
and its tooltip says which way the condition pushes HbA1c, with the relevant latest results:
- **may raise it** (the result may overstate glucose): iron deficiency (with ferritin and
  haemoglobin), B12 or folate deficiency (B12, folate, haemoglobin), asplenia;
- **may lower it** (glucose may be higher than the result suggests): haemolysis, pregnancy
  recorded near the time of the results;
- **either way**: a haemoglobin variant (depends on the laboratory's method), advanced CKD
  (recorded, or a latest eGFR below 30).

What each condition means here, its wording, its source and the results shown with it are the
practice's list: **Admin → Mapping Tables → influences** (situation *hba1c_interpretation*). Transfusions and iron
infusions are rarely recorded, so the tooltip mentions them. Recorded diabetes shows its type
(if recorded), the year and the latest HbA1c. Both diabetes tooltips list the Australian HbA1c
targets for reference; MedUI doesn't compare them with the patient's results.

What you stay responsible for: the badges don't diagnose diabetes or CKD, MedUI doesn't stage
CKD, and the eGFR badge doesn't use urine albumin. Whether the patient has diabetes or CKD, and
recording it, is your decision. A practice manager can switch either results badge off in
Application Setup → General.

## Charts {#charts}

**Patient Charts** draws each curated test over time: glucose, cholesterol (total, HDL, LDL),
eGFR, urine albumin, HbA1c, TSH, PSA, ferritin, FIB-4, weight and blood pressure.

- The shaded band is the **laboratory's range**, from the most recent result that has one;
  the caption says which result. A laboratory's range can change over time (for PSA, with
  age), so earlier results may have been reported against a different range.
- Points above or below the band are labelled *Above range* and *Below range*. MedUI doesn't
  draw targets of its own: practice targets will come with the practice-policy work.
- Tests the laboratory reports without a range (FIB-4, which MedUI calculates from the
  results; weight; blood pressure) have no band. The weight caption gives the BMI and the
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
- Beside Immunisations, **"NIP funded, none recorded in interval: …"** names the vaccines that are
  funded for the patient with no dose recorded within the schedule's interval.
- The **Vaccine Eligibility (NIP)** data block (for AI workflows) gives, per vaccine, the basis, the
  last recorded dose and a note stating what the schedule says and what is recorded. The notes
  don't advise the patient.

What you stay responsible for: vaccines given elsewhere may not be recorded here (check the
Australian Immunisation Register), and an at-risk condition counts only if it meets the NIP
criteria, which you confirm.
