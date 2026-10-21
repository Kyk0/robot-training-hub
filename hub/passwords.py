"""Salted scrypt passwords; only hashes are persisted in the database."""

import hashlib
import hmac
import secrets


def hash_password(password):
    if not 12 <= len(password) <= 256:
        raise ValueError("Use a password with 12 to 256 characters")
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()
    return f"scrypt$16384$8$1${salt}${result}"


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt" or (n, r, p) != ("16384", "8", "1"):
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
