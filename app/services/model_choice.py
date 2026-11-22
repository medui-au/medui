"""The AI models a person may choose for one run (ADR-174, ADR-178): the same list the AI Assistant
offers (enabled, shown in AI Assist, not speech-to-text). A choice is sent to the engine as
`model_id_override`, so the local/cloud derivation and the security check apply as for any run."""


def available_models() -> list:
    from app.models.ai_provider import AIModel
    return (AIModel.query.filter_by(is_enabled=True, show_in_ai_assist=True, is_asr=False)
            .order_by(AIModel.display_name).all())


def chosen(model_id):
    """The model for this id if it is one of available_models(); None for no choice."""
    if not model_id:
        return None
    try:
        mid = int(model_id)
    except (TypeError, ValueError):
        raise ValueError('Choose a model from the list.')
    m = next((m for m in available_models() if m.id == mid), None)
    if m is None:
        raise ValueError('Choose a model from the list.')
    return m


def label(model) -> str:
    if model is None:
        return ''
    where = ''
    if getattr(model, 'provider', None) is not None:
        where = ' (local)' if model.provider.is_local else ' (cloud)'
    return f'{model.display_name or model.model_id}{where}'
