"""Reversible credentials use a server-local key, independent of password hashes."""
import os
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

_key_lock = Lock()


def credential_cipher(create=False):
    path = Path(os.getenv('DATA_DIR', 'data')) / 'credential.key'
    try:
        with _key_lock:
            if create:
                path.parent.mkdir(parents=True, exist_ok=True)
                # This application has one server process. Serialize initial creation
                # so concurrent requests cannot observe a partially written key.
                try:
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descriptor, 'wb') as output:
                        output.write(Fernet.generate_key())
            return Fernet(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, '密码查看密钥不可用，请恢复服务器密钥备份；账号仍可使用原密码登录') from exc


def encrypt_password(password):
    return credential_cipher(create=True).encrypt(password.encode('utf-8')).decode('ascii')


def decrypt_password(value):
    if not value:
        return None
    try:
        return credential_cipher().decrypt(value.encode('ascii')).decode('utf-8')
    except InvalidToken as exc:
        raise HTTPException(503, '密码查看密钥不匹配，请恢复服务器密钥备份或重新设置该账号密码') from exc
