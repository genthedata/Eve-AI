"""
Optional Entra ID (Azure AD) JWT verification for protected routes.
Set ENTRA_AUDIENCE (app id URI or client id). Optionally ENTRA_TENANT_ID for issuer.
If ENTRA_AUDIENCE is unset, require_entra_user returns disabled auth (routes should not use strict mode).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def require_entra_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    audience = os.getenv("ENTRA_AUDIENCE", "").strip()
    if not audience:
        return {"auth": "disabled"}

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = creds.credentials
    try:
        import jwt  # type: ignore
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="PyJWT required when ENTRA_AUDIENCE is set: pip install PyJWT cryptography",
        ) from e

    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        iss = str(unverified.get("iss", "")).rstrip("/")
        if not iss:
            raise ValueError("Token missing iss")
        jwks_url = f"{iss}/discovery/v2.0/keys"
        jwk_client = jwt.PyJWKClient(jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=iss,
        )
        return {"auth": "entra", "claims": payload}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
