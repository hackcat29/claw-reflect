"""Widen id and agent_id columns from 26 to 128 characters.

The columns were sized for 26-character ULIDs, but memory ids from ClawDB are
36-character UUIDs (and request validation allows up to 128 characters), so
every memory upsert failed on PostgreSQL with "value too long for type
character varying(26)".

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# (table, columns). reflection_jobs.id is referenced by reflection_results.job_id;
# PostgreSQL rebuilds that foreign key when both sides are altered together.
COLUMNS = (
    ("memory_records", ("id", "agent_id")),
    ("reflection_jobs", ("id", "agent_id")),
    ("reflection_results", ("id", "job_id", "memory_id")),
    ("extracted_preferences", ("id", "agent_id")),
    ("agent_profiles", ("agent_id",)),
    ("contradiction_records", ("id", "agent_id", "memory_id_a", "memory_id_b", "winner_memory_id")),
    ("decay_records", ("id", "memory_id", "agent_id")),
)


def _alter(length_from: int, length_to: int) -> None:
    for table, columns in COLUMNS:
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.String(length_from),
                type_=sa.String(length_to),
                existing_nullable=column == "winner_memory_id",
            )


def upgrade() -> None:
    # SQLite (used by the tests) does not enforce string lengths.
    if op.get_bind().dialect.name == "postgresql":
        _alter(26, 128)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _alter(128, 26)
