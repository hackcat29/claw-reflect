"""The reflection task must update the job row the API returned to the caller."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from claw_reflect.db.base import Base
from claw_reflect.models.reflection import ReflectionJob
from claw_reflect.workers.tasks import reflect as tasks


class _FakePipeline:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def run(self, ctx):
        return SimpleNamespace(total_processed=3, total_updated=2, total_archived=1)


def _setup(tmp_path, monkeypatch, existing: ReflectionJob | None):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/reflect.db", poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        if existing is not None:
            async with factory() as session:
                session.add(existing)
                await session.commit()

    asyncio.run(prepare())
    monkeypatch.setattr(tasks, "session_factory", factory)
    monkeypatch.setattr(tasks, "_build_llm_adapter", lambda: object())
    monkeypatch.setattr(tasks, "FullReflectionPipeline", _FakePipeline)

    async def rows() -> list[ReflectionJob]:
        async with factory() as session:
            return list((await session.execute(select(ReflectionJob))).scalars())

    return lambda: asyncio.run(rows())


def test_task_completes_the_row_it_was_given(tmp_path, monkeypatch):
    ws = uuid.uuid4()
    row = ReflectionJob(id="JOB-FROM-API", workspace_id=ws, agent_id="a", status="pending", job_type="full")
    rows = _setup(tmp_path, monkeypatch, row)

    tasks.reflect_agent_task.apply(args=(str(ws), "a", "full", {}, "JOB-FROM-API")).get()

    jobs = rows()
    assert len(jobs) == 1, "no second row may be created"
    assert jobs[0].id == "JOB-FROM-API"
    assert jobs[0].status == "completed"
    assert jobs[0].memories_processed == 3 and jobs[0].memories_updated == 2


def test_task_does_not_adopt_another_workspaces_job(tmp_path, monkeypatch):
    other = ReflectionJob(id="OTHER-JOB", workspace_id=uuid.uuid4(), agent_id="a", status="pending", job_type="full")
    rows = _setup(tmp_path, monkeypatch, other)

    tasks.reflect_agent_task.apply(args=(str(uuid.uuid4()), "a", "full", {}, "OTHER-JOB")).get()

    by_id = {job.id: job for job in rows()}
    assert by_id["OTHER-JOB"].status == "pending", "another workspace's job is left alone"
    assert len(by_id) == 2 and any(job.status == "completed" for job in by_id.values())


def test_scheduler_style_call_creates_a_row(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch, None)

    tasks.reflect_agent_task.apply(args=(str(uuid.uuid4()), "a")).get()

    jobs = rows()
    assert len(jobs) == 1 and jobs[0].status == "completed"
