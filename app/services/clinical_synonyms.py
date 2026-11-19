"""Clinical synonym groups for progress note text search.

Each frozenset is one equivalence group.  expand_query() takes any user-supplied
search term, finds its group (if any), and returns all terms in that group so
the caller can run an OR search against them.

Spelling: Australian/British forms are primary; US variants included as aliases.
Abbreviations are lowercase; matching is case-insensitive at call sites.
"""

_SYNONYM_GROUPS: list[frozenset[str]] = [
    # Cardiac
    frozenset({"mi", "myocardial infarction", "heart attack", "stemi", "nstemi", "ami",
               "myocardial infarct"}),
    frozenset({"angina", "chest pain", "cp", "cardiac chest", "ischaemic chest",
               "ischemic chest", "chest tightness", "chest discomfort"}),
    frozenset({"ihd", "ischaemic heart disease", "ischemic heart disease",
               "coronary artery disease", "cad", "coronary disease"}),
    frozenset({"ccf", "congestive cardiac failure", "heart failure", "chf",
               "cardiac failure", "lv failure", "lvf", "fluid overload"}),
    frozenset({"af", "atrial fibrillation", "afib", "a-fib", "atrial flutter",
               "flutter", "fast af"}),
    frozenset({"tia", "transient ischaemic attack", "transient ischemic attack",
               "mini stroke", "ministroke"}),
    frozenset({"cva", "stroke", "cerebrovascular accident", "cerebrovascular event"}),
    frozenset({"palpitations", "palpitation", "racing heart", "fast heart", "tachycardia"}),
    frozenset({"hypertension", "htn", "high blood pressure", "raised bp",
               "elevated bp", "raised blood pressure"}),

    # Respiratory
    frozenset({"copd", "chronic obstructive pulmonary disease", "emphysema",
               "chronic bronchitis", "airflow limitation", "airflow obstruction"}),
    frozenset({"asthma", "wheeze", "wheezing", "bronchospasm", "reactive airway"}),
    frozenset({"sob", "shortness of breath", "dyspnoea", "dyspnea",
               "breathlessness", "breathless", "exertional dyspnoea"}),
    frozenset({"pe", "pulmonary embolism", "clot in lung", "lung clot",
               "pulmonary thromboembolism"}),
    frozenset({"pneumonia", "chest infection", "lower respiratory tract infection",
               "lrti", "community acquired pneumonia", "cap"}),

    # Metabolic / Endocrine
    frozenset({"diabetes", "dm", "t2dm", "t1dm", "type 2 diabetes", "type 1 diabetes",
               "type ii diabetes", "type i diabetes", "bsl", "blood sugar",
               "blood glucose", "hyperglycaemia", "hyperglycemia", "hba1c"}),
    frozenset({"hypothyroidism", "underactive thyroid", "low thyroid",
               "tsh elevated", "hashimoto"}),
    frozenset({"hyperthyroidism", "overactive thyroid", "thyrotoxicosis",
               "graves", "graves disease"}),
    frozenset({"cholesterol", "hyperlipidaemia", "hyperlipidemia",
               "dyslipidaemia", "dyslipidemia", "ldl", "hdl", "triglycerides",
               "lipids", "statin", "hypercholesterolaemia"}),
    frozenset({"osteoporosis", "bone density", "dexa", "low bone density",
               "osteopenia", "fracture risk"}),
    frozenset({"obesity", "overweight", "bmi", "weight management", "weight loss"}),
    frozenset({"gout", "hyperuricaemia", "hyperuricemia", "uric acid",
               "gouty arthritis"}),

    # Renal / Urological
    frozenset({"ckd", "chronic kidney disease", "renal failure", "renal impairment",
               "renal insufficiency", "egfr", "renal function", "kidney disease",
               "kidney failure"}),
    frozenset({"uti", "urinary tract infection", "urine infection", "cystitis",
               "pyelonephritis", "dysuria"}),

    # Gastrointestinal
    frozenset({"gord", "gerd", "reflux", "gastro-oesophageal reflux",
               "gastroesophageal reflux", "heartburn", "oesophageal reflux",
               "acid reflux", "indigestion"}),
    frozenset({"ibs", "irritable bowel syndrome", "irritable bowel",
               "functional bowel", "bowel habit change"}),
    frozenset({"ibd", "inflammatory bowel disease", "crohn", "crohns",
               "ulcerative colitis", "colitis"}),

    # Musculoskeletal
    frozenset({"oa", "osteoarthritis", "degenerative joint", "joint arthritis",
               "degenerative arthritis"}),
    frozenset({"ra", "rheumatoid arthritis", "inflammatory arthritis"}),
    frozenset({"back pain", "lbp", "low back pain", "lumbar pain", "lumbar",
               "sciatica", "sciatic", "disc", "prolapsed disc"}),
    frozenset({"knee", "knee pain", "knee replacement", "tkr",
               "total knee replacement", "knee arthroscopy"}),
    frozenset({"shoulder", "shoulder pain", "rotator cuff", "frozen shoulder",
               "adhesive capsulitis", "shoulder impingement"}),
    frozenset({"hip", "hip pain", "hip replacement", "thr",
               "total hip replacement"}),
    frozenset({"fracture", "broken bone", "fracture neck of femur", "fnof",
               "wrist fracture", "colles"}),

    # Neurological / Mental Health
    frozenset({"depression", "mdd", "major depressive disorder", "low mood",
               "depressed", "antidepressant", "ssri"}),
    frozenset({"anxiety", "gad", "generalised anxiety disorder",
               "generalized anxiety", "panic", "panic attack", "panic disorder"}),
    frozenset({"dementia", "cognitive impairment", "cognitive decline",
               "alzheimer", "alzheimers", "memory loss", "mci",
               "mild cognitive impairment"}),
    frozenset({"migraine", "headache", "tension headache", "cluster headache"}),
    frozenset({"epilepsy", "seizure", "seizures", "fits", "convulsion"}),
    frozenset({"parkinson", "parkinsons", "parkinson's disease", "tremor"}),

    # Vascular
    frozenset({"dvt", "deep vein thrombosis", "clot in leg", "leg clot",
               "deep venous thrombosis"}),
    frozenset({"pvd", "peripheral vascular disease", "peripheral arterial disease",
               "pad", "claudication", "intermittent claudication"}),
    frozenset({"varicose veins", "venous insufficiency", "venous ulcer"}),

    # Haematological
    frozenset({"anaemia", "anemia", "low haemoglobin", "low hemoglobin",
               "iron deficiency", "iron deficiency anaemia", "b12 deficiency",
               "folate deficiency"}),
    frozenset({"dvt", "pe", "anticoagul", "warfarin", "dabigatran",
               "rivaroxaban", "apixaban", "clexane", "enoxaparin"}),

    # Infectious / Skin
    frozenset({"cellulitis", "skin infection", "wound infection"}),
    frozenset({"urti", "upper respiratory tract infection", "cold", "flu",
               "influenza", "viral illness", "viral urti", "viral"}),
    frozenset({"covid", "covid-19", "sars-cov-2", "coronavirus"}),

    # Falls / Frailty
    frozenset({"falls", "fall", "collapse", "syncopal", "syncope",
               "near syncope", "loss of consciousness", "loc", "blackout"}),

    # Screening / Preventive
    frozenset({"colonoscopy", "bowel cancer screening", "fobt", "colon cancer"}),
    frozenset({"mammogram", "breast screen", "breast cancer screening"}),
    frozenset({"pap smear", "cervical screen", "cervical cancer screening",
               "liquid based cytology"}),
    frozenset({"prostate", "psa", "prostate cancer", "bph",
               "benign prostatic hypertrophy", "benign prostatic hyperplasia"}),
]

# Flat index: lowercased term → its group.  Built once at import time.
_INDEX: dict[str, frozenset[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _term in _group:
        _INDEX[_term.lower()] = _group


def expand_query(q: str) -> list[str]:
    """Return the synonym group for q if one exists, otherwise [q.lower()].

    The returned list is what the caller ORs across when matching note text.
    """
    q_lower = q.lower().strip()
    group = _INDEX.get(q_lower)
    if group:
        return sorted(group)
    return [q_lower]
