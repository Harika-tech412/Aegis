"""Shared slowapi limiter (own module so routers and main can both import it)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

SCORE_LIMIT = "30/minute"  # per client IP - generous for a demo, blocks abuse
LOGIN_LIMIT = "5/minute"  # per client IP - brute-force protection
