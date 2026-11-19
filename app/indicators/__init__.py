from app.indicators import (
    diagnosis_data_quality,
    immunisation_activity,
    inbox_results,
    medication_housekeeping,
    observation_entry_counts,
)
from app.indicators.base import (
    CHART_BAR,
    CHART_CATEGORY_TOTALS,
    CHART_STACKED_BAR,
    ChartSpec,
    Column,
    Indicator,
)

__all__ = [
    'get_registry', 'Indicator', 'Column', 'ChartSpec',
    'CHART_BAR', 'CHART_STACKED_BAR', 'CHART_CATEGORY_TOTALS',
]


def _build_immunisation_indicator() -> Indicator:
    # Category columns/segments are derived from the mapdata_vaccine_mapping
    # table at request time (see app/indicators/immunisation_activity.py) —
    # this indicator can't be a static module-level Indicator like the other
    # four, since building its columns/charts requires a DB query.
    categories = immunisation_activity.all_categories()
    keys = immunisation_activity.category_keys()
    category_columns = [Column(keys[c], c, always_show_tile=False) for c in categories]
    category_segments = [(keys[c], c) for c in categories]

    return Indicator(
        key='immunisation_activity',
        label='Immunisations',
        description=(
            'Immunisation activity per doctor — total doses given, distinct '
            'patients vaccinated, age at vaccination, and disease-category mix.'
        ),
        compute=immunisation_activity.compute,
        columns=[
            Column('total', 'Total'),
            Column('patients', 'Patients'),
            Column('age_lt_18', '<18'),
            Column('age_19_50', '19-50'),
            Column('age_51_plus', '51+'),
            *category_columns,
        ],
        charts=[
            ChartSpec(key='total', label='Total Doses', kind=CHART_BAR, metric='total'),
            ChartSpec(key='patients', label='Patients', kind=CHART_BAR, metric='patients'),
            ChartSpec(
                key='age', label='Age at Vaccination', kind=CHART_STACKED_BAR,
                segments=[
                    ('age_lt_18', '<18'), ('age_19_50', '19-50'), ('age_51_plus', '51+'),
                ],
            ),
            ChartSpec(
                key='category_by_doctor', label='Category (by doctor)', kind=CHART_STACKED_BAR,
                segments=category_segments,
            ),
            ChartSpec(
                key='category_practice', label='Category (practice-wide)',
                kind=CHART_CATEGORY_TOTALS,
                segments=category_segments,
            ),
        ],
        rationale=(
            'Total doses, patients vaccinated, and the age/category breakdown of '
            'what you administered. Every number here scales with how many '
            'immunisation-eligible consultations you had — itself a function of '
            'list size, FTE and sub-specialty focus — so treat this as workload '
            'context, not a comparative performance measure, until it can be '
            'expressed as a rate against eligible encounters.'
        ),
    )


def get_registry() -> dict[str, Indicator]:
    """Build the indicator registry. A function (not a module-level constant)
    because the immunisation indicator's columns/charts depend on a DB query
    (mapdata_vaccine_mapping) that needs an app/request context — see
    _build_immunisation_indicator. Cheap to call per-request: four of the
    five indicators are static, and the immunisation one caches its DB
    lookup for 5 minutes (app/indicators/immunisation_activity.py).

    To add a new indicator: write a module with a
    `compute(start_date, end_date) -> list[dict]` function, then add an
    entry here. Nothing else (routes, template) needs to change.
    """
    return {
        'observation_entry_counts': Indicator(
            key='observation_entry_counts',
            label='Vital Sign Entries',
            description=(
                'Count of systolic, diastolic, height and weight observations '
                'entered per doctor — data-quality context for AI-assisted features.'
            ),
            compute=observation_entry_counts.compute,
            columns=[
                Column('systolic', 'Systolic'),
                Column('diastolic', 'Diastolic'),
                Column('height', 'Height'),
                Column('weight', 'Weight'),
                Column('total', 'Total'),
            ],
            charts=[
                ChartSpec(key='total', label='Total Entries', kind=CHART_BAR, metric='total'),
            ],
            rationale=(
                'This counts how many systolic, diastolic, height and weight '
                'readings you recorded in the period. It’s workload-linked — a '
                'busier list naturally produces more entries — so treat it as '
                'data-quality context rather than a performance score. It shows '
                'whether vitals were recorded, not whether they were clinically '
                'indicated at the time.'
            ),
        ),
        'inbox_results': Indicator(
            key='inbox_results',
            label='Inbox Results',
            description=(
                'Pending (unfiled) results per doctor — how many patients and '
                'items are waiting, and how long they’ve sat unactioned.'
            ),
            compute=inbox_results.compute,
            uses_period_filter=False,
            columns=[
                Column('patients', 'Patients'),
                Column('total', 'Results'),
                Column('age_lt_3m', '<3m'),
                Column('age_3_6m', '3-6m'),
                Column('age_6_9m', '6-9m'),
                Column('age_9_12m', '9-12m'),
                Column('age_gt_12m', '>12m'),
            ],
            charts=[
                ChartSpec(key='total', label='Total Results', kind=CHART_BAR, metric='total'),
                ChartSpec(key='patients', label='Patients', kind=CHART_BAR, metric='patients'),
                ChartSpec(
                    key='age', label='Age Distribution', kind=CHART_STACKED_BAR,
                    segments=[
                        ('age_lt_3m', '<3m'),
                        ('age_3_6m', '3-6m'),
                        ('age_6_9m', '6-9m'),
                        ('age_9_12m', '9-12m'),
                        ('age_gt_12m', '>12m'),
                    ],
                ),
            ],
            rationale=(
                'A live snapshot of your unfiled results, broken down by how long '
                'each has been waiting. The total count is influenced by list '
                'size, but the age breakdown — especially anything over 12 months '
                '— is a genuine timeliness signal: a result unfiled for a year is '
                'a patient-safety-relevant gap regardless of how busy your list is.'
            ),
        ),
        'diagnosis_data_quality': Indicator(
            key='diagnosis_data_quality',
            label='Diagnosis Data Quality',
            description=(
                'Diagnosis (PastHistory) housekeeping per doctor — how many were '
                'created, edited, or deleted, and how many have a coded item '
                'and/or clarifying detail rather than free text alone.'
            ),
            compute=diagnosis_data_quality.compute,
            columns=[
                Column('created', 'Created'),
                Column('updated', 'Updated'),
                Column('deleted', 'Deleted'),
                Column('total_activity', 'Created + Updated'),
                Column('created_with_itemcode', 'With Item Code'),
                Column('pct_itemcode', '% With Item Code', summable=False),
                Column('created_with_details', 'With Details'),
            ],
            charts=[
                ChartSpec(
                    key='total_activity', label='Created + Updated',
                    kind=CHART_BAR, metric='total_activity',
                ),
                ChartSpec(
                    key='pct_itemcode', label='% With Item Code',
                    kind=CHART_BAR, metric='pct_itemcode',
                ),
                ChartSpec(
                    key='with_details', label='With Details',
                    kind=CHART_BAR, metric='created_with_details',
                ),
                ChartSpec(
                    key='breakdown', label='Created vs Updated vs Deleted', kind=CHART_STACKED_BAR,
                    segments=[('created', 'Created'), ('updated', 'Updated'), ('deleted', 'Deleted')],
                ),
            ],
            rationale=(
                'Tracks diagnoses created, edited or deleted, and of those '
                'created, how many carry a coded item versus free text alone. '
                'The raw counts reflect documentation volume (confounded by '
                'consultation load); % With Item Code is the stronger signal — '
                'coding a diagnosis instead of leaving it free text is a '
                'structured-data habit that’s genuinely comparable regardless of '
                'list size.'
            ),
        ),
        'medication_housekeeping': Indicator(
            key='medication_housekeeping',
            label='Medication Housekeeping',
            description=(
                'Medication list maintenance per doctor — how many prescriptions '
                'were created vs medications ceased, and how many cessations '
                'documented a reason rather than a silent removal.'
            ),
            compute=medication_housekeeping.compute,
            columns=[
                Column('created', 'Created'),
                Column('ceased', 'Ceased'),
                Column('pct_ceased', '% Ceased of Created', summable=False),
                Column('ceased_with_reason', 'Ceased With Reason'),
                Column('pct_reason', '% Ceased With Reason', summable=False),
            ],
            charts=[
                ChartSpec(key='ceased', label='Ceased', kind=CHART_BAR, metric='ceased'),
                ChartSpec(
                    key='pct_ceased', label='% Ceased of Created',
                    kind=CHART_BAR, metric='pct_ceased',
                ),
                ChartSpec(
                    key='pct_reason', label='% Ceased With Reason',
                    kind=CHART_BAR, metric='pct_reason',
                ),
                ChartSpec(
                    key='breakdown', label='Created vs Ceased', kind=CHART_STACKED_BAR,
                    segments=[('created', 'Created'), ('ceased', 'Ceased')],
                ),
            ],
            rationale=(
                'Prescriptions created versus medications ceased, and how many '
                'cessations recorded a reason. % Ceased of Created is a rough '
                'list-maintenance ratio, not a same-drug conversion rate. '
                '% Ceased With Reason is the stronger signal: documenting why a '
                'medication was stopped, rather than a silent removal, is a '
                'genuine continuity-of-care habit.'
            ),
        ),
        'immunisation_activity': _build_immunisation_indicator(),
    }
