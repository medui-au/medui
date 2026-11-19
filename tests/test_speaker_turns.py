"""Deepgram speaker turns, its Base URL and ASR request parameters (ADR-151).

No database, no network: replies are invented, requests are mocked.
"""
from types import SimpleNamespace
from unittest import mock

import pytest
from flask import Flask

from app.services import request_params as rp
from app.services.ai_providers.asr import (DeepgramProvider, WhisperProvider, deepgram_root,
                                           deepgram_turns)


def _reply(paragraphs, diarized=True, transcript='plain text'):
    body = {'results': {'channels': [{'alternatives': [{
        'transcript': transcript,
        'paragraphs': {'transcript': '…', 'paragraphs': paragraphs}}]}]},
        'metadata': {}}
    if diarized:
        body['metadata']['diarize_info'] = {'model_uuid': 'x', 'arch': 'v2'}
    return body


def _para(speaker, *sentences):
    p = {'sentences': [{'text': s} for s in sentences]}
    if speaker is not None:
        p['speaker'] = speaker
    return p


# ── Base URL ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('stored, root', [
    ('https://api.au.deepgram.com', 'https://api.au.deepgram.com'),
    ('https://api.au.deepgram.com/', 'https://api.au.deepgram.com'),
    ('https://api.deepgram.com/v1/listen', 'https://api.deepgram.com'),   # as older installs saved it
    ('', 'https://api.deepgram.com'),
    (None, 'https://api.deepgram.com'),
    ('api.au.deepgram.com', 'https://api.deepgram.com'),                  # no scheme: not a URL
])
def test_base_url_root(stored, root):
    assert deepgram_root(stored) == root


# ── Reading the reply ─────────────────────────────────────────────────────────

def test_turns_numbered_from_one_and_joined():
    body = _reply([_para(0, 'How long has it hurt?'), _para(1, 'Two weeks.', 'Mostly at night.'),
                   _para(1, 'Worse lying down.'), _para(0, 'Any fever?')])
    assert deepgram_turns(body) == ('[Speaker 1] How long has it hurt?\n'
                                    '[Speaker 2] Two weeks. Mostly at night. Worse lying down.\n'
                                    '[Speaker 1] Any fever?')


def test_one_speaker_is_still_turns():
    assert deepgram_turns(_reply([_para(0, 'Just me talking.')])) == '[Speaker 1] Just me talking.'


@pytest.mark.parametrize('body', [
    _reply([_para(0, 'Hello.')], diarized=False),      # no speaker model ran
    _reply([_para(None, 'Hello.')]),                   # paragraphs without speakers
    _reply([]),                                        # nothing said
    {'results': {}, 'metadata': {'diarize_info': {}}},
])
def test_no_turns(body):
    assert deepgram_turns(body) is None


# ── The request ───────────────────────────────────────────────────────────────

def _deepgram(base_url, body, **kwargs):
    provider = DeepgramProvider(model_id='nova-3', api_key='invented', base_url=base_url)
    resp = mock.Mock(ok=True, status_code=200)
    resp.json.return_value = body
    with mock.patch('requests.post', return_value=resp) as post:
        result = provider.transcribe(b'RIFF', **kwargs)
    return post.call_args, result


def test_today_request_is_unchanged():
    call, result = _deepgram(None, _reply([_para(0, 'x')], diarized=False))
    assert call.args[0] == 'https://api.deepgram.com/v1/listen'
    assert call.kwargs['params'] == {'smart_format': 'true', 'model': 'nova-3', 'language': 'en'}
    assert result.text == 'plain text' and result.speaker_turns is False


def test_au_endpoint_and_speaker_turns():
    call, result = _deepgram('https://api.au.deepgram.com',
                             _reply([_para(0, 'Hi.'), _para(1, 'Hello.')]), speaker_turns='latest')
    assert call.args[0] == 'https://api.au.deepgram.com/v1/listen'
    q = call.kwargs['params']
    assert q['diarize_model'] == 'latest' and q['paragraphs'] == 'true'
    assert 'diarize' not in q                       # Deepgram refuses both together
    assert result.speaker_turns is True
    assert result.text == '[Speaker 1] Hi.\n[Speaker 2] Hello.'


def test_turns_asked_but_none_returned_falls_back_to_text():
    _, result = _deepgram(None, _reply([_para(0, 'x')], diarized=False), speaker_turns='v2')
    assert result.text == 'plain text' and result.speaker_turns is False


def test_unknown_version_is_not_sent():
    call, _ = _deepgram(None, _reply([], diarized=False), speaker_turns='v9')
    assert 'diarize_model' not in call.kwargs['params']


def test_params_sent_and_medui_keys_win():
    call, _ = _deepgram(None, _reply([], diarized=False),
                        params={'numerals': True, 'smart_format': False, 'model': 'other'})
    q = call.kwargs['params']
    assert q['numerals'] == 'true' and q['smart_format'] == 'false' and q['model'] == 'nova-3'


def test_deepgram_error_names_the_problem():
    provider = DeepgramProvider(model_id='nova-3', api_key='invented')
    resp = mock.Mock(ok=False, status_code=400, text='{"err_code":"INVALID_QUERY_PARAMETER"}')
    with mock.patch('requests.post', return_value=resp), \
            pytest.raises(RuntimeError, match='Deepgram 400.*INVALID_QUERY_PARAMETER'):
        provider.transcribe(b'RIFF')


def test_whisper_gets_params_as_form_fields():
    provider = WhisperProvider(model_id='WhisperX_local', base_url='http://whisper.invalid:9000/')
    resp = mock.Mock(ok=True)
    resp.json.return_value = {'text': 'hello', 'language': 'en'}
    with mock.patch('requests.post', return_value=resp) as post:
        provider.transcribe(b'RIFF', params={'initial_prompt': 'GP consult', 'vad_filter': True,
                                             'language': 'fr'})
    data = post.call_args.kwargs['data']
    assert data == {'initial_prompt': 'GP consult', 'vad_filter': 'true', 'language': 'en'}


# ── Parameters on an ASR model ────────────────────────────────────────────────

@pytest.mark.parametrize('text', ['{"diarize": true}', '{"diarize_model": "latest"}',
                                  '{"language": "fr"}', '{"Utterances": true}'])
def test_asr_parameters_refuse_medui_keys(text):
    with pytest.raises(ValueError, match='MedUI sets these itself'):
        rp.parse(text, asr=True)


def test_asr_parameters_allow_what_chat_models_reserve():
    assert rp.parse('{"prompt": "GP consult", "keyterm": "metformin"}', asr=True) == \
        {'prompt': 'GP consult', 'keyterm': 'metformin'}


def test_for_asr_drops_medui_keys_saved_before_the_model_was_asr():
    assert rp.for_asr({'diarize': True, 'numerals': True, 'Language': 'fr'}) == {'numerals': True}
    assert rp.for_asr(None) == {}


# ── process_chunk: when the local labelling step runs ─────────────────────────

def _chunk(model, result, diarize=True, prompt=None, local=True):
    from app.services import voice_service as vs
    provider = mock.Mock()
    provider.transcribe.return_value = result
    labelled = mock.Mock(return_value='[Doctor] labelled')
    with Flask(__name__).app_context(), \
            mock.patch.object(vs.VoiceService, 'resolve_asr_model', return_value=model), \
            mock.patch('app.services.ai_providers.factory.get_provider', return_value=provider), \
            mock.patch.object(vs, '_labelling_prompt', return_value=prompt) as find_prompt, \
            mock.patch.object(vs, '_diarization_model_is_local', return_value=local), \
            mock.patch('app.services.pipeline.nodes.prompt_assembly.PromptAssemblyNode') as pa, \
            mock.patch('app.services.pipeline.nodes.inference.InferenceNode') as inf:
        ctx = SimpleNamespace(results={'final_output': '[Doctor] labelled', 'ai_responses': []})
        pa.return_value.execute.return_value = ctx
        inf.return_value.execute.return_value = ctx
        text = vs.VoiceService.process_chunk(b'RIFF', 0, diarize=diarize)
    return text, provider.transcribe.call_args.kwargs, find_prompt.called


def _model(turns=None, params=None):
    return SimpleNamespace(id=1, model_id='nova-3', request_params=params, speaker_turns=turns,
                           provider=SimpleNamespace(name='Deepgram', is_local=False,
                                                    provider_type='asr_deepgram'))


def _result(text, turns):
    from app.services.ai_providers.base import TranscribeResult
    return TranscribeResult(text=text, speaker_turns=turns)


def test_deepgram_turns_skip_the_local_step():
    text, sent, looked_up = _chunk(_model('latest'), _result('[Speaker 1] Hi.', True),
                                   prompt=SimpleNamespace(id=1, default_model_id=2))
    assert text == '[Speaker 1] Hi.' and not looked_up
    assert sent['speaker_turns'] == 'latest'


def test_without_turns_the_local_step_runs_as_before():
    text, sent, looked_up = _chunk(_model(None), _result('Hi.', False),
                                   prompt=SimpleNamespace(id=1, default_model_id=2))
    assert text == '[Doctor] labelled' and looked_up
    assert sent['speaker_turns'] is None


def test_turns_asked_but_not_returned_uses_the_local_step():
    text, _, looked_up = _chunk(_model('v2'), _result('Hi.', False),
                                prompt=SimpleNamespace(id=1, default_model_id=2))
    assert text == '[Doctor] labelled' and looked_up


def test_dictation_never_asks_for_turns():
    text, sent, looked_up = _chunk(_model('latest'), _result('Dictated.', False), diarize=False)
    assert text == 'Dictated.' and sent['speaker_turns'] is None and not looked_up


def test_model_params_reach_the_service():
    _, sent, _ = _chunk(_model(None, params='{"numerals": true, "diarize": true}'),
                        _result('Hi.', False), diarize=False)
    assert sent['params'] == {'numerals': True}


# ── The Scribe page's status line ─────────────────────────────────────────────

def _status(model, prompt=None, local=True):
    from app.services import voice_service as vs
    with Flask(__name__).app_context(), \
            mock.patch.object(vs, '_labelling_prompt', return_value=prompt), \
            mock.patch.object(vs, '_diarization_model_is_local', return_value=local):
        return vs.speaker_label_status(model)


def test_status_lines():
    prompt = SimpleNamespace(id=1, default_model_id=2)
    assert _status(_model('latest'))['kind'] == 'turns'
    assert _status(_model(None), prompt)['kind'] == 'local'
    assert 'missing' in _status(_model(None), None)['text']
    assert 'no local model' in _status(_model(None), prompt, local=False)['text']
    whisper = SimpleNamespace(speaker_turns='latest',     # a stray value on a non-Deepgram model
                              provider=SimpleNamespace(provider_type='asr_whisper'))
    assert _status(whisper, prompt)['kind'] == 'local'
