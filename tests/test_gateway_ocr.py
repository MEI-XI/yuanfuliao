import json
from pathlib import Path

import httpx
import pytest

from app import gateway_ocr
from app.gateway_ocr import GatewayScanner, GatewayRecognitionError
from app.recognition import CloudRecognitionError, cloud_extract, parse_texts


def test_gateway_reads_image_and_returns_evidence_for_existing_field_parser():
    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == '/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer test-only-key'
        assert body['model'] == 'PaddleOCR-VL-1.5-0.9B'
        assert body['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        return httpx.Response(200, json={'choices': [{'message': {'content': '品名：甘氨酸\n生产日期：2026.01.14\n保质期：12个月'}, 'finish_reason': 'stop'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = GatewayScanner('http://gateway.test/v1', 'PaddleOCR-VL-1.5-0.9B', 'test-only-key', client=client)(Path('tests/fixtures/label.png'))
    assert result['boxes'] == []
    assert result['provider'] == 'PaddleOCR-VL-1.5-0.9B'
    assert parse_texts(result['texts'])['material_name'] == '甘氨酸'
    assert parse_texts(result['texts'])['production_dates'] == ['2026-01-14']


@pytest.mark.parametrize('status,body', [(401, {'error': 'test-only-key'}), (200, {'choices': []}), (200, {'choices': [{'message': {'content': 'partial'}, 'finish_reason': 'length'}]})])
def test_gateway_failures_never_expose_credentials_or_accept_truncation(status, body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))) as client:
        with pytest.raises(GatewayRecognitionError) as error:
            GatewayScanner('http://gateway.test/v1', 'PaddleOCR-VL-1.5-0.9B', 'test-only-key', client=client)(Path('tests/fixtures/label.png'))
    assert 'test-only-key' not in str(error.value)


def test_auxiliary_uses_deepseek_without_thinking_by_default(monkeypatch):
    real_client = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == 'http://gateway.test/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer test-only-key'
        assert body['model'] == 'deepseek-flash'
        assert body['thinking'] == {'type': 'disabled'}
        assert 'reasoning_effort' not in body
        assert body['max_tokens'] == 4096
        assert request.extensions['timeout']['read'] == 45
        assert body['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"material_name":"甘氨酸"}'}, 'finish_reason': 'stop'}]})

    def make_client(**kwargs):
        assert kwargs['trust_env'] is False
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, 'Client', make_client)
    fields = cloud_extract([Path('tests/fixtures/label.png')], [['品名：甘氨酸']], 'test-only-key', base_url='http://gateway.test/v1/')
    assert fields['material_name'] == '甘氨酸'


def test_auxiliary_low_thinking_reserves_enough_output_and_time(monkeypatch):
    real_client = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        assert body['thinking'] == {'type': 'enabled'}
        assert body['reasoning_effort'] == 'low'
        assert body['max_tokens'] == 16384
        assert request.extensions['timeout']['read'] == 120
        assert request.extensions['timeout']['connect'] == 10
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"material_name":"甘氨酸"}', 'reasoning_content': 'internal reasoning'}, 'finish_reason': 'stop'}]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    fields = cloud_extract([], [['品名：甘氨酸']], 'test-only-key', base_url='http://gateway.test/v1', thinking_mode='low')
    assert fields['material_name'] == '甘氨酸'
    assert 'reasoning_content' not in fields


def test_auxiliary_shares_external_credentials_without_changing_base_model(tmp_path, monkeypatch):
    config_path = tmp_path / 'ocr-gateway.json'
    original = json.dumps({'base_url': 'http://gateway.test/v1', 'model': 'PaddleOCR-VL-1.5-0.9B', 'protected_key': 'protected-test-only'})
    config_path.write_text(original, encoding='utf-8')
    monkeypatch.setenv('OCR_GATEWAY_CONFIG', str(config_path))
    monkeypatch.setattr(gateway_ocr, 'decrypt_gateway_key', lambda path: 'test-only-key', raising=False)
    models = []
    real_client = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        models.append(body['model'])
        assert request.headers['authorization'] == 'Bearer test-only-key'
        content = '品名：甘氨酸' if body['model'].startswith('Paddle') else '{"material_name":"甘氨酸"}'
        return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    auxiliary = gateway_ocr.configured_auxiliary()
    assert auxiliary([], [['品名：甘氨酸']])['material_name'] == '甘氨酸'
    base = gateway_ocr.configured_scanner()(Path('tests/fixtures/label.png'))
    assert base['provider'] == 'PaddleOCR-VL-1.5-0.9B'
    assert models == ['deepseek-flash', 'PaddleOCR-VL-1.5-0.9B']
    assert config_path.read_text(encoding='utf-8') == original
    status = gateway_ocr.auxiliary_status()
    assert status == {'configured': True, 'provider': 'DeepSeek', 'model': 'deepseek-flash', 'default_thinking': 'disabled'}


def test_auxiliary_rejects_truncated_output_even_when_partial_json_is_valid(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': '{"material_name":"甘氨酸"}'}, 'finish_reason': 'length'}]})), **kwargs))
    with pytest.raises(CloudRecognitionError, match='截断'):
        cloud_extract([], [['品名：甘氨酸']], 'test-only-key', base_url='http://gateway.test/v1', thinking_mode='low')
