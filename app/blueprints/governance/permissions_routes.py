from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.governance_permission import GovernancePermission
from .permissions import require_governance_level
from . import bp


@bp.route('/permissions/')
@login_required
def permissions_index():
    require_governance_level(9)
    grants = (
        GovernancePermission.query
        .join(GovernancePermission.user)
        .order_by(User.display_name)
        .all()
    )
    all_users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    return render_template(
        'governance/permissions/index.html',
        grants=grants,
        all_users=all_users,
    )


@bp.route('/permissions/grant', methods=['POST'])
@login_required
def permissions_grant():
    require_governance_level(9)
    user_id = request.form.get('user_id', type=int)
    level = request.form.get('governance_level', type=int)
    notes = request.form.get('notes', '').strip() or None

    if not user_id or not level or level < 1 or level > 9:
        flash('Invalid user or level.', 'error')
        return redirect(url_for('governance.permissions_index'))

    target = User.query.get(user_id)
    if not target:
        flash('User not found.', 'error')
        return redirect(url_for('governance.permissions_index'))

    perm = GovernancePermission.query.filter_by(user_id=user_id).first()
    if perm:
        perm.governance_level = level
        perm.notes = notes
        perm.granted_by_id = current_user.id
        flash(f'Updated governance level for {target.display_name or target.username} to {level}.', 'success')
    else:
        perm = GovernancePermission(
            user_id=user_id,
            governance_level=level,
            notes=notes,
            granted_by_id=current_user.id,
        )
        db.session.add(perm)
        flash(f'Granted governance level {level} to {target.display_name or target.username}.', 'success')

    db.session.commit()
    return redirect(url_for('governance.permissions_index'))


@bp.route('/permissions/<int:perm_id>/revoke', methods=['POST'])
@login_required
def permissions_revoke(perm_id):
    require_governance_level(9)
    perm = GovernancePermission.query.get_or_404(perm_id)
    name = perm.user.display_name or perm.user.username
    db.session.delete(perm)
    db.session.commit()
    flash(f'Removed governance override for {name}.', 'success')
    return redirect(url_for('governance.permissions_index'))
