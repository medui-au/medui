"""Extra request parameters per model with a per-step override (ADR-119). No database, no network."""
from types import SimpleNamespace
from unittest import mock

import pytest

from app.services import request_params as rp


def test_blank_is_none():
    assert rp.parse('') is None and rp.parse('  ') is None and rp.parse('{}') is None


def test_object_is_kept():
    assert rp.parse('{"reasoning_effort": "none"}') == {'reasoning_effort': 'none'}


@pytest.mark.parametrize('text, says', [
    ('{"reasoning_effort": ', 'not valid JSON'),
    ('["none"]', 'JSON object'),
    ('"none"', 'JSON object'),
    ('{"temperature": 0.2}', 'temperature'),
    ('{"Model": "other"}', 'Model'),
    ('{"keep_alive": -1}', 'keep_alive'),
    ('{"think": null}', 'null'),
    ('{"x": "' + 'a' * 2100 + '"}', '2000'),
])
def test_refused_with_a_reason(text, says):
    with pytest.raises(ValueError, match=says):
        rp.parse(text)


def test_step_may_use_null_and_text_is_read():
    assert rp.check({'reasoning_effort': None}, allow_null=True) == {'reasoning_effort': None}
    assert rp.check('{"reasoning_effort": "low"}', allow_null=True) == {'reasoning_effort': 'low'}
    with pytest.raises(ValueError, match='not valid JSON'):
        rp.check('{reasoning_effort: low}', allow_null=True)


def test_merge_step_replaces_and_null_removes():
    model = {'reasoning_effort': 'none', 'top_k': 20}
    assert rp.merged(model, None) == model
    assert rp.merged(model, {'reasoning_effort': 'low'}) == {'reasoning_effort': 'low', 'top_k': 20}
    assert rp.merged(model, {'reasoning_effort': None}) == {'top_k': 20}
    assert rp.merged(None, {'reasoning_effort': None}) == {}
    assert model == {'reasoning_effort': 'none', 'top_k': 20}


def test_unreadable_stored_value_loads_as_empty():
    assert rp.load(None) == {} and rp.load('not json') == {} and rp.load('{"model": "x"}') == {}


def test_inference_merges_model_and_step():
    from app.services.pipeline.nodes.inference import _request_params
    model = SimpleNamespace(request_params='{"reasoning_effort": "none"}')
    assert _request_params(model, {}) == {'reasoning_effort': 'none'}
    assert _request_params(model, {'request_params': {'reasoning_effort': 'high'}}) == {'reasoning_effort': 'high'}
    assert _request_params(model, {'request_params': {'reasoning_effort': None}}) == {}
    assert _request_params(SimpleNamespace(request_params=None), {}) == {}


def test_inference_ignores_a_bad_step_value():
    from flask import Flask
    from app.services.pipeline.nodes.inference import _request_params
    model = SimpleNamespace(request_params='{"reasoning_effort": "none"}')
    with Flask(__name__).app_context():
        assert _request_params(model, {'request_params': {'messages': []}}) == {'reasoning_effort': 'none'}


def _sent(**kwargs):
    from app.services.ai_providers.openai_compatible import OpenAICompatibleProvider
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))],
                            model='m', usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    client = mock.MagicMock()
    client.chat.completions.create.return_value = reply
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.base_url, provider.api_key, provider.model_id = 'http://localhost/v1', None, 'm'
    with mock.patch('openai.OpenAI', return_value=client):
        provider.generate('An invented question.', **kwargs)
    return client.chat.completions.create.call_args.kwargs


def test_provider_sends_params_in_the_body():
    sent = _sent(request_params={'reasoning_effort': 'none'})
    assert sent['extra_body'] == {'reasoning_effort': 'none'}
    assert sent['model'] == 'm'


def test_provider_keeps_keep_alive_and_sends_nothing_extra_by_default():
    assert _sent(keep_alive=-1, request_params={'reasoning_effort': 'low'})['extra_body'] == \
        {'reasoning_effort': 'low', 'keep_alive': -1}
    assert 'extra_body' not in _sent()


def _result(message, usage):
    from app.services.ai_providers.openai_compatible import OpenAICompatibleProvider
    reply = SimpleNamespace(choices=[SimpleNamespace(message=message)], model='m', usage=usage)
    client = mock.MagicMock()
    client.chat.completions.create.return_value = reply
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.base_url, provider.api_key, provider.model_id = 'http://localhost/v1', None, 'm'
    with mock.patch('openai.OpenAI', return_value=client):
        return provider.generate('An invented question.')


def test_reasoning_length_kept_not_its_text():
    r = _result(SimpleNamespace(content='391.', reasoning='Seventeen times twenty is 340...'),
                SimpleNamespace(prompt_tokens=5, completion_tokens=40))
    assert r.reasoning_chars == len('Seventeen times twenty is 340...')
    assert r.reasoning_tokens is None
    assert 'Seventeen' not in repr(r)


def test_reasoning_content_and_reported_tokens():
    usage = SimpleNamespace(prompt_tokens=5, completion_tokens=40,
                            completion_tokens_details=SimpleNamespace(reasoning_tokens=31))
    r = _result(SimpleNamespace(content='391.', reasoning_content='abc'), usage)
    assert (r.reasoning_chars, r.reasoning_tokens) == (3, 31)


def test_no_reasoning():
    r = _result(SimpleNamespace(content='391.'), SimpleNamespace(prompt_tokens=5, completion_tokens=2))
    assert (r.reasoning_chars, r.reasoning_tokens) == (0, None)
