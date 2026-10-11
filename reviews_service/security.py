"""Hashing, tokens, one-time codes, form timing and rate limits. Nothing here stores a plain email or IP."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

CODE_TTL_MINUTES = 15
DRAFT_TTL_MINUTES = 60
MAX_CODE_ATTEMPTS = 5
MAX_RESENDS = 3
RESEND_COOLDOWN = 60
FORM_MIN_AGE = 8           # seconds: a person needs longer than this to fill the form
FORM_MAX_AGE = 4 * 3600


class Keys:
    def __init__(self, secret: str):
        self._key = secret.encode()

    def _mac(self, label: str, value: str) -> str:
        return hmac.new(self._key, f"{label}:{value}".encode(), hashlib.sha256).hexdigest()

    def email(self, normalized_email: str) -> str:
        return self._mac("email", normalized_email)

    def ip(self, address: str) -> str:
        return self._mac("ip", address) if address else ""

    def token(self, token: str) -> str:
        return self._mac("token", token)

    def code(self, token_hash: str, code: str) -> str:
        return self._mac("code", f"{token_hash}:{code}")

    def form_token(self, now: Optional[float] = None) -> str:
        stamp = str(int(now if now is not None else time.time()))
        return f"{stamp}.{self._mac('form', stamp)[:32]}"

    def form_token_ok(self, token: str, now: Optional[float] = None) -> bool:
        """Issued by us, at least FORM_MIN_AGE seconds ago and not stale. Stops scripts that post without waiting."""
        try:
            stamp, mac = str(token).split(".", 1)
            age = (now if now is not None else time.time()) - int(stamp)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(mac, self._mac("form", stamp)[:32]) and FORM_MIN_AGE <= age <= FORM_MAX_AGE


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a), str(b))


class RateLimiter:
    """Sliding window per key, in memory only. Keys are hashed before use, so memory never holds an IP or email."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        bucket = self.hits[hashlib.sha256(key.encode()).hexdigest()]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        if len(self.hits) > 50_000:  # never grow without bound
            for stale in [k for k, b in self.hits.items() if not b or now - b[-1] > self.window][:10_000]:
                del self.hits[stale]
        return True


def client_ip(request) -> str:
    """Caddy (the only thing that reaches us) replaces X-Forwarded-For with the real peer; take the last entry."""
    forwarded = [part.strip() for part in request.headers.get("X-Forwarded-For", "").split(",") if part.strip()]
    return forwarded[-1] if forwarded else (request.remote or "")
