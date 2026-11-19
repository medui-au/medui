import re
import json
from collections import defaultdict
from decimal import Decimal
from datetime import datetime

from app.sql.query_loader import load_query, ReadOnlySession
from app.utils.bmi import bmi_height

# LOINC code → canonical display name used as the scale key.
# This is the primary mechanism for ensuring range bands appear regardless of
# what text the lab sends for ResultName.
_LOINC_TO_CANONICAL: dict[str, str] = {
    '14749-6': 'Glucose',
    '14647-2': 'Cholesterol- Total',
    '14646-4': 'Cholesterol-HDL',
    '39469-2': 'Cholesterol-LDL',
    '2085-9':  'Cholesterol-HDL',
    '22748-8': 'Cholesterol-LDL',
    '13457-7': 'Cholesterol-LDL',
    '33914-3': 'eGFR',
    '2276-4':  'Ferritin',
    '4548-4':  'HbA1c',
    '17856-6': 'HbA1c NGSP',
    '3016-3':  'TSH',
    '2857-1':  'PSA',
    '1754-1':  'R U-Albumin',
    '14959-1': 'R U-Albumin',
    '29463-7': 'Weight',
    '98491-4': 'FIB4',
}

# Name-level fallback aliases for results without a LOINC code or with an
# unrecognised LOINC (e.g. lab-specific codes like 'AUSLAB^PLT').
_NAME_ALIASES: dict[str, str] = {
    'Total Cholesterol':       'Cholesterol- Total',
    'Serum Cholesterol':       'Cholesterol- Total',
    'Cholesterol (Total)':     'Cholesterol- Total',
    'Cholesterol Total':       'Cholesterol- Total',
    'Cholesterol':             'Cholesterol- Total',
    'Chol.':                   'Cholesterol- Total',
    'HDL':                     'Cholesterol-HDL',
    'HDL Cholesterol':         'Cholesterol-HDL',
    'HDL-Cholesterol':         'Cholesterol-HDL',
    'LDL':                     'Cholesterol-LDL',
    'LDL Cholesterol':         'Cholesterol-LDL',
    'LDL-Cholesterol':         'Cholesterol-LDL',
    'LDL (calculated)':        'Cholesterol-LDL',
    'LDL (atherogenic)':       'Cholesterol-LDL',
    'Glycated Haemoglobin':    'HbA1c',
    'Glycated Hemoglobin':     'HbA1c',
    'Glycohaemoglobin':        'HbA1c',
    'Haemoglobin A1c':         'HbA1c',
    'Hemoglobin A1c':          'HbA1c',
    'Blood HbA1c Fraction':    'HbA1c',
    'HbA1c (NGSP)':            'HbA1c',
    'HbA1c %':                 'HbA1c',
    'HbA1c IFCC':              'HbA1c NGSP',
    'Thyroid Stimulating Hormone': 'TSH',
    'Thyrotropin':             'TSH',
    'Prostate Specific Antigen': 'PSA',
    'Total PSA':               'PSA',
    'Serum Ferritin':          'Ferritin',
    'Serum Ferritin Assay':    'Ferritin',
    'Random Glucose':          'Glucose',
    'Fasting Glucose':         'Glucose',
    'Plasma Glucose':          'Glucose',
    'GFR':                     'eGFR',
    'Urine Albumin':           'R U-Albumin',
    'Random Urine Albumin':    'R U-Albumin',
}


def parse_range_string(range_str: str) -> tuple:
    """Parse a pathology reference range string into (normalMin, normalMax).

    Handles: "3.5-5.5", ">60", "<7", ">=30", "<=330", "0.5 - 4.0", "over 90",
    "under 7", and a trailing note such as ">60/Male" (the note is ignored).
    Returns (None, None) for anything unparseable.
    """
    if not range_str:
        return None, None
    s = range_str.strip().split('/')[0].strip()
    s = re.sub(r'^(?i:over|above)\s+', '>', s)
    s = re.sub(r'^(?i:under|below)\s+', '<', s)
    m = re.match(r'^([+-]?\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(r'^>=?\s*([+-]?\d+(?:\.\d+)?)$', s)
    if m:
        return float(m.group(1)), None
    m = re.match(r'^<=?\s*([+-]?\d+(?:\.\d+)?)$', s)
    if m:
        return None, float(m.group(1))
    return None, None


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _canonical_name(record: dict) -> str:
    # The SQL-resolved name. Name aliases only applied when the SQL CASE didn't
    # produce a recognised canonical name.
    name = str(record.get('ResultName') or '').strip()
    return _NAME_ALIASES.get(name, name)


def _is_percent(record: dict) -> bool:
    return '%' in str(record.get('Units') or record.get('UNITS') or '')


def names_with_percent_and_count(records: list) -> set:
    """Names reported both as a percentage and as a count ("Monocytes" as % and
    as x10*9/L): each kind gets its own chart (ADR-132)."""
    kinds = defaultdict(set)
    for r in records:
        kinds[_canonical_name(r)].add(_is_percent(r))
    return {n for n, k in kinds.items() if len(k) > 1}


def chart_name(record: dict, mixed: set) -> str:
    """The chart a result belongs to: its name, with " (%)" for the percentage
    rows of a name that also has counts."""
    name = _canonical_name(record)
    return f'{name} (%)' if name in mixed and _is_percent(record) else name


class ChartService:
    def __init__(self, bpsdb_uri: str):
        self._uri = bpsdb_uri

    def _query(self, name: str, params=None) -> list:
        with ReadOnlySession(self._uri) as sess:
            return sess.execute(load_query(name), params)

    def get_chart_data(self, patient_id: int) -> dict:
        """Curated chart data — 12 LOINC codes — for the patient charts page."""
        p = patient_id
        path_data   = self._query('patient_charts_pathology', [p, p, p, p])
        fib4_data   = self._query('patient_charts_fib4',      [p, p, p, p, p])
        weight_data = self._query('patient_charts_weight',    [p])
        bp_raw      = self._query('patient_charts_bp',        [p])
        return self._build_chart_data(patient_id, path_data, fib4_data, weight_data, bp_raw)

    def get_pathatom_chart_data(self, patient_id: int) -> dict:
        p = patient_id
        path_data   = self._query('patient_pathatom',      [p, p])
        fib4_data   = self._query('patient_charts_fib4',   [p, p, p, p, p])
        weight_data = self._query('patient_charts_weight', [p])
        bp_raw      = self._query('patient_charts_bp',     [p])
        return self._build_chart_data(patient_id, path_data, fib4_data, weight_data, bp_raw)

    def get_result_history(self, patient_id: int) -> list:
        """Every numeric result, filed and inbox, in one scan (ADR-097). Names and
        codes not yet harmonised: see inbox_outlier_service.harmonise."""
        return self._query('patient_result_history', [patient_id, patient_id])

    def get_pathatom_raw_rows(self, patient_id: int) -> list:
        p = patient_id
        return self._query('patient_pathatom', [p, p])

    def _get_patient_demographics(self, patient_id: int) -> dict:
        from app.services.clinical_service import ClinicalService
        return ClinicalService.get_patient_demographics(patient_id) or {}

    def _build_chart_data(self, patient_id: int, path_data: list, fib4_data: list,
                          weight_data: list, bp_raw: list) -> dict:
        formatted_bp = []
        for rec in bp_raw:
            formatted_bp.append({
                'ResultName': 'Blood Pressure',
                'ResultValue': f"{rec.get('Systolic')}/{rec.get('Diastolic')}",
                'ReportDate': rec.get('ReportDate'),
                'Systolic': rec.get('Systolic'),
                'Diastolic': rec.get('Diastolic'),
            })

        all_data = path_data + fib4_data + weight_data + formatted_bp
        all_data = [r for r in all_data if str(r.get('ResultValue', '')).lower() != 'invalid']

        grouped_data = defaultdict(list)
        range_strings = defaultdict(list)
        mixed = names_with_percent_and_count(all_data)
        for record in all_data:
            result_name = str(record.get('ResultName') or '').strip()
            if not result_name:
                continue
            if result_name.upper() in ('SYSTOLICBP', 'DIASTOLICBP', 'SYSTOLIC BP', 'DIASTOLIC BP'):
                grouped_data['Blood Pressure'].append(record)
                continue
            result_name = chart_name(record, mixed)
            grouped_data[result_name].append(record)
            r = (record.get('Range') or record.get('RANGE') or '').strip()
            if r:
                range_strings[result_name].append((record.get('ReportDate') or datetime.min, r))

        patient = self._get_patient_demographics(patient_id)
        patient_age = patient.get('AGE') if patient else None
        subtitles = self._get_subtitles(patient)
        scales = self._get_chart_scales(patient_age, patient)

        chart_data = {}
        for result_name, records in grouped_data.items():
            records.sort(key=lambda x: x.get('ReportDate') or datetime.min)

            data_points = []
            for rec in records:
                date_val = rec.get('ReportDate')
                value = rec.get('ResultValue')
                if not date_val or value is None:
                    continue
                if result_name == 'Blood Pressure':
                    data_points.append({
                        'x': self._format_date(date_val),
                        'y': rec.get('Systolic'),
                        'yLow': rec.get('Diastolic'),
                        'name': result_name,
                    })
                else:
                    try:
                        data_points.append({
                            'x': self._format_date(date_val),
                            'y': float(value),
                            'name': rec.get('ResultName'),
                        })
                    except (ValueError, TypeError):
                        continue

            if not data_points:
                continue

            subtitle_info = subtitles.get(result_name, {})
            # Axis only from MedUI's per-test settings; the shaded range is the laboratory's,
            # from the most recent result that has one (ADR-105). A range can change over
            # time (PSA with age, for example), so earlier results may have had another.
            axis = scales.get(result_name)
            if not axis:
                sample_loinc = str(
                    records[0].get('LoincCode') or records[0].get('LOINCCODE') or ''
                ).strip()
                if sample_loinc and sample_loinc in _LOINC_TO_CANONICAL:
                    axis = scales.get(_LOINC_TO_CANONICAL[sample_loinc])
            scale = dict(axis) if axis else {'autoScale': True}
            dated = sorted(range_strings.get(result_name, []), key=lambda t: t[0])
            for range_date, range_str in reversed(dated):
                norm_min, norm_max = parse_range_string(range_str)
                if norm_min is not None or norm_max is not None:
                    if norm_min is not None:
                        scale['normalMin'] = norm_min
                    if norm_max is not None:
                        scale['normalMax'] = norm_max
                    subtitle_info = dict(subtitle_info)
                    lines = subtitle_info.get('subtitle') or []
                    lines = [lines] if isinstance(lines, str) else list(lines)
                    lines.append(f"Laboratory's range {range_str} (result of {self._format_date(range_date)})")
                    subtitle_info['subtitle'] = lines
                    break

            chart_data[result_name] = {
                'title': result_name,
                'subtitle': subtitle_info.get('subtitle', ''),
                'units': subtitle_info.get('units', ''),
                'data': data_points,
                'scale': scale,
            }

        return chart_data

    def _get_weight_info(self, patient: dict) -> dict:
        if not patient:
            return {'subtitle': 'Weight data unavailable'}
        weight = patient.get('WEIGHTVALUE')
        height = bmi_height(patient)   # not a childhood height for an adult
        weight_date = patient.get('WEIGHT_DATE')
        if not weight:
            return {'subtitle': 'Weight data unavailable'}
        weight = float(weight)
        if not height:
            date_str = self._format_date(weight_date) if weight_date else 'unknown date'
            reason = ('no height measured from age 18' if patient.get('HEIGHTVALUE')
                      else 'no height recorded')
            return {'subtitle': f"{weight:g} kg on {date_str}; BMI not worked out: {reason}"}
        bmi = weight / (height * height)
        bmi20 = 20 * height * height
        bmi25 = 25 * height * height
        result = {'height': height, 'current_weight': weight, 'ideal_min': bmi20, 'ideal_max': bmi25}
        date_str = self._format_date(weight_date) if weight_date else 'unknown date'
        if weight < bmi20:
            result['subtitle'] = f"{weight:g} kg on {date_str}; height {height}m; BMI {round(bmi)}. BMI 20 to 25 for this height: {round(bmi20)} to {round(bmi25)} kg"
            result['excess'] = -(bmi20 - weight)
        elif weight > bmi25:
            result['subtitle'] = f"{weight:g} kg on {date_str}; height {height}m; BMI {round(bmi)}. BMI 20 to 25 for this height: {round(bmi20)} to {round(bmi25)} kg"
            result['excess'] = weight - bmi25
        else:
            result['subtitle'] = f"{weight:g} kg on {date_str}; height {height}m; BMI {round(bmi)}. BMI 20 to 25 for this height: {round(bmi20)} to {round(bmi25)} kg"
            result['excess'] = 0
        return result

    def _get_chart_scales(self, patient_age, patient: dict) -> dict:
        """Axis settings per test. No ranges or targets (ADR-105): the shaded range is the
        laboratory's, added from the results; practice targets wait for the practice-policy work."""
        return {
            'Glucose':            {'min': 0,   'max': 30,  'autoScale': False},
            'Cholesterol- Total': {'min': 1,   'max': 10,  'autoScale': False},
            'Cholesterol-HDL':    {'min': 0.5, 'max': 2.5, 'autoScale': False},
            'Cholesterol-LDL':    {'min': 1,   'max': 6,   'autoScale': False},
            'eGFR':               {'min': 0,   'max': 95,  'autoScale': False},
            'Ferritin':           {'autoScale': True},
            'HbA1c':              {'min': 4,   'max': 15,  'autoScale': False},
            'HbA1c NGSP':         {'min': 4,   'max': 15,  'autoScale': False},
            'PSA':                {'autoScale': True},
            'TSH':                {'autoScale': True},
            'FIB4':               {'min': 0.5, 'max': 10,  'autoScale': False},
            'R U-Albumin':        {'min': 0,   'max': 80,  'autoScale': False},
            'Blood Pressure':     {'min': 20,  'max': 300, 'autoScale': False},
            'Weight':             {'autoScale': True},
        }

    def _get_subtitles(self, patient: dict) -> dict:
        weight_info = self._get_weight_info(patient)
        return {
            'Glucose':            {'subtitle': 'Glucose',                                           'units': 'mmol/L'},
            'Cholesterol- Total': {'subtitle': 'Total cholesterol',                                 'units': 'mmol/L'},
            'Cholesterol-HDL':    {'subtitle': 'HDL cholesterol',                                   'units': 'mmol/L'},
            'Cholesterol-LDL':    {'subtitle': 'LDL cholesterol',                                   'units': 'mmol/L'},
            'eGFR':               {'subtitle': ['Kidney function',
                                                'KDIGO eGFR categories (reference): G1 >= 90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 < 15'],
                                   'units': 'mL/min/1.73m²'},
            'R U-Albumin':        {'subtitle': ['Urine albumin (units as reported by the laboratory)'], 'units': ''},
            'HbA1c':              {'subtitle': 'HbA1c',                                             'units': '%'},
            'TSH':                {'subtitle': 'Thyroid stimulating hormone',                       'units': 'mIU/L'},
            'PSA':                {'subtitle': 'Prostate specific antigen',                         'units': 'ng/mL'},
            'Ferritin':           {'subtitle': 'Ferritin',                                          'units': 'ng/mL'},
            'FIB4':               {'subtitle': ['FIB-4 = (Age x AST) / (Platelet Count x √(ALT)), calculated by MedUI from the results'], 'units': 'calculated'},
            'Weight':             {'subtitle': [weight_info.get('subtitle', '')],                   'units': 'kg'},
            'Blood Pressure':     {'subtitle': 'Blood pressure',                                    'units': 'mmHg'},
        }

    def _format_date(self, date_value) -> str:
        if isinstance(date_value, datetime):
            return date_value.strftime('%Y-%m-%d')
        if isinstance(date_value, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(date_value, fmt).strftime('%Y-%m-%d')
                except ValueError:
                    continue
            return date_value[:10] if len(date_value) >= 10 else date_value
        return str(date_value)
