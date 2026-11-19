import datetime
from decimal import Decimal

from flask import current_app

from app.sql.query_loader import ReadOnlySession
from app.repositories.billing_analysis_repository import BillingAnalysisRepository
from app.services.billing_analysis_filters import BILLING_ANALYSIS_FILTERS
from app.services.billing_analysis_criteria import ACTIVE_DAY_CRITERION


class BillingAnalysisService:
    @staticmethod
    def _session() -> ReadOnlySession:
        return ReadOnlySession(current_app.config['BPSDB_URI'])

    @staticmethod
    def get_daily_analysis(start, end, uid: str | None, doctors: list[dict], request_args) -> dict:
        uid_param = int(uid) if uid else None

        extra_sql, extra_params, active_filters = [], [], []
        for f in BILLING_ANALYSIS_FILTERS:
            vals = f.bind(request_args)
            extra_sql.append(f.sql_predicate)
            extra_params.extend(vals)
            if any(v is not None for v in vals):
                active_filters.append(f.key)

        with BillingAnalysisService._session() as sess:
            rows = BillingAnalysisRepository(sess).get_daily_analysis(
                start, end, uid_param, '\n  '.join(extra_sql), extra_params)

        doctor_names = {str(d['bpsdb_userid']): d['full_name'] for d in doctors}
        for row in rows:
            if isinstance(row['service_day'], (datetime.date, datetime.datetime)):
                row['service_day'] = row['service_day'].isoformat()
            if isinstance(row['total_fees'], Decimal):
                row['total_fees'] = float(row['total_fees'])
            row['doctor_name']   = doctor_names.get(str(row['doctor_id']), f"Doctor {row['doctor_id']}")
            row['is_worked_day'] = ACTIVE_DAY_CRITERION.is_worked(row)

        # Practice-wide (or single-doctor, since rows are already SQL-scoped) daily rollup
        daily_totals: dict[str, dict] = {}
        for row in rows:
            agg = daily_totals.setdefault(row['service_day'], {
                'service_day': row['service_day'], 'total_items': 0, 'total_fees': 0.0, 'total_visits': 0})
            agg['total_items']  += row['total_items']
            agg['total_fees']   += row['total_fees']
            agg['total_visits'] += row['total_visits']
        daily_totals = sorted(daily_totals.values(), key=lambda r: r['service_day'])

        # "Worked" days at whatever granularity daily_totals represents (single doctor or
        # practice-wide) — same ACTIVE_DAY_CRITERION, applied uniformly. Totals in the
        # numerator still sum ALL days; only the averaging denominator is restricted to
        # worked days.
        active_days = sum(1 for r in daily_totals if ACTIVE_DAY_CRITERION.is_worked(r))
        summary = {
            'total_fees':   sum(r['total_fees']   for r in daily_totals),
            'total_items':  sum(r['total_items']  for r in daily_totals),
            'total_visits': sum(r['total_visits'] for r in daily_totals),
            'active_days':  active_days,
            'active_day_criterion_label': ACTIVE_DAY_CRITERION.label,
        }
        summary['avg_fees_per_day']   = summary['total_fees']   / active_days if active_days else 0
        summary['avg_items_per_day']  = summary['total_items']  / active_days if active_days else 0
        summary['avg_visits_per_day'] = summary['total_visits'] / active_days if active_days else 0
        summary['fees_per_item']  = summary['total_fees'] / summary['total_items']  if summary['total_items']  else 0
        summary['fees_per_visit'] = summary['total_fees'] / summary['total_visits'] if summary['total_visits'] else 0

        return {
            'detail_rows':    rows,
            'daily_totals':   daily_totals,
            'summary':        summary,
            'chart_labels':   [r['service_day'] for r in daily_totals],
            'chart_values':   [round(r['total_fees'], 2) for r in daily_totals],
            'active_filters': active_filters,
        }
