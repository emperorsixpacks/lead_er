import hmac
import hashlib


def sign(payload: bytes, secret: bytes) -> str:
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify(payload: bytes, signature: str, secret: bytes) -> bool:
    return hmac.compare_digest(signature, sign(payload, secret))
