"""
AES-256-GCM address encryption utility.
The ENCRYPTION_KEY setting must be a base64-encoded 32-byte key.
"""
import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _get_key() -> bytes | None:
    key_b64 = getattr(settings, 'ENCRYPTION_KEY', '')
    if not key_b64:
        return None
    return base64.b64decode(key_b64)


def encrypt_address(plaintext: str) -> str:
    """Encrypt a plaintext address string. Returns base64 blob (nonce + ciphertext)."""
    key = _get_key()
    if not key or not plaintext:
        return ''
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(nonce + ct).decode('ascii')


def decrypt_address(ciphertext_b64: str) -> str:
    """Decrypt an address blob produced by encrypt_address. Returns '' on any error."""
    if not ciphertext_b64:
        return ''
    key = _get_key()
    if not key:
        return ''
    try:
        data = base64.b64decode(ciphertext_b64)
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode('utf-8')
    except Exception:
        return ''
