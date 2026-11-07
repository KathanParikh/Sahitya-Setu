"""Who is calling, and how much they may do.

Supabase Auth handles accounts, passwords and tokens. Each request carries the
token the user got at sign-in, and Supabase confirms it, so a deleted account or
a revoked session stops working at once.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False, description="The access token from Supabase sign-in")


def current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> str:
    """The signed-in user's id, or a 401."""
    unauthorized = HTTPException(401, "Please sign in.", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        response = httpx.get(
            f"{config.SUPABASE_URL}/auth/v1/user",
            headers={"apikey": config.SUPABASE_SECRET,
                     "Authorization": f"Bearer {credentials.credentials}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.error("Could not reach Supabase Auth: %s", exc)
        raise HTTPException(503, "Sign-in could not be checked. Please try again.")
    if response.status_code in (400, 401, 403):
        raise unauthorized
    if response.status_code != 200:
        logger.error("Supabase Auth returned %s", response.status_code)
        raise HTTPException(503, "Sign-in could not be checked. Please try again.")
    return response.json()["id"]


# All users share one free LLM quota, so one person must not be able to use it
# up. Counts live in memory, which is enough for a single server process.
_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()
_WINDOW_SECONDS = 3600


def check_limit(user_id: str, action: str, per_hour: int) -> None:
    """Count one use of an action, or raise a 429 if the hourly limit is reached."""
    now = time.monotonic()
    with _hits_lock:
        hits = _hits[(user_id, action)]
        while hits and now - hits[0] >= _WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= per_hour:
            minutes = int((_WINDOW_SECONDS - (now - hits[0])) // 60) + 1
            raise HTTPException(
                429,
                f"Hourly limit reached. Please try again in about {minutes} minutes.",
                headers={"Retry-After": str(minutes * 60)},
            )
        hits.append(now)
