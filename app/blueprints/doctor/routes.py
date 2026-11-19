import json
import re as _re
import threading
from datetime import date, datetime, timedelta, timezone

from flask import render_template, request, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user

from . import bp
from app.sql.query_loader import load_query, ReadOnlySession
from flask import current_app


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _bpsdb():
    return ReadOnlySession(current_app.config['BPSDB_URI'])


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _resolve_period(args: dict) -> tuple[date, date, str]:
    """Parse period/date_from/date_to from request args. Default: 'today'."""
    period = args.get('period', 'today')
    today  = date.today()

    if period == 'today':
        return today, today, period
    elif period == '2days':
        return today - timedelta(days=1), today, period
    elif period == '7days':
        return today - timedelta(days=6), today, period
    elif period == 'month':
        return today.replace(day=1), today, period
    elif period == 'last_month':
        first_this = today.replace(day=1)
        last_prev  = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev, period
    elif period == 'year':
        return today.replace(month=1, day=1), today, period
    elif period == 'last_year':
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31), period
    elif period == 'custom':
        try:
            start = date.fromisoformat(args.get('date_from', ''))
            end   = date.fromisoformat(args.get('date_to',   ''))
            return start, end, period
        except (ValueError, TypeError):
            pass

    return today, today, 'today'


def _doctor_context() -> tuple[int | None, str, list[dict]]:
    """Resolve active bpsdb_user_id, display name, and doctors list.

    Non-admins: fixed to their own bpsdb_user_id.
    Admins:     may select any doctor via ?doctor_id=; None means all doctors.

    Returns: (bpsdb_user_id, display_name, doctors_list)
    """
    is_admin = current_user.is_admin

    if is_admin:
        doctors = []
        try:
            with _bpsdb() as sess:
                from app.services import practitioner_names
                doctors = practitioner_names.swap(sess.execute(load_query('doctor_all_doctors')),
                                                  'bpsdb_userid', 'full_name')
        except Exception as exc:
            current_app.logger.warning('doctor: get_all_doctors failed: %s', exc)

        selected_id = request.args.get('doctor_id') or None
        if selected_id:
            match   = next((d for d in doctors if str(d['bpsdb_userid']) == str(selected_id)), None)
            display = f"Dr {match['full_name']}" if match else 'Unknown Doctor'
        else:
            display = 'All Doctors'
        return selected_id, display, doctors, is_admin
    else:
        uid     = current_user.bpsdb_user_id
        display = f"Dr {current_user.display_name or current_user.username}"
        return uid, display, [], is_admin


# ── Billings ───────────────────────────────────────────────────────────────────

@bp.get('/billings')
@login_required
def billings():
    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'today'
    start, end, period = _resolve_period(args)
    uid, display_name, doctors, is_admin = _doctor_context()

    uid_param = int(uid) if uid is not None else None
    params    = [start, end, uid_param, uid_param]

    summary = {'total_fees': 0, 'total_items': 0, 'total_visits': 0}
    items   = []
    try:
        with _bpsdb() as sess:
            rows = sess.execute(load_query('doctor_billings_summary'), params)
            if rows:
                summary = rows[0]
            items = sess.execute(load_query('doctor_billings_items'), params)
    except Exception as exc:
        current_app.logger.warning('doctor.billings query failed: %s', exc)

    return render_template(
        'doctor/billings.html',
        start_date=start,
        end_date=end,
        period=period,
        display_name=display_name,
        doctors=doctors,
        selected_doctor_id=request.args.get('doctor_id', ''),
        is_admin=is_admin,
        summary=summary,
        items=items,
    )


# ── Billing Analysis (admin-only) ───────────────────────────────────────────────

@bp.get('/billing-analysis')
@login_required
@_require_admin
def billing_analysis():
    from app.services.billing_analysis_service import BillingAnalysisService
    from app.services.billing_analysis_filters import BILLING_ANALYSIS_FILTERS
    from app.services.doctor_profile_service import DoctorProfileService

    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'month'
    start, end, period = _resolve_period(args)
    uid, display_name, doctors, is_admin = _doctor_context()

    try:
        data = BillingAnalysisService.get_daily_analysis(start, end, uid, doctors, request.args)
    except Exception as exc:
        current_app.logger.warning('doctor.billing_analysis query failed: %s', exc)
        data = {'detail_rows': [], 'daily_totals': [], 'summary': {},
                'chart_labels': [], 'chart_values': [], 'active_filters': []}

    doctor_profile = None
    if uid:
        try:
            doctor_profile = DoctorProfileService.get_profile(int(uid))
        except Exception as exc:
            current_app.logger.warning('doctor.billing_analysis profile lookup failed: %s', exc)

    return render_template(
        'doctor/billing_analysis.html',
        start_date=start, end_date=end, period=period,
        display_name=display_name, doctors=doctors,
        selected_doctor_id=request.args.get('doctor_id', ''),
        is_admin=is_admin,
        filter_defs=BILLING_ANALYSIS_FILTERS,
        chart_data_json=json.dumps({'labels': data['chart_labels'], 'values': data['chart_values']}),
        doctor_profile=doctor_profile,
        **data,
    )


# ── Progress Notes ─────────────────────────────────────────────────────────────

def _strip_rtf(text: str) -> str:
    if not text:
        return ''
    s = str(text)
    if s.strip().startswith('{\\rtf'):
        try:
            from striprtf.striprtf import rtf_to_text
            s = rtf_to_text(s)
            s = _re.sub(r'\n{3,}', '\n\n', s)
            return s.strip()
        except Exception:
            pass
    s = _re.sub(r'\{\\[^}]*\}', '', s)
    s = _re.sub(r'\\[a-z]+\-?\d*\s?', '', s)
    return s.strip()


@bp.get('/progress-notes')
@login_required
def progress_notes():
    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'today'
    start, end, period = _resolve_period(args)
    uid, display_name, doctors, is_admin = _doctor_context()

    search_raw = request.args.get('search', '').strip()
    uid_param    = int(uid) if uid is not None else None
    search_param = f'%{search_raw}%' if search_raw else None
    params       = [start, end, uid_param, uid_param, search_param, search_param]

    notes = []
    limit_reached = False
    try:
        with _bpsdb() as sess:
            rows = sess.execute(load_query('doctor_progress_notes'), params)
            for row in rows:
                row = dict(row)
                row['visit_notes'] = _strip_rtf(row.get('visit_notes') or '')
                notes.append(row)
        limit_reached = len(notes) >= 200
    except Exception as exc:
        current_app.logger.warning('doctor.progress_notes query failed: %s', exc)

    return render_template(
        'doctor/progress_notes.html',
        start_date=start,
        end_date=end,
        period=period,
        display_name=display_name,
        doctors=doctors,
        selected_doctor_id=request.args.get('doctor_id', ''),
        is_admin=is_admin,
        search=search_raw,
        notes=notes,
        limit_reached=limit_reached,
    )


# ── Quality ─────────────────────────────────────────────────────────────────────

# ── Criterion review (ADR-109) ────────────────────────────────────────────────

@bp.get('/criterion-review')
@login_required
def criterion_review():
    """Results meeting a diagnostic criterion where the diagnosis isn't recorded. A doctor sees
    the patients whose last visit was with them; an administrator sees all, or one doctor's."""
    import pyodbc
    from flask import abort
    from app.services import criterion_review_service
    if not current_user.has_level(5):
        abort(403)
    if not criterion_review_service.enabled():
        abort(404)
    uid, display_name, doctors, is_admin = _doctor_context()
    try:
        data, error = criterion_review_service.load(), None
    except pyodbc.Error as exc:                   # BPSDB unreachable: show, don't 500
        current_app.logger.error('criterion review: %s', exc)
        data, error = {'diabetes': [], 'ckd': [], 'cohort': 0, 'recorded': {'diabetes': 0, 'ckd': 0}}, str(exc)
    if uid or not is_admin:
        mine = lambda rows: [r for r in rows if uid and str(r.get('last_doctor_id')) == str(uid)]
        data['diabetes'], data['ckd'] = mine(data['diabetes']), mine(data['ckd'])
    return render_template('doctor/criterion_review.html', error=error, doctors=doctors,
                           selected_doctor_id=uid if is_admin else None, display_name=display_name,
                           is_admin=is_admin, **data)


@bp.get('/quality')
@login_required
def quality():
    from app.indicators import get_registry
    from app.services import quality_service

    registry = get_registry()
    indicator_key = request.args.get('indicator')
    if indicator_key not in registry:
        indicator_key = next(iter(registry))
    indicator = registry[indicator_key]

    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'month'
    start, end, period = _resolve_period(args)
    uid, display_name, doctors, is_admin = _doctor_context()

    # Admin with no doctor selected sees every doctor (table + chart);
    # admin with a doctor selected, or any non-admin, sees only that one
    # doctor's row — never another doctor's data, per the access model in
    # plans/decisions.md.
    show_table = is_admin and uid is None
    target_uid = int(uid) if uid is not None else current_user.bpsdb_user_id

    rows: list[dict] = []
    error = None
    try:
        rows = indicator.compute(start, end)
    except Exception as exc:
        current_app.logger.warning('doctor.quality (%s) query failed: %s', indicator_key, exc)
        error = 'Could not reach the practice database.'

    rows_for_view = rows if show_table else [r for r in rows if r.get('bpsdb_userid') == target_uid]

    charts_by_key = {c.key: c for c in indicator.charts}
    chart_key = request.args.get('chart')
    if chart_key not in charts_by_key:
        chart_key = indicator.charts[0].key if indicator.charts else None
    # Everyone gets a chart, built from every doctor's row (not just their
    # own) — admins see it named, everyone else sees it anonymised (own bar
    # highlighted, colleagues' names withheld). See quality_service.build_chart.
    chart = (
        quality_service.build_chart(
            charts_by_key[chart_key], rows,
            anonymize=not show_table, mine_userid=current_user.bpsdb_user_id,
        )
        if (chart_key and rows) else None
    )
    totals_row = quality_service.build_totals_row(indicator, rows) if show_table else None

    return render_template(
        'doctor/quality.html',
        indicators_nav=[
            {'key': k, 'label': v.label, 'active': k == indicator_key}
            for k, v in registry.items()
        ],
        indicator=indicator,
        rows=rows_for_view,
        totals_row=totals_row,
        show_table=show_table,
        chart=chart,
        chart_key=chart_key,
        start_date=start,
        end_date=end,
        period=period,
        display_name=display_name,
        doctors=doctors,
        selected_doctor_id=request.args.get('doctor_id', ''),
        is_admin=is_admin,
        error=error,
    )


@bp.get('/quality/report')
@login_required
def quality_report():
    """Printable/downloadable slide stack: every indicator, one slide each,
    for whichever single doctor is currently in view on the Quality page
    (see quality() above — same target_uid resolution, same access model:
    a non-admin always gets their own data regardless of any doctor_id
    passed in, an admin gets whichever doctor they'd drilled into)."""
    from app.indicators import get_registry
    from app.services import quality_service

    registry = get_registry()

    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'month'
    start, end, period = _resolve_period(args)
    uid, display_name, _doctors, is_admin = _doctor_context()
    target_uid = int(uid) if uid is not None else current_user.bpsdb_user_id
    if uid is None:
        # _doctor_context() labels a doctor-id-less admin request "All
        # Doctors" (correct for the main table view) — this report is
        # always single-subject, so if an admin somehow reaches it with no
        # doctor_id (the on-page button always includes one), label it as
        # their own report instead of the misleading "All Doctors".
        display_name = f"Dr {current_user.display_name or current_user.username}"

    slides = []
    for indicator in registry.values():
        try:
            rows = indicator.compute(start, end)
        except Exception as exc:
            current_app.logger.warning(
                'doctor.quality_report (%s) query failed: %s', indicator.key, exc
            )
            slides.append({'indicator': indicator, 'row': None, 'charts': [], 'error': True})
            continue

        row = next((r for r in rows if r.get('bpsdb_userid') == target_uid), None)
        # Every chart variant the indicator offers (its on-page tab toggle),
        # not just the default one — a report is a standalone document with
        # no toggle to click, so it includes them all.
        charts = [
            {
                'label': spec.label,
                'data': quality_service.build_chart(
                    spec, rows, anonymize=True, mine_userid=target_uid,
                ),
            }
            for spec in indicator.charts
        ] if rows else []
        slides.append({'indicator': indicator, 'row': row, 'charts': charts, 'error': False})

    return render_template(
        'doctor/quality_report.html',
        slides=slides,
        display_name=display_name,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(),
    )


# ── Stubs (to be implemented) ──────────────────────────────────────────────────

@bp.get('/')
@login_required
def index():
    return render_template('stub.html', page_title='Doctor Data')


@bp.get('/transcripts')
@login_required
def transcripts():
    from app.models.consultation_transcript import ConsultationTranscript
    from app.models.user import User
    from app.extensions import db

    is_admin = current_user.is_admin

    try:
        filter_start = date.fromisoformat(request.args.get('start_date', ''))
    except (ValueError, TypeError):
        filter_start = date.today()
    try:
        filter_end = date.fromisoformat(request.args.get('end_date', ''))
    except (ValueError, TypeError):
        filter_end = date.today()

    filter_patient_id = request.args.get('patient_id') or None

    # Convert local (Brisbane) date boundaries to naive-UTC for DB comparison.
    # Stored timestamps are naive UTC; using db.func.date() would compare the
    # UTC date, which is wrong for dates near midnight in AEST (UTC+10).
    from zoneinfo import ZoneInfo
    _tz = ZoneInfo(current_app.config.get('PRACTICE_TIMEZONE', 'Australia/Brisbane'))
    _start_utc = (datetime(filter_start.year, filter_start.month, filter_start.day,
                           0, 0, 0, tzinfo=_tz)
                  .astimezone(timezone.utc).replace(tzinfo=None))
    _end_utc   = (datetime(filter_end.year, filter_end.month, filter_end.day,
                           23, 59, 59, 999999, tzinfo=_tz)
                  .astimezone(timezone.utc).replace(tzinfo=None))

    q = ConsultationTranscript.query.filter(
        ConsultationTranscript.created_at >= _start_utc,
        ConsultationTranscript.created_at <= _end_utc,
    )

    if is_admin:
        filter_user_id = request.args.get('doctor_id') or None
        if filter_user_id:
            q = q.filter(ConsultationTranscript.user_id == int(filter_user_id))
        doctor_user_ids = [
            r[0] for r in db.session.query(ConsultationTranscript.user_id).distinct().all()
            if r[0]
        ]
        doctor_users = User.query.filter(User.id.in_(doctor_user_ids)).all() if doctor_user_ids else []
    else:
        filter_user_id = None
        doctor_users   = []
        q = q.filter(ConsultationTranscript.user_id == current_user.id)

    if filter_patient_id:
        q = q.filter(ConsultationTranscript.patient_id == int(filter_patient_id))

    transcript_rows = q.order_by(ConsultationTranscript.created_at.desc()).all()

    patient_ids   = list({t.patient_id for t in transcript_rows if t.patient_id})
    patient_names = {}
    if patient_ids:
        try:
            id_list = ','.join(str(int(i)) for i in patient_ids)
            sql = (
                f"SELECT InternalId, TRIM(Firstname) + ' ' + TRIM(Surname) AS full_name"
                f" FROM PATIENTS WHERE InternalId IN ({id_list})"
            )
            with _bpsdb() as sess:
                for row in sess.execute(sql):
                    patient_names[row['InternalId']] = row['full_name']
        except Exception as exc:
            current_app.logger.warning('doctor.transcripts: patient name lookup failed: %s', exc)

    patient_options = [
        {'patient_id': pid, 'name': patient_names.get(pid, f'Patient {pid}')}
        for pid in sorted(patient_ids)
    ]

    return render_template(
        'doctor/transcripts.html',
        transcripts=transcript_rows,
        patient_names=patient_names,
        patient_options=patient_options,
        doctor_users=doctor_users,
        filter_start=filter_start,
        filter_end=filter_end,
        filter_user_id=filter_user_id or '',
        filter_patient_id=filter_patient_id or '',
        is_admin=is_admin,
    )


@bp.get('/chats')
@login_required
def chats():
    from app.models.chat import ChatSession
    from app.models.user import User
    from app.extensions import db

    is_admin = current_user.is_admin

    try:
        filter_start = date.fromisoformat(request.args.get('start_date', ''))
    except (ValueError, TypeError):
        filter_start = date.today()
    try:
        filter_end = date.fromisoformat(request.args.get('end_date', ''))
    except (ValueError, TypeError):
        filter_end = date.today()

    filter_patient_id = request.args.get('patient_id') or None

    # Convert local (Brisbane) date boundaries to naive-UTC for DB comparison —
    # same rationale as doctor.transcripts (stored timestamps are naive UTC).
    from zoneinfo import ZoneInfo
    _tz = ZoneInfo(current_app.config.get('PRACTICE_TIMEZONE', 'Australia/Brisbane'))
    _start_utc = (datetime(filter_start.year, filter_start.month, filter_start.day,
                           0, 0, 0, tzinfo=_tz)
                  .astimezone(timezone.utc).replace(tzinfo=None))
    _end_utc   = (datetime(filter_end.year, filter_end.month, filter_end.day,
                           23, 59, 59, 999999, tzinfo=_tz)
                  .astimezone(timezone.utc).replace(tzinfo=None))

    q = ChatSession.query.filter(
        ChatSession.created_at >= _start_utc,
        ChatSession.created_at <= _end_utc,
    )

    if is_admin:
        filter_user_id = request.args.get('doctor_id') or None
        if filter_user_id:
            q = q.filter(ChatSession.user_id == int(filter_user_id))
        doctor_user_ids = [
            r[0] for r in db.session.query(ChatSession.user_id).distinct().all()
            if r[0]
        ]
        doctor_users = User.query.filter(User.id.in_(doctor_user_ids)).all() if doctor_user_ids else []
    else:
        filter_user_id = None
        doctor_users   = []
        q = q.filter(ChatSession.user_id == current_user.id)

    if filter_patient_id:
        q = q.filter(ChatSession.patient_id == int(filter_patient_id))

    session_rows = q.order_by(ChatSession.created_at.desc()).all()

    patient_ids   = list({s.patient_id for s in session_rows if s.patient_id})
    patient_names = {}
    if patient_ids:
        try:
            id_list = ','.join(str(int(i)) for i in patient_ids)
            sql = (
                f"SELECT InternalId, TRIM(Firstname) + ' ' + TRIM(Surname) AS full_name"
                f" FROM PATIENTS WHERE InternalId IN ({id_list})"
            )
            with _bpsdb() as sess:
                for row in sess.execute(sql):
                    patient_names[row['InternalId']] = row['full_name']
        except Exception as exc:
            current_app.logger.warning('doctor.chats: patient name lookup failed: %s', exc)

    patient_options = [
        {'patient_id': pid, 'name': patient_names.get(pid, f'Patient {pid}')}
        for pid in sorted(patient_ids)
    ]

    session_messages = {s.id: s.messages.all() for s in session_rows}

    return render_template(
        'doctor/chats.html',
        sessions=session_rows,
        session_messages=session_messages,
        patient_names=patient_names,
        patient_options=patient_options,
        doctor_users=doctor_users,
        filter_start=filter_start,
        filter_end=filter_end,
        filter_user_id=filter_user_id or '',
        filter_patient_id=filter_patient_id or '',
        is_admin=is_admin,
    )


@bp.get('/sms')
@login_required
def sms():
    return redirect(url_for('doctor.comms', **request.args), 301)


# ── Comms ───────────────────────────────────────────────────────────────────────

@bp.get('/comms')
@login_required
def comms():
    from app.models.patient_message import PatientMessage, MessageChannel, MessageStatus
    from app.extensions import db

    args = request.args.to_dict()
    if 'period' not in args and 'date_from' not in args:
        args['period'] = 'today'
    start, end, period = _resolve_period(args)
    uid, display_name, doctors, is_admin = _doctor_context()

    channels = request.args.getlist('channel') or ['email', 'sms']
    statuses = request.args.getlist('status')  or ['sent', 'failed', 'revoked', 'draft']
    search   = request.args.get('search', '').strip() or None

    user_id = None
    if uid is not None:
        from app.models.user import User
        u = User.query.filter_by(bpsdb_user_id=int(uid)).first()
        user_id = u.id if u else -1

    q = PatientMessage.query.filter(
        db.func.date(PatientMessage.created_at) >= start,
        db.func.date(PatientMessage.created_at) <= end,
    )
    valid_channels = [MessageChannel(c) for c in channels if c in MessageChannel._value2member_map_]
    if valid_channels:
        q = q.filter(PatientMessage.channel.in_(valid_channels))
    valid_statuses = [MessageStatus(s) for s in statuses if s in MessageStatus._value2member_map_]
    if valid_statuses:
        q = q.filter(PatientMessage.status.in_(valid_statuses))
    if user_id is not None:
        q = q.filter(PatientMessage.created_by_id == user_id)
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(
            PatientMessage.to_address.ilike(like),
            PatientMessage.subject.ilike(like),
        ))

    messages = q.order_by(PatientMessage.created_at.desc()).limit(300).all()

    patient_ids   = list({m.patient_id for m in messages if m.patient_id})
    patient_names = {}
    if patient_ids:
        try:
            id_list = ','.join(str(int(i)) for i in patient_ids)
            sql = (
                f"SELECT InternalId, TRIM(Firstname) + ' ' + TRIM(Surname) AS full_name"
                f" FROM PATIENTS WHERE InternalId IN ({id_list})"
            )
            with _bpsdb() as sess:
                for row in sess.execute(sql):
                    patient_names[row['InternalId']] = row['full_name']
        except Exception as exc:
            current_app.logger.warning('doctor.comms: patient name lookup failed: %s', exc)

    return render_template(
        'doctor/comms.html',
        messages=messages,
        patient_names=patient_names,
        start_date=start,
        end_date=end,
        period=period,
        search=search or '',
        display_name=display_name,
        doctors=doctors,
        selected_doctor_id=request.args.get('doctor_id', ''),
        is_admin=is_admin,
        channels=channels,
        statuses=statuses,
    )


# ── Doctor Links ───────────────────────────────────────────────────────────────

def _links_check(app, link_id: int, url: str) -> None:
    """Background thread: HEAD-check URL and increment dead_count on failure."""
    with app.app_context():
        try:
            import requests as _req
            resp = _req.head(url, timeout=5, allow_redirects=True)
            is_dead = resp.status_code >= 400
        except Exception:
            is_dead = True
        if is_dead:
            from app.extensions import db
            from app.models.doctor_link import DoctorLink
            lnk = DoctorLink.query.get(link_id)
            if lnk:
                lnk.dead_count += 1
                db.session.commit()


@bp.get('/links')
@login_required
def links():
    from app.models.doctor_link import DoctorLink
    items = (DoctorLink.query
             .filter_by(user_id=current_user.id)
             .order_by(DoctorLink.popularity.desc(), DoctorLink.name)
             .all())
    return render_template('doctor/links.html', links=items)


@bp.get('/links/go/<int:link_id>')
@login_required
def links_go(link_id: int):
    from app.extensions import db
    from app.models.doctor_link import DoctorLink
    lnk = DoctorLink.query.filter_by(id=link_id, user_id=current_user.id).first_or_404()
    lnk.popularity += 1
    db.session.commit()
    dest = lnk.url
    app = current_app._get_current_object()
    threading.Thread(target=_links_check, args=(app, link_id, dest), daemon=True).start()
    return redirect(dest)


@bp.post('/links')
@login_required
def links_add():
    from app.extensions import db
    from app.models.doctor_link import DoctorLink
    data = request.get_json(silent=True) or {}
    url  = (data.get('url') or '').strip()
    name = (data.get('name') or '').strip()
    if not url or not name:
        return jsonify({'ok': False, 'error': 'name and url are required'}), 400
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    lnk = DoctorLink(
        user_id  = current_user.id,
        name     = name,
        url      = url,
        keywords = (data.get('keywords') or '').strip() or None,
    )
    db.session.add(lnk)
    db.session.commit()
    return jsonify({'ok': True, 'id': lnk.id}), 201


@bp.put('/links/<int:link_id>')
@login_required
def links_update(link_id: int):
    from app.extensions import db
    from app.models.doctor_link import DoctorLink
    lnk  = DoctorLink.query.filter_by(id=link_id, user_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        lnk.name = (data['name'] or '').strip() or lnk.name
    if 'url' in data:
        url = (data['url'] or '').strip()
        if url and not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        if url:
            lnk.url = url
    if 'keywords' in data:
        lnk.keywords = (data['keywords'] or '').strip() or None
    db.session.commit()
    return jsonify({'ok': True})


@bp.delete('/links/<int:link_id>')
@login_required
def links_delete(link_id: int):
    from app.extensions import db
    from app.models.doctor_link import DoctorLink
    lnk = DoctorLink.query.filter_by(id=link_id, user_id=current_user.id).first_or_404()
    db.session.delete(lnk)
    db.session.commit()
    return jsonify({'ok': True})


# ── Application Usage (admin) ──────────────────────────────────────────────────
# Reports over the permanent usage record (plans/usage_reporting_plan.md).
# On screen (admin only) staff appear by name unless the "Show names" switch is
# turned off (names=0), e.g. while sharing the screen. An export uses permanent
# labels unless names are confirmed in the pop-up, and the server re-checks admin
# before including them.

# The page's state lives in the URL (ADR-137): tab, measure, breakdown (`by`),
# rows view and page, plus the filters, so Back works, a view can be bookmarked
# and an export gets exactly what is on screen.
_USAGE_COMMON = ('period', 'date_from', 'date_to', 'group', 'user_id', 'role', 'names',
                 'src_set', 'src_live', 'src_imported', 'src_unattributed')


def _usage_filters(args):
    from app.services.usage_report_service import Filters, GROUPS, SOURCES, AI_FILTERS, NONAI_FILTERS
    period_args = dict(args)
    if 'period' not in period_args and 'date_from' not in period_args:
        period_args['period'] = 'year'
    start, end, period = _resolve_period(period_args)
    sources = {s for s in SOURCES if args.get(f'src_{s}')} if args.get('src_set') else set(SOURCES)
    tab_names = AI_FILTERS if args.get('tab', 'ai') != 'nonai' else NONAI_FILTERS
    return Filters(
        start=start, end=end, user_id=args.get('user_id', type=int), role=args.get('role', ''),
        sources=sources, group=args.get('group', 'week') if args.get('group') in GROUPS else 'week',
        # Only the open tab's own filters count; the other tab's are dropped.
        **{n: args.get(n, '') for n in tab_names},
    ), period


def _usage_view(args):
    from app.services.usage_report_service import View
    return View(tab=args.get('tab', 'ai'), measure=args.get('measure', 'runs'), by=args.get('by', ''),
                rows=args.get('view') == 'rows', page=args.get('page', 1, type=int) or 1).normalise()


def _usage_args(args, view) -> dict:
    """The current URL's arguments that belong to this view, without blanks."""
    from app.services.usage_report_service import tab_filters
    keep = set(_USAGE_COMMON) | set(tab_filters(view.tab)) | {'tab', 'measure', 'by', 'view', 'page'}
    out = {k: v for k, v in args.items() if k in keep and v not in ('', None)}
    out.update(tab=view.tab, by=view.by)          # the normalised values, never a bad one
    if view.tab == 'ai':
        out['measure'] = view.measure
    else:
        out.pop('measure', None)
    if 'page' in out:
        out['page'] = view.page
    return out


@bp.get('/usage')
@login_required
@_require_admin
def usage():
    from app.services import usage_report_service as reports
    filters, period = _usage_filters(request.args)
    view = _usage_view(request.args)
    show_names = request.args.get('names', '1') != '0'
    report = reports.build(view, filters, show_names=show_names)
    namer = reports.person_namer(show_names)
    report['filters'] = reports.describe(filters, view, namer)
    current = _usage_args(request.args, view)

    def usage_url(**changes):
        # `None` removes an argument. Switching tab or measure starts the
        # breakdown afresh and drops the other tab's filters.
        merged = dict(current)
        if 'tab' in changes:
            merged = {k: v for k, v in merged.items() if k in _USAGE_COMMON}
        if 'tab' in changes or 'measure' in changes:
            merged.pop('view', None)
            merged.pop('page', None)
        for k, v in changes.items():
            if v is None or v == '':
                merged.pop(k, None)
            else:
                merged[k] = v
        return url_for('doctor.usage', **merged)

    chips = []
    if filters.user_id:
        chips.append(('Person', namer(filters.user_id), usage_url(user_id=None, page=None)))
    if filters.role:
        chips.append(('Role', filters.role, usage_url(role=None, page=None)))
    for n in reports.tab_filters(view.tab):
        value = getattr(filters, n)
        if value:
            chips.append((reports.FILTER_LABELS[n], reports.value_label(n, value),
                          usage_url(**{n: None, 'page': None})))
    clear_url = usage_url(**{k: None for k in ('user_id', 'role', 'page', *reports.tab_filters(view.tab))})
    drills = [usage_url(**reports.drill(view, filters, key)) if key is not None else None
              for key in report['table']['keys']]
    choices = reports.choices()
    people = sorted(((uid, namer(uid)) for uid in choices['users']), key=lambda p: p[1])
    return render_template(
        'doctor/usage.html', report=report, filters=filters, view=view, period=period,
        start_date=filters.start, end_date=filters.end, show_names=show_names,
        choices=choices, people=people, chips=chips, clear_url=clear_url, drills=drills, usage_url=usage_url,
        tabs=reports.TABS, measures=reports.MEASURES, labels=reports.value_label,
        chart_json=json.dumps({'type': report['chart_type'], 'data': report['chart']}),
    )


@bp.get('/usage/export')
@login_required
@_require_admin
def usage_export():
    from flask import Response
    from app.services import usage_report_service as reports
    from app.services import usage_service

    fmt = request.args.get('format', 'csv')
    if fmt not in ('csv', 'md', 'print'):
        abort(400)
    # Names only on explicit, confirmed request — and only for an admin, which
    # _require_admin has already established for this whole route.
    identified = request.args.get('identify') == '1' and current_user.is_admin
    filters, _ = _usage_filters(request.args)
    view = _usage_view(request.args)
    report = reports.build(view, filters, show_names=identified, export=True)
    report['filters'] = reports.describe(filters, view, reports.person_namer(identified))

    usage_service.record_task(
        'report.export', 'practice', user_id=current_user.id, patient_linked=False,
        workstation=request.remote_addr,
        detail={'report': f'{view.kind}:{"rows" if view.rows else view.by}', 'format': fmt,
                'identified': identified})

    stamp = datetime.now().strftime('%Y%m%d')
    part = 'rows' if view.rows else f'by_{view.by}'
    base = f"application_usage_{view.kind}_{part}_{stamp}{'_NAMED' if identified else ''}"
    if fmt == 'csv':
        return Response(reports.to_csv(report), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="{base}.csv"'})
    if fmt == 'md':
        return Response(reports.to_markdown(report, identified), mimetype='text/markdown',
                        headers={'Content-Disposition': f'attachment; filename="{base}.md"'})
    return render_template('doctor/usage_print.html', report=report, identified=identified,
                           generated_at=datetime.now())
