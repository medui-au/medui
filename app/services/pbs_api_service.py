"""Thin client for the Australian PBS public API (data-api.health.gov.au/pbs/api/v3).

Only used for brand→generic suggestions when the mapping popup opens.
Never called after a mapping is approved — the stored mapping is used from then on.
"""
import requests
from flask import current_app

PBS_BASE = 'https://data-api.health.gov.au/pbs/api/v3'
_TIMEOUT = 8  # seconds per call

# Maps MIMS DRUGNAME keywords (uppercase) to substrings expected in PBS schedule_form.
# Each tuple: (set of MIMS keywords, set of PBS form substrings to prefer).
# Ordered most-specific first so 'EAR DROPS' matches ear before the generic DROPS rule.
_FORM_MAP = [
    ({'EAR'},                                           {'ear'}),
    ({'EYE', 'OPHTHAL'},                                {'eye', 'ophthalm'}),
    ({'MDI', 'ACCUHALER', 'TURBUHALER', 'HANDIHALER',
      'INHALER', 'ROTAHALER', 'TWISTHALER'},            {'inhaler', 'aerosol', 'inhalation', 'powder for'}),
    ({'NASAL'},                                         {'nasal'}),
    ({'SPRAY'},                                         {'spray'}),
    ({'CREAM'},                                         {'cream'}),
    ({'OINT'},                                          {'ointment'}),
    ({'GEL'},                                           {'gel'}),
    ({'FOAM'},                                          {'foam'}),
    ({'PATCH'},                                         {'patch'}),
    ({'INJ', 'INJECTION'},                              {'injection', 'infusion', 'solution for'}),
    ({'SUPP'},                                          {'suppository'}),
    ({'PESS'},                                          {'pessary'}),
    ({'LOZENGE'},                                       {'lozenge', 'troche'}),
    ({'SYRP', 'SYRUP'},                                 {'syrup', 'oral liquid', 'oral solution'}),
    ({'SUSP'},                                          {'suspension'}),
    ({'DROPS'},                                         {'drops', 'solution'}),
    ({'CAP', 'CAPSULE'},                                {'capsule'}),
    ({'TAB', 'TABLET'},                                 {'tablet'}),
]


def _form_score(mims_name: str, schedule_form: str) -> int:
    """Return the number of PBS form terms that match the MIMS name.

    Higher score = better form match. 0 = no recognised form in MIMS name,
    or no match found in schedule_form.
    """
    words = set(mims_name.upper().split())
    sf = (schedule_form or '').lower()
    for mims_kws, pbs_terms in _FORM_MAP:
        if words & mims_kws:                        # MIMS name contains this form keyword
            if any(t in sf for t in pbs_terms):     # PBS form contains the matching term
                return 1
            return -1                               # form mismatch — penalise
    return 0                                        # no form recognised — neutral


def _name_is_combo(name: str) -> bool:
    """Return True if the drug name indicates a combination product.

    Only `+` is used as a reliable combo indicator in drug names.
    `/` is intentionally ignored: it appears in both combination brand names
    (e.g. dose ratios like "100/50" in Seretide) and dose strings ("150/12.5MG"),
    making it impossible to distinguish reliably from the name string alone.
    """
    return '+' in name


def _best_candidate(candidates: list[dict], mims_name: str) -> dict:
    """Pick the best PBS item from a list of candidates.

    Sorting key: (form_score DESC, drug_name length ASC).
    Form score of -1 means actively wrong form — those are ranked last.
    """
    return max(
        candidates,
        key=lambda i: (
            _form_score(mims_name, i.get('schedule_form', '')),
            -len(i.get('drug_name', '')),
        ),
    )


def _fetch_atc(pbs_code: str, hdrs: dict) -> str | None:
    """Fetch the ATC code for a single PBS item code. Returns None on any failure."""
    try:
        r = requests.get(f'{PBS_BASE}/item-atc-relationships', headers=hdrs,
                         timeout=_TIMEOUT, params={
                             'pbs_code': pbs_code,
                             'get_latest_schedule_only': 'Y',
                             'fields': 'atc_code',
                             'limit': 1,
                         })
        if r.ok and r.text.strip():
            d = r.json().get('data', [])
            if d:
                return d[0].get('atc_code')
    except Exception:
        pass
    return None


def pbs_atc_by_generic(generic_name: str, mims_name: str = '') -> str | None:
    """Look up an ATC code for a known generic name via the PBS drug_name index.

    Used when a mapping already has a generic name but the ATC code was missing
    from the original brand-name lookup. Iterates PBS listings for the generic,
    applying form-matching when mims_name is supplied, and returns the first ATC found.
    """
    key = current_app.config.get('PBS_API_KEY', '')
    if not key or not generic_name:
        return None
    hdrs = {'Subscription-Key': key}
    try:
        r = requests.get(f'{PBS_BASE}/items', headers=hdrs, timeout=_TIMEOUT, params={
            'drug_name': generic_name.strip() + '%',
            'get_latest_schedule_only': 'Y',
            'fields': 'pbs_code,schedule_form',
            'limit': 10,
        })
        if not r.ok or not r.text.strip():
            return None
        items = r.json().get('data', [])
        if not items:
            return None
        # Sort by form score so we try best-matching forms first
        if mims_name:
            items = sorted(items,
                           key=lambda i: -_form_score(mims_name, i.get('schedule_form', '')))
        for item in items:
            pbs_code = item.get('pbs_code')
            if pbs_code:
                atc = _fetch_atc(pbs_code, hdrs)
                if atc:
                    return atc
    except Exception as exc:
        current_app.logger.warning('pbs_atc_by_generic: %s', exc)
    return None


def pbs_suggest(brand_name: str) -> dict:
    """Look up brand_name against the PBS API.

    Returns {'generic_name': str, 'atc_code': str|None, 'pbs_code': str|None}.
    Returns all-empty dict on any failure (rate limit, timeout, not listed, no key).
    """
    empty = {'generic_name': '', 'atc_code': None, 'pbs_code': None}
    key = current_app.config.get('PBS_API_KEY', '')
    if not key or not brand_name:
        return empty

    hdrs = {'Subscription-Key': key}
    prefix = brand_name.strip().split()[0] + '%'
    mims_is_combo = _name_is_combo(brand_name)

    try:
        r = requests.get(f'{PBS_BASE}/items', headers=hdrs, timeout=_TIMEOUT, params={
            'brand_name': prefix,
            'get_latest_schedule_only': 'Y',
            'fields': 'brand_name,drug_name,pbs_code,schedule_form',
            'limit': 5,
        })
        if r.status_code in (204, 429) or not r.ok or not r.text.strip():
            return empty
        items = r.json().get('data', [])
        if not items:
            return empty

        if not mims_is_combo:
            singles = [i for i in items if not _name_is_combo(i.get('drug_name', ''))]
            if not singles:
                # Brand-name search returned only combination products for a single-molecule
                # MIMS name — happens when prescribed by INN (e.g. irbesartan).
                # Fall back to a drug_name search to find single-molecule PBS listings.
                r_dn = requests.get(f'{PBS_BASE}/items', headers=hdrs, timeout=_TIMEOUT,
                                    params={
                                        'drug_name': prefix,
                                        'get_latest_schedule_only': 'Y',
                                        'fields': 'brand_name,drug_name,pbs_code,schedule_form',
                                        'limit': 5,
                                    })
                if r_dn.ok and r_dn.text.strip():
                    dn_items = r_dn.json().get('data', [])
                    singles = [i for i in dn_items
                               if not _name_is_combo(i.get('drug_name', ''))]
            candidates = singles if singles else items
        else:
            candidates = items

        best      = _best_candidate(candidates, brand_name)
        drug_name = best.get('drug_name', '')
        pbs_code  = best.get('pbs_code')

        atc = _fetch_atc(pbs_code, hdrs) if pbs_code else None
        return {'generic_name': drug_name, 'atc_code': atc, 'pbs_code': pbs_code}

    except Exception as exc:
        current_app.logger.warning('pbs_suggest: %s', exc)
        return empty
