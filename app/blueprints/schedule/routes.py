from datetime import datetime

from flask import redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from . import bp
from app.services.schedule_service import ScheduleService


@bp.get('/')
@login_required
def index():
    return redirect(url_for('schedule.daysheet'))


@bp.get('/daysheet')
@login_required
def daysheet():
    date_str = request.args.get('date', '').strip()
    is_today = False

    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
            is_today = (target_date.date() == datetime.now().date())
        except ValueError:
            current_app.logger.warning(
                'schedule.daysheet received invalid date %r — defaulting to today', date_str
            )
            target_date = datetime.now()
            is_today = True
    else:
        target_date = datetime.now()
        is_today = True

    iso_date = target_date.strftime('%Y-%m-%d')
    bpsdb_userid = str(current_user.bpsdb_user_id or '') if hasattr(current_user, 'bpsdb_user_id') else ''

    try:
        appointments = ScheduleService.get_appointments(iso_date)
    except Exception as e:
        current_app.logger.error('schedule appointments error for %s: %s', iso_date, e)
        appointments = []

    try:
        daysheet_data = ScheduleService.get_daysheet(iso_date)
    except Exception as e:
        current_app.logger.error('schedule daysheet error for %s: %s', iso_date, e)
        daysheet_data = []

    # Build provider list from both datasets for the filter chips
    providers: dict[str, str] = {}
    for row in appointments:
        pid = str(row.get('provider_id', ''))
        if pid and pid not in providers:
            providers[pid] = row.get('Provider', '??')
    for row in daysheet_data:
        pid = str(row.get('provider_id', ''))
        if pid and pid not in providers:
            providers[pid] = row.get('UserName', '??')

    providers_list = sorted(
        [{'id': pid, 'initials': initials} for pid, initials in providers.items()],
        key=lambda x: x['initials'],
    )

    return render_template(
        'schedule/daysheet.html',
        appointments=appointments,
        daysheet=daysheet_data,
        target_date=target_date,
        iso_date=iso_date,
        is_today=is_today,
        providers=providers_list,
        bpsdb_userid=bpsdb_userid,
    )


@bp.get('/api/appointments')
@login_required
def api_appointments():
    iso_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d')).strip()
    bpsdb_userid = str(current_user.bpsdb_user_id or '') if hasattr(current_user, 'bpsdb_user_id') else ''

    try:
        rows = ScheduleService.get_appointments(iso_date)
    except Exception as e:
        current_app.logger.error('api_appointments error for %s: %s', iso_date, e)
        rows = []

    return render_template(
        'schedule/partials/appointments_table.html',
        rows=rows,
        bpsdb_userid=bpsdb_userid,
    )


@bp.get('/api/daysheet')
@login_required
def api_daysheet():
    iso_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d')).strip()
    bpsdb_userid = str(current_user.bpsdb_user_id or '') if hasattr(current_user, 'bpsdb_user_id') else ''

    try:
        rows = ScheduleService.get_daysheet(iso_date)
    except Exception as e:
        current_app.logger.error('api_daysheet error for %s: %s', iso_date, e)
        rows = []

    return render_template(
        'schedule/partials/daysheet_table.html',
        rows=rows,
        bpsdb_userid=bpsdb_userid,
    )
