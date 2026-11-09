"""Platform admin routes: mint workspace API keys for the hosting platform.

Mounted at /admin, outside /api/v1, so the workspace API-key middleware does
not apply. Every request needs `Authorization: Bearer <REFLECT_ADMIN_TOKEN>`.
With no admin token configured the routes don't exist (404), so a default
deployment exposes nothing new.
"""

from __future__ import annotations

import base64
import hmac
import secrets
import uuid

from blake3 import blake3
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from claw_reflect.config import Settings
from claw_reflect.db.session import session_factory
from claw_reflect.models.api_key import ApiKey

router = APIRouter()


class CreateApiKeyBody(BaseModel):
    workspace_id: uuid.UUID
    label: str | None = Field(default=None, max_length=200)


class CreatedApiKey(BaseModel):
    api_key: str
    id: uuid.UUID
    workspace_id: uuid.UUID


def require_admin(request: Request) -> None:
    settings = Settings()  # type: ignore[call-arg]
    expected = settings.admin_token.get_secret_value() if settings.admin_token else ""
    if not expected:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    header = request.headers.get("authorization", "")
    provided = header[len("Bearer ") :] if header.startswith("Bearer ") else ""
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})


@router.post("/api-keys", response_model=CreatedApiKey, status_code=201, dependencies=[Depends(require_admin)])
async def create_api_key(body: CreateApiKeyBody) -> CreatedApiKey:
    """Create a key bound to one workspace. The raw key is returned once."""
    raw_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    row = ApiKey(key_hash=blake3(raw_key.encode("utf-8")).hexdigest(), workspace_id=body.workspace_id, label=body.label)
    async with session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return CreatedApiKey(api_key=raw_key, id=row.id, workspace_id=row.workspace_id)
