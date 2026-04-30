"""
API 키 암호화/복호화 - Fernet (AES-128-CBC + HMAC-SHA256).
SECRET_KEY에서 32바이트 키를 파생해 사용.
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from .config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        settings = get_settings()
        # SECRET_KEY → SHA-256 → base64url → Fernet key
        raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(raw)
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """평문 문자열 → 암호화된 문자열 (base64url)"""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """암호화된 문자열 → 평문 문자열"""
    if not ciphertext:
        return ""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask(plaintext: str, visible: int = 4) -> str:
    """API 키 마스킹 표시용: 앞 4자만 보이고 나머지 *"""
    if not plaintext or len(plaintext) <= visible:
        return "****"
    return plaintext[:visible] + "*" * (len(plaintext) - visible)
