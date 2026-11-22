"""The protocol catalogue (ADR-182): what the setup wizard offers a practice building its own
protocol. Guideline-supported options per measure, each with its citations, and patient groups whose
rules decide which option a GP sees preselected, but no choices: the practice makes every one in the
wizard. Also example condition wording (from a general practice's care-plan library, de-identified)
and prevention lines, for the practice to keep, edit or drop. Australian guidelines only.

Nothing here is used until a practice runs the wizard and an administrator approves the result.
"""
import datetime

ACCESSED = datetime.date(2026, 11, 22)   # when the guideline links and quotes were checked

ASCVD = ['isIHD', 'isCVA', 'isVasculopathy', 'isRevascularisation']

# key, label, unit, careplan result-token key, scope, order (as the seeded measures)
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

GUIDELINES = {'redbook': {'title': 'Guidelines for preventive activities in general practice (Red Book)',
             'publisher': 'RACGP',
             'edition': '10th edn, 2024',
             'published_on': datetime.date(2024, 6, 28),
             'url': 'https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/view-all-racgp-guidelines/preventive-activities-in-general-practice'},
 'racgp_t2d': {'title': 'Management of type 2 diabetes: A handbook for general practice',
               'publisher': 'RACGP and Diabetes Australia',
               'edition': 'web edition, recommendations 14/11/2024',
               'published_on': datetime.date(2024, 11, 14),
               'url': 'https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/view-all-racgp-guidelines/management-of-type-2-diabetes'},
 'cvd2023': {'title': 'Australian guideline for assessing and managing cardiovascular disease risk',
             'publisher': 'Australian Chronic Disease Prevention Alliance',
             'edition': '2023',
             'published_on': datetime.date(2023, 5, 22),
             'url': 'https://www.cvdcheck.org.au'},
 'acs2025': {'title': 'Australian clinical guideline for diagnosing and managing acute coronary syndromes',
             'publisher': 'National Heart Foundation of Australia and CSANZ',
             'edition': '2025',
             'url': 'https://www.heartfoundation.org.au/for-professionals/acs-guideline'},
 'hf_htn2016': {'title': 'Guideline for the diagnosis and management of hypertension in adults',
                'publisher': 'National Heart Foundation of Australia',
                'edition': '2016',
                'published_on': datetime.date(2016, 7, 18),
                'url': 'https://www.mja.com.au/journal/2016/205/2/guideline-diagnosis-and-management-hypertension-adults-2016'},
 'nhmrc_alcohol': {'title': 'Australian guidelines to reduce health risks from drinking alcohol',
                   'publisher': 'NHMRC',
                   'edition': '2020',
                   'published_on': datetime.date(2020, 12, 1),
                   'url': 'https://www.nhmrc.gov.au/health-advice/alcohol'},
 'nbcsp': {'title': 'National Bowel Cancer Screening Program: lowered eligible age',
           'publisher': 'Australian Government Department of Health',
           'edition': 'from 1 July 2024',
           'url': 'https://www.health.gov.au/our-work/national-bowel-cancer-screening-program/about-the-national-bowel-cancer-screening-program/lowered-eligible-age'},
 'nlcsp': {'title': 'National Lung Cancer Screening Program (Red Book lung cancer topic)',
           'publisher': 'RACGP / Australian Government',
           'edition': 'from 1 July 2025',
           'url': 'https://www.racgp.org.au/clinical-resources/clinical-guidelines/key-racgp-guidelines/view-all-racgp-guidelines/preventive-activities-in-general-practice/cancer/lung-cancer'},
 'gout': {'title': 'Gout (check, Independent learning program)',
          'publisher': 'RACGP',
          'edition': '2024',
          'url': 'https://www.racgp.org.au/check/check-issues/2024/gout'},
 'mbs_an047': {'title': 'MBS explanatory note AN.0.47: GP chronic condition management plans',
               'publisher': 'Australian Government (MBS Online)',
               'edition': '1 November 2026',
               'url': 'https://www9.health.gov.au/mbs/fullDisplay.cfm?type=note&qt=NoteID&q=AN.0.47'}}

MODULES = [('diabetes_glucose',
  'Type 2 diabetes: blood glucose',
  {'any': ['isDiabetes']},
  {'goals': 'Keep my blood glucose in my target range over the long term.',
   'measures_text': 'HbA1c; home blood glucose readings if the GP has asked for monitoring.',
   'monitoring': 'HbA1c every 3–6 months depending on control, as the GP judges; at least every 12 months. '
                 'GP review at least twice a year: blood pressure, medicines, diabetes education.',
   'services': ['Credentialled diabetes educator', 'Dietitian'],
   'patient_info': 'Your doctor will arrange an HbA1c blood test every 3 to 6 months. This test measures '
                   'your average blood glucose over the last 3 months.',
   'safety_netting': 'See your GP sooner if your readings are repeatedly outside the range your GP gave you, '
                     'you have symptoms of very high or low blood glucose, or you are unwell and cannot keep '
                     'fluids down.',
   'source_note': "Example wording from a general practice's care-plan library; RACGP diabetes handbook."}),
 ('diabetes_complications',
  'Type 2 diabetes: complications screening',
  {'any': ['isDiabetes']},
  {'goals': 'Find any eye, kidney, foot or nerve problems early.',
   'measures_text': 'Eye check done (date); urine albumin-to-creatinine ratio and eGFR (date, value); foot '
                    'check done (date).',
   'monitoring': 'Eye check by an optometrist or ophthalmologist every 1–2 years (at least yearly at higher '
                 'risk). Urine albumin-to-creatinine ratio and eGFR every 12 months. Foot and nerve check at '
                 'least every 12 months.',
   'services': ['Optometrist', 'Podiatrist'],
   'patient_info': 'A yearly urine test checks your kidneys, and a yearly check of your feet looks for nerve '
                   'or circulation changes early.',
   'source_note': "Example wording from a general practice's care-plan library; RACGP diabetes handbook "
                  '(cycle of care).'}),
 ('cv_risk',
  'Cardiovascular risk and cholesterol',
  {'any': ['isHypercholesterolaemia',
           'isDiabetes',
           'isHT',
           'isCKDRecorded',
           'isFH',
           'isIHD',
           'isCVA',
           'isVasculopathy',
           'isRevascularisation']},
  {'goals': 'Lower my risk of heart attack and stroke.',
   'measures_text': 'Lipid profile (date, values); blood pressure; smoking status.',
   'monitoring': 'Lipids every 12 months until at the target, then every 1–2 years; blood pressure each '
                 'visit.',
   'services': ['Dietitian', 'Exercise physiologist'],
   'patient_info': 'Lowering your cholesterol towards your target can reduce your risk of heart and blood '
                   'vessel disease. You can lower your risk further by not smoking, eating a healthy diet, '
                   'being active and keeping a healthy weight.',
   'safety_netting': 'Tell your doctor about any chest pain or tightness on exertion, or an unexplained drop '
                     'in how much you can do. Call 000 for chest pain lasting more than 10 minutes, or with '
                     'sweating or breathlessness.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('hypertension',
  'Hypertension',
  {'any': ['isHT']},
  {'goals': 'Keep my blood pressure at my target over the long term, to prevent heart disease, stroke and '
            'kidney disease.',
   'measures_text': 'Clinic blood pressure (latest); home blood pressure average if the GP has asked for it.',
   'monitoring': 'Blood pressure each visit; when stable, at least every 6 months. Kidney function and '
                 'lipids every 1–2 years.',
   'services': ['Pharmacist (medicine review)', 'Dietitian'],
   'patient_info': 'Blood pressure control can be lost over time, and some people need more than one '
                   'medicine to stay at their target. Good control of blood pressure and cholesterol, and '
                   'not smoking, keep your heart and stroke risk lower.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('chd_stroke',
  'Coronary heart disease, stroke or TIA',
  {'any': ['isIHD', 'isCVA', 'isRevascularisation']},
  {'goals': 'Prevent another event and keep active.',
   'measures_text': 'Blood pressure; lipids; activity; smoking status.',
   'monitoring': 'As for cardiovascular risk and hypertension; specialist follow-up as recorded.',
   'services': ['Cardiac or stroke rehabilitation', 'Exercise physiologist'],
   'patient_info': 'Take your heart and blood-thinning medicines as prescribed. Know the signs of stroke: '
                   'Face, Arms, Speech, Time. Call 000 at once if you notice them.',
   'safety_netting': 'As for cardiovascular risk, plus the signs of stroke.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('af',
  'Atrial fibrillation',
  {'any': ['isAF']},
  {'goals': 'Keep my heart rate and rhythm controlled and lower my risk of stroke.',
   'measures_text': 'Pulse and blood pressure at visits; medicines taken as prescribed.',
   'monitoring': 'ECG and other tests as the GP or cardiologist sets.',
   'services': ['Cardiologist (as recorded)'],
   'patient_info': 'Take your medicines as prescribed. Know the signs of stroke: Face, Arms, Speech, Time.',
   'safety_netting': 'See your GP soon for palpitations that do not settle, dizziness or fainting; call 000 '
                     'for signs of stroke or chest pain.',
   'source_note': "Example wording from a general practice's care plans."}),
 ('ckd',
  'Chronic kidney disease',
  {'any': ['isCKDRecorded']},
  {'goals': 'Protect my kidney function.',
   'measures_text': 'eGFR; urine albumin-to-creatinine ratio; blood pressure.',
   'monitoring': 'eGFR and urine albumin-to-creatinine ratio at least every 12 months, more often as the GP '
                 'sets.',
   'services': ['Dietitian', 'Nephrologist (as recorded)'],
   'patient_info': 'Some medicines, including anti-inflammatory pain relievers, can affect the kidneys. '
                   'Check with your GP or pharmacist before starting a new medicine, including ones bought '
                   'without a prescription.',
   'source_note': 'Red Book kidney topic: yearly checks with diabetes or hypertension.'}),
 ('copd',
  'COPD',
  None,
  {'goals': 'Keep my breathing as good as possible and recover quickly from flare-ups.',
   'measures_text': 'Symptoms; flare-ups in the past year; spirometry if the GP repeats it.',
   'monitoring': 'Inhaler technique checked at review; vaccines from the NIP block.',
   'services': ['Pulmonary rehabilitation or exercise physiologist', 'Physiotherapist'],
   'patient_info': 'Use your preventer and reliever medicines as your GP has advised. See your GP early if a '
                   'chest infection or worse breathing starts. Yearly influenza vaccination is recommended.',
   'safety_netting': "See your GP the same day if your breathing is worse than usual and your reliever isn't "
                     'helping, or you have a fever with more cough or sputum; call 000 if you are very '
                     'breathless or drowsy.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('asthma',
  'Asthma',
  None,
  {'goals': 'Keep my asthma symptoms well controlled while using the lowest effective medicine.',
   'measures_text': 'Symptoms; reliever use; night waking; flare-ups.',
   'monitoring': 'Written asthma action plan reviewed; inhaler technique checked.',
   'services': ['Pharmacist (inhaler technique)'],
   'patient_info': 'Use your preventer every day as prescribed, even when you feel well.',
   'safety_netting': "Follow your asthma action plan. Call 000 if your reliever isn't helping or you can't "
                     'speak in sentences.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('osteoarthritis',
  'Osteoarthritis',
  None,
  {'goals': 'Control pain, keep mobile and use medicines safely.',
   'measures_text': 'Pain score; walking distance or a named activity; function.',
   'services': ['Physiotherapist', 'Exercise physiologist', 'Dietitian (if weight is a goal)'],
   'patient_info': 'Osteoarthritis needs some physical and emotional adjustment to the pain and stiffness it '
                   'causes. Pain is often helped by simple measures such as heat, massage and rub-on '
                   'treatments, and by regular gentle exercise. Simple pain relief may help on bad days; '
                   'your GP will advise what suits you.',
   'gp_reference': 'Practice approach (library): regular simple analgesia first, with second-line agents for '
                   'the worst days. Uncontrolled chronic pain is an indication to discuss referral for joint '
                   'replacement.',
   'source_note': "Example wording from a general practice's care-plan library; no medicine names or doses "
                  'in patient text.'}),
 ('rheumatoid_arthritis',
  'Rheumatoid arthritis',
  None,
  {'goals': 'Keep my arthritis well suppressed, as measured by my symptoms and blood tests.',
   'measures_text': 'Symptoms; ESR and CRP as monitored.',
   'monitoring': 'Blood tests at the interval the rheumatologist sets.',
   'services': ['Rheumatologist (as recorded)', 'Physiotherapist', 'Occupational therapist'],
   'patient_info': 'Some arthritis medicines need regular blood tests and must be taken exactly as directed. '
                   'Keep to your blood test schedule.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('gout',
  'Gout',
  None,
  {'goals': 'Prevent further attacks of gout.',
   'measures_text': 'Attacks in the last 6 months; serum urate if the GP monitors it.',
   'patient_info': 'Drink plenty of water and limit alcohol, especially beer. See your GP early in an '
                   'attack.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('osteoporosis',
  'Osteoporosis',
  None,
  {'goals': 'Reduce my risk of fractures.',
   'measures_text': 'Falls in the past year; bone density (date) as the GP sets.',
   'services': ['Physiotherapist or exercise physiologist (strength and balance)'],
   'patient_info': 'Weight-bearing exercise, enough calcium and vitamin D in your diet, and preventing falls '
                   'all help protect your bones. Take your bone medicine exactly as directed.',
   'source_note': "Example wording from a general practice's care plans."}),
 ('skin_cancer',
  'Past skin cancer or solar damage',
  None,
  {'goals': 'Find any new skin cancer early, when it can be treated simply.',
   'measures_text': 'Skin check done (date).',
   'monitoring': 'By recorded history (Red Book): previous melanoma, a skin check at least every 12 months; '
                 'other past skin cancer, an opportunistic check usually no more than once a year; very high '
                 'risk, every 6 months (GP to confirm).',
   'patient_info': 'You have had skin cancer before, a sign of past sun damage, so your risk of new skin '
                   "cancers is higher than average. We'd like to find them as early as possible. At your "
                   'request we can put this on our recall system to remind you.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('medication_management',
  'Medication management',
  None,
  {'goals': 'Take my medicines safely and as prescribed.',
   'measures_text': 'Medicines list reconciled; dose administration aid used, if relevant.',
   'services': ['Pharmacist (home medicines review, dose administration aid)'],
   'patient_info': 'Bring all your medicines, including ones bought without a prescription, to your review.',
   'source_note': "Example wording from a general practice's care-plan library."}),
 ('living_at_home',
  'Living safely at home',
  None,
  {'goals': 'Keep living safely at home.',
   'measures_text': 'Falls; ability to manage named daily tasks; supports in place.',
   'services': ['Occupational therapist',
                'Physiotherapist',
                'Podiatrist',
                'Practice nurse health assessment'],
   'patient_info': 'Help at home can be arranged through My Aged Care if you need it.',
   'source_note': "Example wording from a general practice's care-plan library."})]

PREVENTION = [('bowel',
  'Bowel cancer screening',
  {'age_min': 45, 'age_max': 74, 'flags_none': ['isColonCaPolyps']},
  'A free home bowel screening test every 2 years, ages 45–74 (National Bowel Cancer Screening Program). Not '
  'needed while you are on a colonoscopy program.',
  'Red Book; NBCSP (from 45 since 1 July 2024).'),
 ('breast',
  'Breast screening',
  {'sex': 'F', 'age_min': 50, 'age_max': 74},
  'A mammogram every 2 years through BreastScreen, women aged 50–74.',
  'Red Book.'),
 ('cervical',
  'Cervical screening',
  {'sex': 'F', 'age_min': 25, 'age_max': 74},
  'A cervical screening (HPV) test every 5 years, ages 25–74. You can choose to collect the sample yourself.',
  'Red Book.'),
 ('lung',
  'Lung cancer screening',
  {'age_min': 50, 'age_max': 70, 'needs': 'smoking_history'},
  'You may be eligible for the National Lung Cancer Screening Program (ages 50–70, smoking now or quit in '
  'the last 10 years, at least 30 pack-years): a low-dose CT scan every 2 years. Please discuss it with your '
  'GP.',
  'NLCSP via the Red Book lung topic (from 1 July 2025).'),
 ('prostate',
  'Prostate (PSA) testing: informed choice',
  {'sex': 'M', 'age_min': 50, 'age_max': 69},
  'Men aged 50–69 can discuss the benefits and harms of PSA testing with their GP and decide whether to '
  'test.',
  'Red Book (from 45 with a moderate family history, 40 with a high one; GP to judge).'),
 ('skin',
  'Skin checks by risk',
  {'needs': 'skin_cancer_history'},
  'With a past melanoma, a skin check at least every 12 months; with other past skin cancer, a check about '
  'once a year; your GP will tell you if you need checks more often.',
  'Red Book skin cancer topic.'),
 ('cvd_risk',
  'Heart and stroke risk check',
  {'age_min': 45, 'age_max': 79, 'flags_none': ['isIHD', 'isCVA', 'isVasculopathy', 'isRevascularisation']},
  'A heart and stroke risk check with your GP (Australian CVD risk calculator), usually every 5 years from '
  '45 (from 35 with diabetes, from 30 for Aboriginal and Torres Strait Islander people).',
  'Red Book; CVD 2023.'),
 ('falls',
  'Falls',
  {'age_min': 65},
  'Tell your GP about any falls; a yearly falls check is recommended from 65 (from 50 for Aboriginal and '
  'Torres Strait Islander people).',
  'Red Book falls topic.'),
 ('bones',
  'Bone health',
  {'age_min': 50},
  'From 50, your GP can check your risk of fractures; routine bone density scans are not recommended for '
  'everyone.',
  'Red Book osteoporosis topic.'),
 ('diabetes_risk',
  'Diabetes risk check',
  {'age_min': 40, 'flags_none': ['isDiabetes']},
  'A diabetes risk check (AUSDRISK) every 3 years from 40 (a yearly blood test from 18 for Aboriginal and '
  'Torres Strait Islander people).',
  'Red Book diabetes topic.')]

# measure → the questions the wizard asks: patient groups in order, each with the rule that
# preselects the practice's chosen option for it. The first group whose rule matches decides.
GROUPS = {
    'bp': [
        dict(key='high_risk', label='Diabetes, CKD, or established cardiovascular disease (coronary disease, stroke/TIA, PVD, revascularisation)',
             rule={'any': ['isDiabetes', 'isCKDRecorded'] + ASCVD}),
        dict(key='general', label='Everyone else with hypertension', rule={'always': True}),
    ],
    'ldl': [
        dict(key='ascvd', label='Established atherosclerotic disease (coronary disease or MI, stroke/TIA, PVD, revascularisation)',
             rule={'any': ASCVD}),
        dict(key='high_risk', label='Diabetes, CKD or familial hypercholesterolaemia, without established disease',
             rule={'any': ['isDiabetes', 'isCKDRecorded', 'isFH']}),
        dict(key='general', label='Everyone else (primary prevention)', rule={'always': True}),
    ],
    'hba1c': [dict(key='diabetes', label='Type 2 diabetes', rule={'any': ['isDiabetes']})],
    'home_bgl': [dict(key='monitoring', label='Patients the GP asks to check their glucose at home (never preselected)', rule=None)],
    'alcohol': [dict(key='adults', label='Adults', rule={'always': True})],
    'activity': [dict(key='adults', label='Adults', rule={'always': True})],
}

# measure → guideline-supported options the wizard offers. Citations: (guideline key, section, short quote).
OPTIONS = {
    'bp': [
        dict(code='bp_130_80', label='< 130/80 mmHg', plan_wording='The practice target for your blood pressure is below 130/80.',
             citations=[('racgp_t2d', 'Goals for optimum management', 'Diabetes with CKD: < 130/80 mmHg')]),
        dict(code='bp_140_90', label='< 140/90 mmHg (the GP may set lower)',
             plan_wording='The practice target for your blood pressure is below 140/90; your GP may set a lower one.',
             citations=[('hf_htn2016', 'Treatment targets', '< 140/90 mmHg or lower if tolerated'),
                        ('racgp_t2d', 'Goals for optimum management', 'Generally ≤ 140/90 mmHg')]),
        dict(code='bp_120_sys', label='< 120 mmHg systolic, with close follow-up',
             plan_wording='The practice target for your blood pressure is below 120 systolic, with close follow-up.',
             citations=[('hf_htn2016', 'Treatment targets (selected high-risk patients)',
                         'aiming for a target of < 120 mmHg systolic can improve cardiovascular outcomes')]),
    ],
    'ldl': [
        dict(code='ldl_14_50', label='< 1.4 mmol/L and a reduction of at least 50% from baseline',
             plan_wording='The practice target for your LDL cholesterol is below 1.4 mmol/L, and at least half your starting level.',
             citations=[('acs2025', 'Recovery and secondary prevention',
                         'an initial target LDL-C level of < 1.4 mmol/L and a reduction of at least 50% from baseline'),
                        ('racgp_t2d', 'Summary of recommendations', 'Diabetes with ASCVD: LDL-C < 1.4 mmol/L and ≥ 50% reduction')]),
        dict(code='ldl_18', label='< 1.8 mmol/L (older Australian target)', plan_wording='The practice target for your LDL cholesterol is below 1.8 mmol/L.',
             citations=[('racgp_t2d', 'Goals for optimum management (earlier edition, about 2020)', 'LDL-C < 2.0 (< 1.8 with CVD)')]),
        dict(code='ldl_20', label='< 2.0 mmol/L (earlier RACGP diabetes goal)', plan_wording='The practice target for your LDL cholesterol is below 2.0 mmol/L.',
             citations=[('racgp_t2d', 'Goals for optimum management (earlier edition, about 2020)', 'LDL-C < 2.0 mmol/L')]),
        dict(code='ldl_by_risk', label='No numeric target: the GP decides treatment by five-year CVD risk',
             plan_wording='Your GP will decide your cholesterol treatment from your heart and stroke risk.',
             citations=[('cvd2023', 'Lipid-modifying treatment',
                         'It is uncertain whether treating to a specific, lower, plasma lipid target in primary prevention')]),
    ],
    'hba1c': [
        dict(code='hba1c_7', label='Generally ≤ 7% (53 mmol/mol), individualised by the GP',
             plan_wording="The practice's general aim for your HbA1c is 7% (53 mmol/mol) or less; your GP may set an individual target.",
             citations=[('racgp_t2d', 'Goals for optimum management', 'Generally ≤7% (53 mmol/mol)')]),
    ],
    'home_bgl': [
        dict(code='bgl_racgp', label='Fasting / before meals 4.0–7.0; 2 hours after meals 5.0–10.0 mmol/L',
             plan_wording='If you check your blood glucose at home, aim for 4.0–7.0 mmol/L fasting or before meals and '
                          '5.0–10.0 mmol/L two hours after meals.',
             citations=[('racgp_t2d', 'Self-monitoring of blood glucose', 'fasting and preprandial 4.0–7.0 mmol/L; 2-hour postprandial 5.0–10.0')]),
    ],
    'alcohol': [
        dict(code='alcohol_nhmrc', label='No more than 10 standard drinks a week and no more than 4 on any one day',
             plan_wording='No more than 10 standard drinks a week and no more than 4 on any one day. The less you drink, the lower your risk.',
             citations=[('nhmrc_alcohol', 'Guideline 1', 'no more than 10 standard drinks a week and no more than 4 standard drinks on any one day'),
                        ('redbook', 'Alcohol', 'there is no level of drinking with no risk')]),
    ],
    'activity': [
        dict(code='activity_guidelines', label='150–300 min moderate (or 75–150 vigorous) a week, plus strength on 2+ days',
             plan_wording='Aim for 150 to 300 minutes of moderate activity a week (or 75 to 150 minutes of vigorous activity), '
                          'plus muscle-strengthening activity on at least 2 days. From 65, include balance activities on 3 or more days.',
             citations=[('redbook', 'Physical activity', 'at least 150-300 minutes a week of moderate activity; muscle strengthening on 2 or more days')]),
    ],
    # Individual patients only: offered to the GP, never preselected, no wizard question.
    'uacr': [dict(code='uacr_racgp', label='Women < 3.5 mg/mmol; men < 2.5 mg/mmol', plan_wording='Your target urine albumin-to-creatinine ratio is below {value}.',
                  citations=[('racgp_t2d', 'Goals for optimum management', 'women <3.5 mg/mmol; men <2.5 mg/mmol')])],
    'urate': [dict(code='urate_treat_to_target', label='< 0.36 mmol/L (< 0.30 mmol/L with tophi)', plan_wording='Your target serum urate is below {value}.',
                   citations=[('gout', 'Urate-lowering therapy', 'under 0.36 mmol/L for non-tophaceous gout and under 0.30 mmol/L for tophaceous gout')])],
    'waist': [dict(code='waist_redbook', label='Men < 94 cm; women < 80 cm', plan_wording='Your target waist measurement is below {value}.',
                   citations=[('redbook', 'Overweight and obesity', 'men 94 cm or more increased risk (102 greatly increased); women 80 cm and 88 cm')])],
    'weight': [dict(code='weight_5_10', label='5–10% weight loss', plan_wording='Your goal is to lose 5 to 10% of your body weight.',
                    citations=[('racgp_t2d', 'Goals for optimum management', '5–10% weight loss for people who are overweight or obese')])],
}

# Every protocol measure also gets a "GP sets individually" option (never preselected).
GP_SETS_LABEL = 'GP sets individually'
