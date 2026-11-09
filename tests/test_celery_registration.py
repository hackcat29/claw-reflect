"""A standalone worker (celery -A claw_reflect.workers.celery_app worker) must know every task."""

from __future__ import annotations

from claw_reflect.workers.celery_app import celery_app

TASKS = (
    "claw_reflect.workers.tasks.reflect.reflect_agent_task",
    "claw_reflect.workers.tasks.reflect.full_reflection_task",
    "claw_reflect.workers.tasks.decay.decay_stale_task",
    "claw_reflect.workers.tasks.score.rescore_memories_task",
    "claw_reflect.workers.tasks.profile.update_profile_task",
)


def test_worker_registers_every_task_without_importing_them_elsewhere():
    # What a worker process does at startup: load only the app's configured modules.
    celery_app.loader.import_default_modules()
    missing = [name for name in TASKS if name not in celery_app.tasks]
    assert not missing, f"worker would reject these tasks: {missing}"


def test_every_scheduled_task_is_registered():
    celery_app.loader.import_default_modules()
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert scheduled <= set(celery_app.tasks), scheduled - set(celery_app.tasks)
