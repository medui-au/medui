"""Practitioners' preferred names (ADR-106).

A user can go by a name other than the one in Best Practice (My Settings, or an
administrator in Setup → Users). MedUI shows that name everywhere: its own users'
display_name, and the names its Best Practice queries return, swapped here by BP
user ID. The BP name is never changed. Redaction keeps the BP name and adds the
preferred name, so either form is caught.
"""
from flask import g, has_app_context

_TITLES = {'dr', 'dr.', 'prof', 'prof.', 'professor', 'mr', 'mr.', 'mrs', 'mrs.', 'ms', 'ms.',
           'miss', 'mx', 'mx.', 'assoc', 'a/prof', 'a/prof.'}


def preferred_by_bp_user() -> dict[int, str]:
    """{BP user ID: preferred name} for users who have one; once per request."""
    if not has_app_context():
        return {}
    cached = g.get('_preferred_names')
    if cached is not None:
        return cached
    from app.models.user import User
    rows = (User.query.with_entities(User.bpsdb_user_id, User.preferred_name)
            .filter(User.bpsdb_user_id.isnot(None), User.preferred_name.isnot(None)).all())
    g._preferred_names = {int(uid): n.strip() for uid, n in rows if n and n.strip()}
    return g._preferred_names


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def name(bp_user_id, bp_name: str) -> str:
    """The preferred name for this BP user, else the name BP gave."""
    uid = _to_int(bp_user_id)
    return preferred_by_bp_user().get(uid, bp_name) if uid is not None else bp_name


def _words(full_name: str) -> list[str]:
    words = [w for w in (full_name or '').split() if w]
    while words and words[0].lower() in _TITLES:
        words = words[1:]
    return words


def initials(bp_user_id, bp_initials: str) -> str:
    """Initials from the preferred name (first and last word, titles left out), keeping
    BP's '(K)' marker; else the initials BP gave."""
    uid = _to_int(bp_user_id)
    preferred = preferred_by_bp_user().get(uid) if uid is not None else None
    words = _words(preferred) if preferred else []
    if not words:
        return bp_initials
    letters = (words[0][0] + (words[-1][0] if len(words) > 1 else '')).upper()
    if (bp_initials or '').endswith('(K)'):
        letters += '(K)'
    return letters


def swap(rows: list[dict], id_key: str, name_key: str, initials_mode: bool = False) -> list[dict]:
    """Apply the preferred names to query rows in place (and return them)."""
    if not preferred_by_bp_user():
        return rows
    for row in rows:
        if name_key in row:
            fn = initials if initials_mode else name
            row[name_key] = fn(row.get(id_key), row.get(name_key))
    return rows


def apply_to_user(user) -> None:
    """Set the user's shown name after their preferred name changes (caller commits)."""
    user.display_name = user.preferred_name or user.bp_display_name or user.display_name


def extra_rows(rows: list[dict], id_key: str = 'user_id', first_key: str = 'first_name',
               surname_key: str = 'surname', lower: bool = False) -> list[dict]:
    """For redaction and the leak checker: a copy of each BP user row whose user has a
    preferred name, with the name parts replaced by the preferred ones. Added to the BP
    rows, never instead of them. Read fresh each time (not cached), so a name saved
    here is redacted at once, on every front-end."""
    preferred = preferred_by_bp_user()
    if not preferred:
        return []
    extra = []
    for row in rows:
        uid = _to_int(row.get(id_key))
        words = _words(preferred.get(uid, '')) if uid is not None else []
        if len(words) < 2:
            continue      # a first name alone is too common to redact everywhere
        first, surname = ' '.join(words[:-1]), words[-1]
        if lower:
            first, surname = first.lower(), surname.lower()
        copy = dict(row)
        copy[first_key], copy[surname_key] = first, surname
        extra.append(copy)
    return extra



def clinician_first_names(user_id) -> list[str]:
    """The first names of the clinician who recorded a consultation (ADR-133).

    Their Best Practice first name and the first name(s) of their preferred name
    in MedUI. Passed to the redaction core for the transcript only, where they are
    taken in any case. Read fresh each run. [] for an unknown user; a BP failure
    leaves the preferred name (the practitioner pass fails the run closed anyway).
    """
    from app.extensions import db
    from app.models.user import User
    uid = _to_int(user_id)
    user = db.session.get(User, uid) if uid is not None else None
    if user is None:
        return []
    rows: list[dict] = []
    if user.bpsdb_user_id is not None:
        from flask import current_app
        from app.services import redaction_core
        try:
            source = redaction_core.redactor().source
            rows = list(source.query('practice_doctors')) + list(source.query('practice_staff'))
        except Exception as exc:  # pyodbc raises several unrelated error types
            current_app.logger.warning('clinician first names: BP lookup failed: %s',
                                       type(exc).__name__)
    return first_names_for(user.preferred_name, user.bpsdb_user_id, rows)


def first_names_for(preferred_name, bp_user_id, rows: list[dict]) -> list[str]:
    """The preferred name's first name(s), then the BP first name of this user's own row
    (not a host-added preferred-name row, whose id carries a 'p')."""
    names: list[str] = []
    words = _words(preferred_name or '')
    if words:
        names.append(' '.join(words[:-1]) if len(words) > 1 else words[0])
    if bp_user_id is not None:
        for row in rows:
            if str(row.get('user_id')) == str(bp_user_id):
                first = (row.get('first_name') or '').strip()
                if first:
                    names.append(first)
    return list(dict.fromkeys(names))
