"""Tests for the platform admin routes (/admin/api-keys)."""

from __future__ import annotations

import uuid

import pytest
from blake3 import blake3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from claw_reflect.api import admin
from claw_reflect.models.api_key import ApiKey


def _use_test_db(monkeypatch, async_session) -> None:
    factory = async_sessionmaker(async_session.bind, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(admin, "session_factory", factory)


@pytest.mark.asyncio
async def test_disabled_without_admin_token(client, monkeypatch):
    monkeypatch.delenv("REFLECT_ADMIN_TOKEN", raising=False)
    response = await client.post("/admin/api-keys", json={"workspace_id": str(uuid.uuid4())})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rejects_missing_or_wrong_token(client, monkeypatch):
    monkeypatch.setenv("REFLECT_ADMIN_TOKEN", "s3cret-admin-token")
    body = {"workspace_id": str(uuid.uuid4())}
    assert (await client.post("/admin/api-keys", json=body)).status_code == 401
    assert (await client.post("/admin/api-keys", json=body, headers={"authorization": "Bearer nope"})).status_code == 401


@pytest.mark.asyncio
async def test_creates_a_workspace_key_stored_as_a_hash(client, async_session, monkeypatch):
    monkeypatch.setenv("REFLECT_ADMIN_TOKEN", "s3cret-admin-token")
    _use_test_db(monkeypatch, async_session)
    workspace_id = uuid.uuid4()

    response = await client.post(
        "/admin/api-keys",
        json={"workspace_id": str(workspace_id), "label": "clawcloud instance"},
        headers={"authorization": "Bearer s3cret-admin-token"},
    )

    assert response.status_code == 201
    raw = response.json()["api_key"]
    assert response.json()["workspace_id"] == str(workspace_id)
    row = (await async_session.execute(select(ApiKey).where(ApiKey.workspace_id == workspace_id))).scalar_one()
    assert row.key_hash == blake3(raw.encode()).hexdigest()
    assert raw not in row.key_hash
