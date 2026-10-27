import json
from pathlib import Path

import httpx
import pytest

from app.gateway_ocr import GatewayScanner, GatewayRecognitionError
from app.recognition import parse_texts


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
