from pathlib import Path

from flask import abort, current_app, render_template
from flask_login import current_user, login_required
from markupsafe import Markup
from . import bp


@bp.get('/')
@login_required
def index():
    return render_template('index.html')


@bp.get('/install-status')
@login_required
def install_status():
    # The home page's installation panel, loaded after the page (the checks connect to
    # Best Practice and OCR, and mustn't hold the page up). Administrators only.
    if not current_user.is_admin:
        abort(403)
    from app.services import install_status as status
    found = status.items()
    return render_template('install_status.html', items=found, summary=status.summary(found),
                           demo=status.is_demo())


@bp.get('/about')
def about():
    # Public: the intended purpose is shown to anyone who reaches the app, signed in or not.
    # Rendered from docs/intended_purpose.md so the app and the docs can't drift apart.
    import markdown as md_lib
    path = Path(current_app.root_path).parent / 'docs' / 'intended_purpose.md'
    text = path.read_text(encoding='utf-8')
    body = text[text.index('## Statement'):]
    return render_template('about.html', body=Markup(md_lib.markdown(body)))
