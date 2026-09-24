import hmac
import os
from typing import Optional

import jwt


def verify_internal_request(authorization: Optional[str], body: bytes) -> None:
    _ = body
    secret = os.environ.get("INTERNAL_JOB_SECRET", "").strip()
    if not secret:
        raise PermissionError("INTERNAL_JOB_SECRET not configured")

    auth = (authorization or "").strip()
    if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), secret):
        return

    current = os.environ.get("QSTASH_CURRENT_SIGNING_KEY", "").strip()
    next_key = os.environ.get("QSTASH_NEXT_SIGNING_KEY", "").strip()
    if auth.startswith("Bearer ") and current:
        token = auth[7:].strip()
        for key in (current, next_key):
            if not key:
                continue
            try:
                jwt.decode(token, key, algorithms=["HS256"])
                return
            except jwt.PyJWTError:
                continue

    raise PermissionError("Unauthorized internal job request")
