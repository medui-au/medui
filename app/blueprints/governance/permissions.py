"""Governance-level access helpers shared across both register route modules."""
from functools import lru_cache
from flask import abort
from flask_login import current_user


def effective_governance_level(user) -> int:
    """Return the higher of the user's general security_level or their governance override."""
    from app.models.governance_permission import GovernancePermission
    perm = GovernancePermission.query.filter_by(user_id=user.id).first()
    override = perm.governance_level if perm else 0
    return max(user.security_level, override)


def require_governance_level(level: int) -> None:
    if effective_governance_level(current_user) < level:
        abort(403)


def has_governance_level(level: int) -> bool:
    return effective_governance_level(current_user) >= level
