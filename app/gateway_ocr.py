"""OpenAI-compatible OCR gateway. Credentials stay in an external user config."""
import base64
import json
import os
import re
import subprocess
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps


class GatewayRecognitionError(RuntimeError):
    pass


def configured_scanner():
    from app.recognition import LocalScanner
    default = Path(os.getenv('LOCALAPPDATA', str(Path.home() / '.config'))) / 'Yuanfuliao' / 'ocr-gateway.json'
    path = Path(os.getenv('OCR_GATEWAY_CONFIG', str(default)))
    if not path.exists():
        return LocalScanner()
    return ConfiguredGatewayScanner(path)


class ConfiguredGatewayScanner:
    def __init__(self, path):
        self.path = path

    def __call__(self, image_path):
        try:
            config = json.loads(self.path.read_text(encoding='utf-8-sig'))
            # Windows DPAPI binds this ciphertext to the service user's account.
            # Capture stdout privately; never log the command result or config.
            command = "$c = Get-Content -LiteralPath $env:YFL_OCR_CONFIG -Raw | ConvertFrom-Json; $p = New-Object System.Management.Automation.PSCredential('gateway', (ConvertTo-SecureString $c.protected_key)); [Console]::Write($p.GetNetworkCredential().Password)"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                    env={**{key: value for key, value in os.environ.items() if key.upper() != 'PSMODULEPATH'}, 'YFL_OCR_CONFIG': str(self.path)}, capture_output=True,
                                    timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode or not result.stdout:
                raise ValueError('credential unavailable')
            key = result.stdout.decode('utf-8').strip()
            scanner = GatewayScanner(config['base_url'], config['model'], key)
        except Exception:
            raise GatewayRecognitionError('OCR 网关配置无法读取，请检查运行服务的 Windows 账号及本机加密配置') from None
        return scanner(image_path)


class GatewayScanner:
    def __init__(self, base_url, model, api_key, *, client=None):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._api_key = api_key
        self._client = client

    def __call__(self, path):
        with Image.open(path) as original:
            picture = ImageOps.exif_transpose(original).convert('RGB')
            picture.thumbnail((2400, 2400))
            image = BytesIO()
            picture.save(image, format='JPEG', quality=95)
        payload = {'model': self.model, 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'OCR:'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image.getvalue()).decode('ascii')}}]}],
            'temperature': 0, 'max_tokens': 4096, 'stream': False}
        client = self._client or httpx.Client(timeout=httpx.Timeout(180, connect=10), trust_env=False)
        try:
            response = client.post(self.base_url + '/chat/completions', headers={'Authorization': 'Bearer ' + self._api_key}, json=payload)
            if response.status_code != 200:
                raise GatewayRecognitionError(f'OCR 网关请求失败（HTTP {response.status_code}），请检查网关服务或密钥配置')
            try:
                choice = response.json()['choices'][0]
                content = choice['message']['content']
                if isinstance(content, list):
                    content = '\n'.join(part['text'] for part in content if part.get('type') == 'text')
                if not isinstance(content, str) or not content.strip() or choice.get('finish_reason') == 'length':
                    raise ValueError('incomplete content')
            except (KeyError, IndexError, TypeError, ValueError):
                raise GatewayRecognitionError('OCR 网关返回为空、格式不正确或结果被截断，请重试') from None
            # Preserve raw text as evidence; remove Markdown table separators for the existing parser.
            texts = [re.sub(r'^#+\s*', '', line.strip()).replace('**', '') for line in content.splitlines() if line.strip()]
            texts = [re.sub(r'\s*\|\s*', '：', line.strip('| ')) if '|' in line else line for line in texts if not re.fullmatch(r'[\s|:\-]+', line)]
            return {'texts': texts, 'boxes': [], 'rotation': 0, 'provider': self.model, 'raw_text': content}
        except httpx.HTTPError:
            raise GatewayRecognitionError('OCR 网关连接失败或响应超时，请检查内网连接与网关服务') from None
        finally:
            if self._client is None:
                client.close()
