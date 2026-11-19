"""In-app help (ADR-102): the help centre, a topic, and the section the [?] panel shows.

GET /help                           Topics the user's role may see, by area; ?q= searches
GET /help/<topic>                   One topic, all its sections
GET /help/panel/<topic>/<section>   One section, for the side panel (HTML fragment)
"""
from flask import abort, render_template, request
from flask_login import current_user, login_required

from . import bp
from app.services import help_service as hs


@bp.get('/')
@login_required
def index():
    query = request.args.get('q', '').strip()
    topics = sorted(hs.visible_topics(current_user), key=lambda t: t.title)
    by_area = [(area, [t for t in topics if t.area == area]) for area in hs.AREAS]
    return render_template('help/index.html', query=query,
                           results=hs.search(query, current_user) if query else None,
                           by_area=[(a, ts) for a, ts in by_area if ts])


@bp.get('/<topic_id>')
@login_required
def topic(topic_id):
    t = hs.topics().get(topic_id)
    if not t or not hs.can_see(t, current_user):
        abort(404)
    related = [r for r in (hs.topics().get(rid) for rid in t.related) if r and hs.can_see(r, current_user)]
    return render_template('help/topic.html', topic=t, related=related, render=hs.render)


@bp.get('/panel/<topic_id>/<section_id>')
@login_required
def panel(topic_id, section_id):
    t, s = hs.find(f'{topic_id}.{section_id}')
    if not t or not s or not hs.can_see(t, current_user):
        abort(404)
    return render_template('help/_panel_section.html', topic=t, section=s, render=hs.render)
