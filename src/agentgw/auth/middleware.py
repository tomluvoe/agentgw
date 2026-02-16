"""Authentication middleware for API endpoints."""

from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication on protected endpoints.

    Set AGENTGW_API_KEY environment variable to enable authentication.
    If not set, authentication is disabled (open access).

    Public endpoints (no auth required):
    - GET /
    - GET /static/*
    - GET /health
    - GET /docs (Swagger UI)
    - GET /openapi.json
    """

    PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self._api_key = api_key or os.environ.get("AGENTGW_API_KEY")
        if self._api_key:
            logger.info("API key authentication enabled")
        else:
            logger.warning("API key authentication DISABLED - set AGENTGW_API_KEY to enable")

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip auth if no API key configured
        if not self._api_key:
            return await call_next(request)

        # Allow public paths
        if request.url.path in self.PUBLIC_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            # For HTML requests (browser), redirect to login or show friendly error
            if "text/html" in request.headers.get("Accept", ""):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. Set Authorization header with API key.",
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = auth_header

        # Validate token
        if token != self._api_key:
            logger.warning("Invalid API key attempt from %s", request.client.host if request.client else "unknown")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )

        return await call_next(request)


def verify_api_key(credentials: HTTPAuthorizationCredentials | None = None) -> bool:
    """Dependency for protecting individual endpoints with API key auth.

    Usage:
        @app.get("/protected")
        async def protected_endpoint(auth: bool = Depends(verify_api_key)):
            return {"message": "Access granted"}
    """
    api_key = os.environ.get("AGENTGW_API_KEY")

    # If no API key configured, allow access
    if not api_key:
        return True

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return True
