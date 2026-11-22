---
title: Patient targets
area: Patients
roles: [doctor, nurse]
reviewed: 2026-11-22
related: [practice-protocols, care-plans, patient-record]
---

**Patient Data → GPCCMP: Targets & Plan** (or **Targets** in Patient Tools) shows a patient's
current targets: blood pressure, LDL cholesterol, HbA1c and the others the practice protocol
covers, plus any individual targets their doctor has set. Nurses can see them; doctors set and
change them. MedUI never sets a target itself and never says whether one has been met.

## Setting and changing targets {#overview}

Each measure shows the patient's current target, who set it and when, with the latest result
from Best Practice beside it for reference. A doctor presses **Change** to choose again.

Where a measure has no target yet, the options come from the practice protocol (Admin →
Practice Protocols). If the protocol has a rule for a condition **coded** in the patient's record,
that option is **preselected** and the reason is shown, for example *Practice protocol v1: IHD
coded*. You can:

- keep the preselected option;
- choose another option;
- set an **individual target** for this patient, with an optional reason;
- choose **No target for now**.

**Background** under each option shows the guidelines and the practice's reason for it. Some
options are marked as targets the GP sets: you enter the value.

**Add a measure** brings in measures that aren't preselected for this patient, including
measures that are for individual patients only (such as uACR, urate and waist).

Nothing is saved until you press **Save targets** or **Save and continue to plan decisions**. Only
new and changed targets are saved. A measure showing a preselected option is saved with it; choose
**No target for now** to leave it unset. If you try to leave the page another way with changes not
saved, the browser asks first. The whole flow is in [GPCCMP plan decisions](help:gpccmp-plan.flow).

## History {#history}

A target is never overwritten. A change closes the old target and keeps it, so **Earlier
targets** under each measure lists every target that was set, by whom, when, under which
protocol version and why.
