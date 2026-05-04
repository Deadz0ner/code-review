"""Token verification.

Simple HMAC check against a per-user expected token. The comparison is the
sensitive part — the agent should notice a constant-time-comparison issue here
even though bandit does not flag it.
"""
import hashlib

from config import SECRET_KEY


def expected_token(user_id):
    raw = (user_id + ":" + SECRET_KEY).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_token(user_id, token):
    if not user_id or not token:
        return False
    expected = expected_token(user_id)
    return token == expected
