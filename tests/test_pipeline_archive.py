"""Archived pipelines (ADR-130): hidden from the designer list and never run. No database."""
import pytest

from app.models.pipeline import Pipeline, PipelineStatus


@pytest.mark.parametrize('status,archived', [
    (PipelineStatus.draft, False), (PipelineStatus.active, False), (PipelineStatus.archived, True)])
def test_is_archived(status, archived):
    assert Pipeline(name='Invented', status=status).is_archived is archived


def test_engine_refuses_an_archived_pipeline(monkeypatch):
    from app.extensions import db
    from app.services.pipeline.engine import PipelineEngine
    monkeypatch.setattr(db.session, 'get', lambda model, pid: Pipeline(name='Invented', status=PipelineStatus.archived))
    with pytest.raises(ValueError, match='archived'):
        PipelineEngine._execute('run-x', 1, None, 1, {}, False, None)
