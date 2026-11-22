"""flask gpccmp seed-pipeline — add the GPCCMP drafting prompts and pipeline (ADR-174).

Adds new rows only, matched by name, so running it again changes nothing. It never reads, edits,
renames or deactivates an existing prompt or pipeline.
"""
import json

import click
from flask.cli import AppGroup

gpccmp_cli = AppGroup('gpccmp', help='GPCCMP drafting (ADR-174).')

PIPELINE_SETTING = 'gpccmp.pipeline_id'


def seed_pipeline(model_id: int | None = None) -> dict:
    from app.extensions import db
    from app.models.ai_provider import AIModel
    from app.models.pipeline import Pipeline, PipelineStatus, PipelineStep, RedactionPolicy
    from app.models.prompt import SystemPrompt, UserPrompt
    from app.models.system_setting import SystemSetting
    from app.services import gpccmp_prompt_seed as seed

    if model_id is not None and not db.session.get(AIModel, model_id):
        raise click.ClickException(f'No AI model with id {model_id}.')
    made = []
    sp = SystemPrompt.query.filter_by(name=seed.SYSTEM_PROMPT_NAME).first()
    if sp is None:
        sp = SystemPrompt(name=seed.SYSTEM_PROMPT_NAME, prompt_text=seed.SYSTEM_PROMPT, is_active=True,
                          is_default=False, description='GPCCMP drafting frame and tabular format (ADR-174). '
                          'The practice protocol and the GP decisions arrive as data.')
        db.session.add(sp)
        made.append('system prompt')
    up = UserPrompt.query.filter_by(name=seed.USER_PROMPT_NAME).first()
    if up is None:
        up = UserPrompt(name=seed.USER_PROMPT_NAME, prompt_text=seed.USER_PROMPT, system_prompt_name=seed.SYSTEM_PROMPT_NAME,
                        description='Carries [GP DECISIONS], [PROTOCOL MODULES] and the record (ADR-174).',
                        show_in_assistant=False, temperature=0.2, is_active=True)
        db.session.add(up)
        db.session.flush()
        made.append('user prompt')
    pl = Pipeline.query.filter_by(name=seed.PIPELINE_NAME).first()
    if pl is None:
        pl = Pipeline(name=seed.PIPELINE_NAME, redaction_policy=RedactionPolicy.redact_all,
                      status=PipelineStatus.active if model_id else PipelineStatus.draft,
                      description='Drafts a GPCCMP from the GP\'s decisions, the practice protocol and the record (ADR-174). '
                                  'Started from GPCCMP: Targets & Plan, not from the AI Assistant.',
                      show_in_topnav=False)
        db.session.add(pl)
        db.session.flush()
        steps = [('data_assembly', {'blocks': list(seed.RECORD_BLOCKS)}, 'Record'),
                 ('prompt_assembly', {'user_prompt_id': up.id}, 'GPCCMP prompt'),
                 ('inference', {'model_id': model_id} if model_id else {}, 'Draft'),
                 ('deredaction', {}, 'Restore')]
        for i, (node, cfg, label) in enumerate(steps):
            db.session.add(PipelineStep(pipeline_id=pl.id, step_order=i, node_type=node, config_json=json.dumps(cfg), label=label))
        made.append('pipeline')
    db.session.commit()
    if not SystemSetting.get(PIPELINE_SETTING):
        SystemSetting.set(PIPELINE_SETTING, pl.id, description='The GPCCMP drafting pipeline (ADR-174)')
    return {'made': made, 'pipeline_id': pl.id, 'user_prompt_id': up.id, 'system_prompt_id': sp.id}


@gpccmp_cli.command('seed-pipeline')
@click.option('--model-id', type=int, default=None, help='The AI model for the draft step (otherwise set it in the Pipeline Designer).')
def seed_pipeline_command(model_id):
    """Add the GPCCMP drafting prompts and pipeline (new rows only)."""
    out = seed_pipeline(model_id)
    click.echo(f"Added: {', '.join(out['made']) or 'nothing (already there)'}. Pipeline id {out['pipeline_id']}.")
    if not model_id:
        click.echo('Choose its model in Admin → Pipeline Designer and set it active.')
