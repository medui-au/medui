from datetime import datetime, timezone
from flask import current_app
from flask_login import current_user
from app.extensions import db
from app.models.prompt import SystemPrompt, UserPrompt


class SystemPromptService:

    @staticmethod
    def list_active():
        """Return one row per name — the currently active version."""
        return (SystemPrompt.query
                .filter_by(is_active=True)
                .order_by(SystemPrompt.name)
                .all())

    @staticmethod
    def get(prompt_id: int) -> SystemPrompt | None:
        return db.session.get(SystemPrompt, prompt_id)

    @staticmethod
    def get_by_name(name: str) -> SystemPrompt | None:
        return (SystemPrompt.query
                .filter_by(name=name, is_active=True)
                .first())

    @staticmethod
    def get_history(name: str) -> list[SystemPrompt]:
        return (SystemPrompt.query
                .filter_by(name=name)
                .order_by(SystemPrompt.version.desc())
                .all())

    @staticmethod
    def create(data: dict) -> SystemPrompt:
        sp = SystemPrompt(
            name=data['name'].strip(),
            prompt_text=data['prompt_text'].strip(),
            description=data.get('description', '').strip() or None,
            version=1,
            is_active=True,
            is_default=bool(data.get('is_default')),
            scope_key=(data.get('scope_key') or '').strip() or None,
            created_by_id=current_user.id if current_user.is_authenticated else None,
        )
        if sp.is_default:
            SystemPromptService._clear_default()
        db.session.add(sp)
        db.session.commit()
        return sp

    @staticmethod
    def edit(prompt_id: int, data: dict) -> SystemPrompt:
        """Append-only: deactivate current, insert new row at version + 1."""
        current = db.session.get(SystemPrompt, prompt_id)
        if not current:
            raise ValueError(f'SystemPrompt {prompt_id} not found')
        if not current.is_active:
            raise ValueError('Cannot edit an inactive (historical) system prompt version')

        current.is_active = False
        current.is_default = False

        new_sp = SystemPrompt(
            name=current.name,
            prompt_text=data.get('prompt_text', current.prompt_text).strip(),
            description=data.get('description', current.description or '').strip() or None,
            version=current.version + 1,
            is_active=True,
            is_default=bool(data.get('is_default')),
            # Carried forward unless the form sends a choice ('' = practice default).
            scope_key=((data['scope_key'].strip() or None) if 'scope_key' in data
                       else current.scope_key),
            created_by_id=current_user.id if current_user.is_authenticated else None,
        )
        if new_sp.is_default:
            SystemPromptService._clear_default()
        db.session.add(new_sp)
        db.session.commit()
        return new_sp

    @staticmethod
    def set_default(prompt_id: int) -> SystemPrompt:
        sp = db.session.get(SystemPrompt, prompt_id)
        if not sp or not sp.is_active:
            raise ValueError('Prompt not found or inactive')
        SystemPromptService._clear_default()
        sp.is_default = True
        db.session.commit()
        return sp

    @staticmethod
    def delete(prompt_id: int) -> None:
        sp = db.session.get(SystemPrompt, prompt_id)
        if not sp:
            raise ValueError('Not found')
        # Soft-delete: mark all versions inactive
        for row in SystemPrompt.query.filter_by(name=sp.name).all():
            row.is_active = False
        db.session.commit()

    @staticmethod
    def _clear_default() -> None:
        SystemPrompt.query.filter_by(is_default=True).update({'is_default': False})


class UserPromptService:

    @staticmethod
    def list_all() -> list[UserPrompt]:
        return (UserPrompt.query
                .filter_by(is_active=True)
                .order_by(UserPrompt.name)
                .all())

    @staticmethod
    def list_for_assistant() -> list[UserPrompt]:
        return (UserPrompt.query
                .filter_by(is_active=True, show_in_assistant=True)
                .order_by(UserPrompt.name)
                .all())

    @staticmethod
    def get(prompt_id: int) -> UserPrompt | None:
        return db.session.get(UserPrompt, prompt_id)

    @staticmethod
    def create(data: dict) -> UserPrompt:
        up = UserPrompt(
            name=data['name'].strip(),
            description=data.get('description', '').strip() or None,
            prompt_text=data['prompt_text'].strip(),
            system_prompt_name=data.get('system_prompt_name', '').strip() or None,
            classifier=data.get('classifier', '').strip() or None,
            default_model_id=_int_or_none(data.get('default_model_id')),
            show_in_assistant=bool(data.get('show_in_assistant')),
            temperature=_float_or_none(data.get('temperature')),
            max_tokens=_int_or_none(data.get('max_tokens')),
            is_active=True,
            created_by_id=current_user.id if current_user.is_authenticated else None,
        )
        db.session.add(up)
        db.session.commit()
        return up

    @staticmethod
    def edit(prompt_id: int, data: dict) -> UserPrompt:
        up = db.session.get(UserPrompt, prompt_id)
        if not up:
            raise ValueError(f'UserPrompt {prompt_id} not found')
        up.name = data.get('name', up.name).strip()
        up.description = data.get('description', up.description or '').strip() or None
        up.prompt_text = data.get('prompt_text', up.prompt_text).strip()
        up.system_prompt_name = data.get('system_prompt_name', '').strip() or None
        up.classifier = data.get('classifier', '').strip() or None
        up.default_model_id = _int_or_none(data.get('default_model_id'))
        up.show_in_assistant = bool(data.get('show_in_assistant'))
        up.temperature = _float_or_none(data.get('temperature'))
        up.max_tokens = _int_or_none(data.get('max_tokens'))
        db.session.commit()
        return up

    @staticmethod
    def toggle_assistant(prompt_id: int) -> UserPrompt:
        up = db.session.get(UserPrompt, prompt_id)
        if not up:
            raise ValueError('Not found')
        up.show_in_assistant = not up.show_in_assistant
        db.session.commit()
        return up

    @staticmethod
    def delete(prompt_id: int) -> None:
        up = db.session.get(UserPrompt, prompt_id)
        if not up:
            raise ValueError('Not found')
        up.is_active = False
        db.session.commit()


def _float_or_none(v) -> float | None:
    try:
        return float(v) if v not in (None, '', 'None') else None
    except (TypeError, ValueError):
        return None


def _int_or_none(v) -> int | None:
    try:
        return int(v) if v not in (None, '', 'None') else None
    except (TypeError, ValueError):
        return None
