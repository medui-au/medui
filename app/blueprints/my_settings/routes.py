"""My settings: each user's personal settings (ADR-085)."""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import user_settings_service as user_settings
from . import bp


@bp.get('/settings')
@login_required
def index():
    return render_template('my_settings/index.html',
                           sections=user_settings.page_sections(current_user))


@bp.post('/settings')
@login_required
def save():
    errors = user_settings.save_from_form(current_user, request.form)
    if errors:
        for msg in errors:
            flash(msg, 'danger')
    else:
        flash('Settings saved.', 'success')
    return redirect(url_for('my_settings.index'))


@bp.get('/settings/details-card')
@login_required
def details_card():
    """Your own details from Best Practice, for the card on your name (ADR-125)."""
    from app.services.doctor_profile_service import get_card
    return render_template('my_settings/_details_card.html', card=get_card(current_user),
                           person=current_user, lookup=False)


# ── My usage (ADR-138) ───────────────────────────────────────────────────────
# Your own Application Usage. The person is always the signed-in user: any
# user_id, role, source or names argument in the address is ignored.
_MY_USAGE_DROP = ('user_id', 'role', 'names', 'src_set', 'src_live', 'src_imported', 'src_unattributed')


@bp.get('/settings/usage')
@login_required
def usage():
    import json
    from app.blueprints.doctor.routes import _usage_args, _usage_filters, _usage_view
    from app.services import my_usage_service as mine
    from app.services import usage_report_service as reports

    args = request.args.copy()
    # Opens on Non-AI when this installation has AI switched off, or the user has no AI.
    if 'tab' not in args and not (current_app.config.get('AI_ENABLED') and current_user.can_use_ai):
        args['tab'] = 'nonai'
    filters, period = _usage_filters(args)
    view = mine.own_view(_usage_view(args))
    report = mine.build(current_user.id, view, filters)
    locked = mine.lock(filters, current_user.id)
    current = {k: v for k, v in _usage_args(args, view).items() if k not in _MY_USAGE_DROP}

    def usage_url(**changes):
        merged = dict(current)
        if 'tab' in changes:
            merged = {k: v for k, v in merged.items() if k in ('period', 'date_from', 'date_to', 'group')}
        if 'tab' in changes or 'measure' in changes:
            merged.pop('view', None)
            merged.pop('page', None)
        for k, v in changes.items():
            if v is None or v == '':
                merged.pop(k, None)
            else:
                merged[k] = v
        return url_for('my_settings.usage', **merged)

    chips = [(reports.FILTER_LABELS[n], reports.value_label(n, getattr(filters, n)),
              usage_url(**{n: None, 'page': None}))
             for n in reports.tab_filters(view.tab) if getattr(filters, n)]
    clear_url = usage_url(**{k: None for k in ('page', *reports.tab_filters(view.tab))})
    drills = [usage_url(**mine.drill(view, locked, key)) if key is not None else None
              for key in report['table']['keys']]
    return render_template(
        'my_settings/usage.html', report=report, filters=filters, view=view, period=period,
        start_date=filters.start, end_date=filters.end, chips=chips, clear_url=clear_url,
        drills=drills, usage_url=usage_url, tabs=reports.TABS, measures=reports.MEASURES,
        chart_json=json.dumps({'type': report['chart_type'], 'data': report['chart']}),
    )
