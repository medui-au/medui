"""An EXAMPLE practice protocol for the tests only (ADR-171 data shape). It is not part of MedUI and
not a recommendation: each practice builds its own protocol on Admin → Practice Protocols. The tests
load it through conftest.py in place of a practice's own data module."""
from datetime import date

ACCESSED = date(2026, 11, 22)

# key → guideline row (careplan_guidelines). Matched to existing rows by title.
GUIDELINES = {
    'redbook': dict(title='Guidelines for preventive activities in general practice (Red Book)',
                    publisher='RACGP', edition='10th edn, 2024', published_on=date(2024, 6, 28),
                    url='https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/'
                        'view-all-racgp-guidelines/preventive-activities-in-general-practice'),
    'racgp_t2d': dict(title='Management of type 2 diabetes: A handbook for general practice',
                      publisher='RACGP and Diabetes Australia', edition='web edition, recommendations 14/11/2024',
                      published_on=date(2024, 11, 14),
                      url='https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/'
                          'view-all-racgp-guidelines/management-of-type-2-diabetes'),
    'cvd2023': dict(title='Australian guideline for assessing and managing cardiovascular disease risk',
                    publisher='Australian Chronic Disease Prevention Alliance', edition='2023',
                    published_on=date(2023, 5, 22), url='https://www.cvdcheck.org.au'),
    'acs2025': dict(title='Australian clinical guideline for diagnosing and managing acute coronary syndromes',
                    publisher='National Heart Foundation of Australia and CSANZ', edition='2025',
                    url='https://www.heartfoundation.org.au/for-professionals/acs-guideline'),
    'hf_htn2016': dict(title='Guideline for the diagnosis and management of hypertension in adults',
                       publisher='National Heart Foundation of Australia', edition='2016',
                       published_on=date(2016, 7, 18),
                       url='https://www.mja.com.au/journal/2016/205/2/guideline-diagnosis-and-management-hypertension-adults-2016'),
    'nhmrc_alcohol': dict(title='Australian guidelines to reduce health risks from drinking alcohol',
                          publisher='NHMRC', edition='2020', published_on=date(2020, 12, 1),
                          url='https://www.nhmrc.gov.au/health-advice/alcohol'),
    'nbcsp': dict(title='National Bowel Cancer Screening Program: lowered eligible age',
                  publisher='Australian Government Department of Health', edition='from 1 July 2024',
                  url='https://www.health.gov.au/our-work/national-bowel-cancer-screening-program/'
                      'about-the-national-bowel-cancer-screening-program/lowered-eligible-age'),
    'nlcsp': dict(title='National Lung Cancer Screening Program (Red Book lung cancer topic)',
                  publisher='RACGP / Australian Government', edition='from 1 July 2025',
                  url='https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/'
                      'view-all-racgp-guidelines/preventive-activities-in-general-practice/cancer/lung-cancer'),
    'gout': dict(title='Gout (check, Independent learning program)', publisher='RACGP', edition='2024',
                 url='https://www.racgp.org.au/check/check-issues/2024/gout'),
    'mbs_an047': dict(title='MBS explanatory note AN.0.47: GP chronic condition management plans',
                      publisher='Australian Government (MBS Online)', edition='1 November 2026',
                      url='https://www9.health.gov.au/mbs/fullDisplay.cfm?type=note&qt=NoteID&q=AN.0.47'),
    'practice_library': dict(title='Example practice library (invented, for tests)',
                             publisher='An example practice', edition='example',
                             licence_note='Invented for the tests'),
}

# key, label, unit, careplan result-token key, scope, order
MEASURES = [
    ('bp', 'Blood pressure', 'mmHg', 'bp', 'protocol', 10),
    ('ldl', 'LDL cholesterol', 'mmol/L', 'ldl_c', 'protocol', 20),
    ('hba1c', 'HbA1c', '%', 'hba1c_ngsp', 'protocol', 30),
    ('home_bgl', 'Home blood glucose (if monitoring)', 'mmol/L', None, 'protocol', 40),
    ('alcohol', 'Alcohol', 'standard drinks', 'alcohol', 'protocol', 50),
    ('activity', 'Physical activity', 'minutes a week', None, 'protocol', 60),
    ('uacr', 'Urine albumin-to-creatinine ratio', 'mg/mmol', 'uacr', 'individual', 110),
    ('urate', 'Serum urate', 'mmol/L', 'urate', 'individual', 120),
    ('waist', 'Waist circumference', 'cm', None, 'individual', 130),
    ('weight', 'Weight', 'kg', 'weight', 'individual', 140),
]

ASCVD = ['isIHD', 'isCVA', 'isVasculopathy', 'isRevascularisation']

# measure key → options. Each citation: (guideline key, section, short quote).
OPTIONS = {
    'bp': [
        dict(code='bp_high_risk', label='< 130/80 mmHg', priority=10,
             patient_group='Diabetes, CKD, or established cardiovascular disease (coronary disease, stroke/TIA, PVD)',
             plan_wording='The practice target for your blood pressure is below 130/80.',
             default_rule={'any': ['isDiabetes', 'isCKDRecorded'] + ASCVD},
             rationale='Decision 1. The stricter of the RACGP diabetes handbook\'s two CKD figures, applied to the '
                       'whole higher-risk group; matches the practice library.',
             citations=[('racgp_t2d', 'Goals for optimum management', 'Diabetes with CKD: < 130/80 mmHg'),
                        ('practice_library', 'Hypertension', 'Target blood pressure is < 130/80 on average')]),
        dict(code='bp_general', label='< 140/90 mmHg (the GP may set lower)', priority=90,
             patient_group='Hypertension without diabetes, CKD or known cardiovascular disease',
             plan_wording='The practice target for your blood pressure is below 140/90; your GP may set a lower one.',
             default_rule={'always': True},
             rationale='Decision 1. National clinical guidance; a lower individual target stays open to the GP.',
             citations=[('hf_htn2016', 'Treatment targets', '< 140/90 mmHg or lower if tolerated'),
                        ('racgp_t2d', 'Goals for optimum management', 'Generally ≤ 140/90 mmHg'),
                        ('cvd2023', 'Blood pressure-lowering treatment',
                         'consider setting a target based on individual CVD risk factors, in collaboration with the person')]),
        dict(code='bp_individual', label='GP sets individually (aged 80+ or frail)', priority=100, gp_sets=True,
             patient_group='Aged 80 or over, or frail (the GP decides)',
             plan_wording='Your GP has set your blood pressure target.',
             rationale='Decision 1. No numeric target for the very old in the guidelines read; watch for '
                       'orthostatic hypotension and syncope.',
             citations=[('cvd2023', 'Blood pressure-lowering treatment',
                         'In older people, monitor for medicine-related adverse effects such as orthostatic hypotension or syncope')]),
    ],
    'ldl': [
        dict(code='ldl_ascvd', label='< 1.4 mmol/L and a reduction of at least 50% from baseline', priority=10,
             patient_group='Established atherosclerotic disease: coronary disease or MI, stroke/TIA, PVD, revascularisation',
             plan_wording='The practice target for your LDL cholesterol is below 1.4 mmol/L, and at least half your starting level.',
             default_rule={'any': ASCVD},
             rationale='Decision 2. Current national guidance for established disease.',
             citations=[('acs2025', 'Recovery and secondary prevention',
                         'an initial target LDL-C level of < 1.4 mmol/L and a reduction of at least 50% from baseline'),
                        ('racgp_t2d', 'Summary of recommendations', 'Diabetes with ASCVD: LDL-C < 1.4 mmol/L and ≥ 50% reduction')]),
        dict(code='ldl_high', label='< 2.0 mmol/L', priority=20,
             patient_group='Diabetes, CKD or familial hypercholesterolaemia, without established atherosclerotic disease',
             plan_wording='The practice target for your LDL cholesterol is below 2.0 mmol/L.',
             default_rule={'any': ['isDiabetes', 'isCKDRecorded', 'isFH']},
             rationale='Decision 2. The earlier RACGP diabetes goal, already in the practice\'s 2024 plans. CVD 2023 does '
                       'not treat diabetes alone as automatically high risk: this is a practice choice.',
             citations=[('racgp_t2d', 'Goals for optimum management (earlier edition, about 2020)', 'LDL-C < 2.0 mmol/L'),
                        ('cvd2023', 'Clinically determined high risk',
                         'moderate-to-severe CKD and confirmed familial hypercholesterolaemia are managed as high risk')]),
        dict(code='ldl_aspirational', label='Aspirational: total cholesterol < 4.0 with LDL-C < 2.0 mmol/L', priority=90,
             patient_group='Everyone else in a plan (primary prevention)',
             plan_wording="The practice's aspirational target is total cholesterol below 4.0 and LDL cholesterol below 2.0 mmol/L.",
             default_rule={'always': True},
             rationale='Decision 2. Continues the practice library for goal-setting. Labelled aspirational: CVD 2023 '
                       'decides treatment by five-year risk category, not by a lipid target.',
             citations=[('practice_library', 'Hypercholesterolaemia', 'Your target cholesterol is 4.0 mmol/L'),
                        ('cvd2023', 'Lipid-modifying treatment',
                         'It is uncertain whether treating to a specific, lower, plasma lipid target in primary prevention')]),
    ],
    'hba1c': [
        dict(code='hba1c_general', label='Generally ≤ 7% (53 mmol/mol), individualised by the GP', priority=10,
             patient_group='Type 2 diabetes',
             plan_wording="The practice's general aim for your HbA1c is 7% (53 mmol/mol) or less; your GP may set an individual target.",
             default_rule={'any': ['isDiabetes']},
             rationale='Decision 3. RACGP diabetes handbook, individualised.',
             citations=[('racgp_t2d', 'Goals for optimum management', 'Generally ≤7% (53 mmol/mol)')]),
        dict(code='hba1c_individual', label='GP sets individually', priority=100, gp_sets=True,
             patient_group='Frail, palliative, or where the GP individualises',
             plan_wording='Your GP has set your HbA1c target.',
             rationale='Decision 3. Less stringent goals where life expectancy is limited.',
             citations=[('racgp_t2d', 'HbA1c targets and individualisation', 'needs individualisation according to patient circumstances')]),
    ],
    'home_bgl': [
        dict(code='bgl_racgp', label='Fasting / before meals 4.0–7.0; 2 hours after meals 5.0–10.0 mmol/L', priority=10,
             patient_group='Only where the GP has asked the patient to check their glucose at home',
             plan_wording='If you check your blood glucose at home, aim for 4.0–7.0 mmol/L fasting or before meals and '
                          '5.0–10.0 mmol/L two hours after meals.',
             rationale='Decision 3. RACGP figures; not preselected, because home monitoring is the GP\'s decision.',
             citations=[('racgp_t2d', 'Self-monitoring of blood glucose', 'fasting and preprandial 4.0–7.0 mmol/L; 2-hour postprandial 5.0–10.0')]),
    ],
    'alcohol': [
        dict(code='alcohol_nhmrc', label='No more than 10 standard drinks a week and no more than 4 on any one day', priority=10,
             patient_group='Adults',
             plan_wording='No more than 10 standard drinks a week and no more than 4 on any one day. The less you drink, the lower your risk.',
             default_rule={'always': True},
             rationale='Decision 4. Replaces the library\'s "less than 2 standard drinks a day" (NHMRC 2009).',
             citations=[('nhmrc_alcohol', 'Guideline 1', 'no more than 10 standard drinks a week and no more than 4 standard drinks on any one day'),
                        ('redbook', 'Alcohol', 'there is no level of drinking with no risk')]),
    ],
    'activity': [
        dict(code='activity_guidelines', label='150–300 min moderate (or 75–150 vigorous) a week, plus strength on 2+ days', priority=10,
             patient_group='Adults; from 65, add balance activities on 3 or more days',
             plan_wording='Aim for 150 to 300 minutes of moderate activity a week (or 75 to 150 minutes of vigorous activity), '
                          'plus muscle-strengthening activity on at least 2 days. From 65, include balance activities on 3 or more days.',
             default_rule={'always': True},
             rationale='Decision 11 (adopted).',
             citations=[('redbook', 'Physical activity', 'at least 150-300 minutes a week of moderate activity; muscle strengthening on 2 or more days')]),
    ],
    'uacr': [
        dict(code='uacr_racgp', label='Women < 3.5 mg/mmol; men < 2.5 mg/mmol', priority=10,
             patient_group='Individual patients (set by the GP outside the GPCCMP protocol)',
             plan_wording='Your target urine albumin-to-creatinine ratio is below {value}.',
             rationale='Decision 11: not part of the GPCCMP protocol; available to the GP for an individual patient.',
             citations=[('racgp_t2d', 'Goals for optimum management', 'women <3.5 mg/mmol; men <2.5 mg/mmol')]),
    ],
    'urate': [
        dict(code='urate_treat_to_target', label='< 0.36 mmol/L (< 0.30 mmol/L with tophi)', priority=10,
             patient_group='Individual patients with gout (set by the GP)',
             plan_wording='Your target serum urate is below {value}.',
             rationale='Decision 11: not part of the GPCCMP protocol.',
             citations=[('gout', 'Urate-lowering therapy', 'under 0.36 mmol/L for non-tophaceous gout and under 0.30 mmol/L for tophaceous gout')]),
    ],
    'waist': [
        dict(code='waist_redbook', label='Men < 94 cm; women < 80 cm', priority=10,
             patient_group='Individual patients (set by the GP)',
             plan_wording='Your target waist measurement is below {value}.',
             rationale='Decision 11: not part of the GPCCMP protocol. Red Book thresholds for increased risk.',
             citations=[('redbook', 'Overweight and obesity', 'men 94 cm or more increased risk (102 greatly increased); women 80 cm and 88 cm')]),
    ],
    'weight': [
        dict(code='weight_5_10', label='5–10% weight loss', priority=10,
             patient_group='Individual patients who are overweight (set by the GP)',
             plan_wording='Your goal is to lose 5 to 10% of your body weight.',
             rationale='Decision 11: an individual goal the GP may set.',
             citations=[('racgp_t2d', 'Goals for optimum management', '5–10% weight loss for people who are overweight or obese')]),
    ],
}

CVD_FLAGS = ['isHypercholesterolaemia', 'isDiabetes', 'isHT', 'isCKDRecorded', 'isFH'] + ASCVD

# condition_key, label, applies_when, fields. No targets and no named medicines or doses in patient text.
MODULES = [
    ('diabetes_glucose', 'Type 2 diabetes: blood glucose', {'any': ['isDiabetes']}, dict(
        goals='Keep my blood glucose in my target range over the long term.',
        measures_text='HbA1c; home blood glucose readings if the GP has asked for monitoring.',
        monitoring='HbA1c every 3–6 months depending on control, as the GP judges; at least every 12 months. '
                   'GP review at least twice a year: blood pressure, medicines, diabetes education.',
        services=['Credentialled diabetes educator', 'Dietitian'],
        patient_info='Your doctor will arrange an HbA1c blood test every 3 to 6 months. This test measures your average '
                     'blood glucose over the last 3 months.',
        safety_netting='See your GP sooner if your readings are repeatedly outside the range your GP gave you, you have '
                       'symptoms of very high or low blood glucose, or you are unwell and cannot keep fluids down.',
        source_note='Practice library "Diabetes Type 2 – Blood Glucose Control"; RACGP diabetes handbook.')),
    ('diabetes_complications', 'Type 2 diabetes: complications screening', {'any': ['isDiabetes']}, dict(
        goals='Find any eye, kidney, foot or nerve problems early.',
        measures_text='Eye check done (date); urine albumin-to-creatinine ratio and eGFR (date, value); foot check done (date).',
        monitoring='Eye check by an optometrist or ophthalmologist every 1–2 years (at least yearly at higher risk). '
                   'Urine albumin-to-creatinine ratio and eGFR every 12 months. Foot and nerve check at least every 12 months.',
        services=['Optometrist', 'Podiatrist'],
        patient_info='A yearly urine test checks your kidneys, and a yearly check of your feet looks for nerve or circulation changes early.',
        source_note='Practice library "Screening for complications"; RACGP diabetes handbook (cycle of care).')),
    ('cv_risk', 'Cardiovascular risk and cholesterol', {'any': CVD_FLAGS}, dict(
        goals='Lower my risk of heart attack and stroke.',
        measures_text='Lipid profile (date, values); blood pressure; smoking status.',
        monitoring='Lipids every 12 months until at the target, then every 1–2 years; blood pressure each visit.',
        services=['Dietitian', 'Exercise physiologist'],
        patient_info='Lowering your cholesterol towards your target can reduce your risk of heart and blood vessel disease. '
                     'You can lower your risk further by not smoking, eating a healthy diet, being active and keeping a healthy weight.',
        safety_netting='Tell your doctor about any chest pain or tightness on exertion, or an unexplained drop in how much you can do. '
                       'Call 000 for chest pain lasting more than 10 minutes, or with sweating or breathlessness.',
        source_note='Practice library "reduction of cardiac and vascular disease risk", "Hypercholesterolaemia".')),
    ('hypertension', 'Hypertension', {'any': ['isHT']}, dict(
        goals='Keep my blood pressure at my target over the long term, to prevent heart disease, stroke and kidney disease.',
        measures_text='Clinic blood pressure (latest); home blood pressure average if the GP has asked for it.',
        monitoring='Blood pressure each visit; when stable, at least every 6 months. Kidney function and lipids every 1–2 years.',
        services=['Pharmacist (medicine review)', 'Dietitian'],
        patient_info='Blood pressure control can be lost over time, and some people need more than one medicine to stay at '
                     'their target. Good control of blood pressure and cholesterol, and not smoking, keep your heart and stroke risk lower.',
        source_note='Practice library "Hypertension (high blood pressure)".')),
    ('chd_stroke', 'Coronary heart disease, stroke or TIA', {'any': ['isIHD', 'isCVA', 'isRevascularisation']}, dict(
        goals='Prevent another event and keep active.',
        measures_text='Blood pressure; lipids; activity; smoking status.',
        monitoring='As for cardiovascular risk and hypertension; specialist follow-up as recorded.',
        services=['Cardiac or stroke rehabilitation', 'Exercise physiologist'],
        patient_info='Take your heart and blood-thinning medicines as prescribed. Know the signs of stroke: Face, Arms, Speech, Time. '
                     'Call 000 at once if you notice them.',
        safety_netting='As for cardiovascular risk, plus the signs of stroke.',
        source_note='Practice library "Known coronary artery disease", "secondary prevention".')),
    ('af', 'Atrial fibrillation', {'any': ['isAF']}, dict(
        goals='Keep my heart rate and rhythm controlled and lower my risk of stroke.',
        measures_text='Pulse and blood pressure at visits; medicines taken as prescribed.',
        monitoring='ECG and other tests as the GP or cardiologist sets.',
        services=['Cardiologist (as recorded)'],
        patient_info='Take your medicines as prescribed. Know the signs of stroke: Face, Arms, Speech, Time.',
        safety_netting='See your GP soon for palpitations that do not settle, dizziness or fainting; call 000 for signs of stroke or chest pain.',
        source_note='Practice plans 2022.')),
    ('ckd', 'Chronic kidney disease', {'any': ['isCKDRecorded']}, dict(
        goals='Protect my kidney function.',
        measures_text='eGFR; urine albumin-to-creatinine ratio; blood pressure.',
        monitoring='eGFR and urine albumin-to-creatinine ratio at least every 12 months, more often as the GP sets.',
        services=['Dietitian', 'Nephrologist (as recorded)'],
        patient_info='Some medicines, including anti-inflammatory pain relievers, can affect the kidneys. Check with your GP '
                     'or pharmacist before starting a new medicine, including ones bought without a prescription.',
        source_note='New in v1 (no library module). Red Book kidney topic: yearly checks with diabetes or hypertension.')),
    ('copd', 'COPD', None, dict(
        goals='Keep my breathing as good as possible and recover quickly from flare-ups.',
        measures_text='Symptoms; flare-ups in the past year; spirometry if the GP repeats it.',
        monitoring='Inhaler technique checked at review; vaccines from the NIP block.',
        services=['Pulmonary rehabilitation or exercise physiologist', 'Physiotherapist'],
        patient_info='Use your preventer and reliever medicines as your GP has advised. See your GP early if a chest infection '
                     'or worse breathing starts. Yearly influenza vaccination is recommended.',
        safety_netting="See your GP the same day if your breathing is worse than usual and your reliever isn't helping, or you have "
                       'a fever with more cough or sputum; call 000 if you are very breathless or drowsy.',
        source_note='Practice library "COPD".')),
    ('asthma', 'Asthma', None, dict(
        goals='Keep my asthma symptoms well controlled while using the lowest effective medicine.',
        measures_text='Symptoms; reliever use; night waking; flare-ups.',
        monitoring='Written asthma action plan reviewed; inhaler technique checked.',
        services=['Pharmacist (inhaler technique)'],
        patient_info='Use your preventer every day as prescribed, even when you feel well.',
        safety_netting="Follow your asthma action plan. Call 000 if your reliever isn't helping or you can't speak in sentences.",
        source_note='Practice library "Controlled asthma using preventer medication".')),
    ('osteoarthritis', 'Osteoarthritis', None, dict(
        goals='Control pain, keep mobile and use medicines safely.',
        measures_text='Pain score; walking distance or a named activity; function.',
        services=['Physiotherapist', 'Exercise physiologist', 'Dietitian (if weight is a goal)'],
        patient_info='Osteoarthritis needs some physical and emotional adjustment to the pain and stiffness it causes. Pain is '
                     'often helped by simple measures such as heat, massage and rub-on treatments, and by regular gentle exercise. '
                     'Simple pain relief may help on bad days; your GP will advise what suits you.',
        gp_reference='Practice approach (library): regular simple analgesia first, with second-line agents for the worst days. '
                     'Uncontrolled chronic pain is an indication to discuss referral for joint replacement.',
        source_note='Practice library "Osteoarthritis" (5 standard paragraphs); the dose wording moved out of patient text (decision 7).')),
    ('rheumatoid_arthritis', 'Rheumatoid arthritis', None, dict(
        goals='Keep my arthritis well suppressed, as measured by my symptoms and blood tests.',
        measures_text='Symptoms; ESR and CRP as monitored.',
        monitoring='Blood tests at the interval the rheumatologist sets.',
        services=['Rheumatologist (as recorded)', 'Physiotherapist', 'Occupational therapist'],
        patient_info='Some arthritis medicines need regular blood tests and must be taken exactly as directed. Keep to your blood test schedule.',
        source_note='Practice library "Rheumatoid arthritis".')),
    ('gout', 'Gout', None, dict(
        goals='Prevent further attacks of gout.',
        measures_text='Attacks in the last 6 months; serum urate if the GP monitors it.',
        patient_info='Drink plenty of water and limit alcohol, especially beer. See your GP early in an attack.',
        source_note='Practice library "Gout".')),
    ('osteoporosis', 'Osteoporosis', None, dict(
        goals='Reduce my risk of fractures.',
        measures_text='Falls in the past year; bone density (date) as the GP sets.',
        services=['Physiotherapist or exercise physiologist (strength and balance)'],
        patient_info='Weight-bearing exercise, enough calcium and vitamin D in your diet, and preventing falls all help protect '
                     'your bones. Take your bone medicine exactly as directed.',
        source_note='Practice plans 2022.')),
    ('skin_cancer', 'Past skin cancer or solar damage', None, dict(
        goals='Find any new skin cancer early, when it can be treated simply.',
        measures_text='Skin check done (date).',
        monitoring='By recorded history (Red Book): previous melanoma, a skin check at least every 12 months; other past skin '
                   'cancer, an opportunistic check usually no more than once a year; very high risk, every 6 months (GP to confirm).',
        patient_info='You have had skin cancer before, a sign of past sun damage, so your risk of new skin cancers is higher than '
                     "average. We'd like to find them as early as possible. At your request we can put this on our recall system to remind you.",
        source_note='Practice library (6 standard paragraphs), with the Red Book risk tiers (decision 6).')),
    ('medication_management', 'Medication management', None, dict(
        goals='Take my medicines safely and as prescribed.',
        measures_text='Medicines list reconciled; dose administration aid used, if relevant.',
        services=['Pharmacist (home medicines review, dose administration aid)'],
        patient_info='Bring all your medicines, including ones bought without a prescription, to your review.',
        source_note='Practice library "Pharmacy care", "Medication management".')),
    ('living_at_home', 'Living safely at home', None, dict(
        goals='Keep living safely at home.',
        measures_text='Falls; ability to manage named daily tasks; supports in place.',
        services=['Occupational therapist', 'Physiotherapist', 'Podiatrist', 'Practice nurse health assessment'],
        patient_info='Help at home can be arranged through My Aged Care if you need it.',
        source_note='Practice library "Health maintenance, Home management".')),
]

# key, label, rule, wording, source. Worked out by MedUI from recorded facts (phase 4), never the AI.
PREVENTION = [
    ('bowel', 'Bowel cancer screening', {'age_min': 45, 'age_max': 74, 'flags_none': ['isColonCaPolyps']},
     'A free home bowel screening test every 2 years, ages 45–74 (National Bowel Cancer Screening Program). '
     'Not needed while you are on a colonoscopy program.', 'Red Book; NBCSP (from 45 since 1 July 2024).'),
    ('breast', 'Breast screening', {'sex': 'F', 'age_min': 50, 'age_max': 74},
     'A mammogram every 2 years through BreastScreen, women aged 50–74.', 'Red Book.'),
    ('cervical', 'Cervical screening', {'sex': 'F', 'age_min': 25, 'age_max': 74},
     'A cervical screening (HPV) test every 5 years, ages 25–74. You can choose to collect the sample yourself.', 'Red Book.'),
    ('lung', 'Lung cancer screening', {'age_min': 50, 'age_max': 70, 'needs': 'smoking_history'},
     'You may be eligible for the National Lung Cancer Screening Program (ages 50–70, smoking now or quit in the last '
     '10 years, at least 30 pack-years): a low-dose CT scan every 2 years. Please discuss it with your GP.',
     'NLCSP via the Red Book lung topic (from 1 July 2025). Decision 8.'),
    ('prostate', 'Prostate (PSA) testing: informed choice', {'sex': 'M', 'age_min': 50, 'age_max': 69},
     'Men aged 50–69 can discuss the benefits and harms of PSA testing with their GP and decide whether to test.',
     'Red Book (from 45 with a moderate family history, 40 with a high one; GP to judge). Decision 6.'),
    ('skin', 'Skin checks by risk', {'needs': 'skin_cancer_history'},
     'With a past melanoma, a skin check at least every 12 months; with other past skin cancer, a check about once a year; '
     'your GP will tell you if you need checks more often.', 'Red Book skin cancer topic. Decision 6.'),
    ('cvd_risk', 'Heart and stroke risk check', {'age_min': 45, 'age_max': 79, 'flags_none': ASCVD},
     'A heart and stroke risk check with your GP (Australian CVD risk calculator), usually every 5 years from 45 '
     '(from 35 with diabetes, from 30 for Aboriginal and Torres Strait Islander people).', 'Red Book; CVD 2023.'),
    ('falls', 'Falls', {'age_min': 65},
     'Tell your GP about any falls; a yearly falls check is recommended from 65 (from 50 for Aboriginal and Torres Strait '
     'Islander people).', 'Red Book falls topic.'),
    ('bones', 'Bone health', {'age_min': 50},
     'From 50, your GP can check your risk of fractures; routine bone density scans are not recommended for everyone.',
     'Red Book osteoporosis topic.'),
    ('diabetes_risk', 'Diabetes risk check', {'age_min': 40, 'flags_none': ['isDiabetes']},
     'A diabetes risk check (AUSDRISK) every 3 years from 40 (a yearly blood test from 18 for Aboriginal and Torres Strait '
     'Islander people).', 'Red Book diabetes topic.'),
]
