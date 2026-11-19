from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from . import bp


@bp.get('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    from app.services.auth_service import AuthService
    users = AuthService.get_login_users()
    return render_template('auth/login.html', users=users)


@bp.post('/login')
def login_post():
    from app.services.auth_service import AuthService
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    user = AuthService.authenticate(username, password)
    if user:
        login_user(user, remember=False)
        AuthService.record_login(user)
        next_url = AuthService.safe_next(request.args.get('next'))
        if AuthService.needs_bp_setup(user, next_url, url_for('setup.index')):
            # An administrator, and Best Practice isn't set in .env: open Setup → Database (once,
            # at login only, so it can't loop).
            flash(AuthService.BP_SETUP_MESSAGE, 'warning')
            return redirect(url_for('setup.index', tab='database'))
        return redirect(next_url or url_for('main.index'))

    flash('Invalid username or password.', 'error')
    return redirect(url_for('auth.login'))


@bp.post('/theme')
@login_required
def set_theme():
    from app.extensions import db
    theme = request.form.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    current_user.theme = theme
    db.session.commit()
    return '', 204


@bp.get('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
