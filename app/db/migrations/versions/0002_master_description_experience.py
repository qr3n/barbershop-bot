"""master description + experience

Revision ID: 0002_master_desc_exp
Revises: 0001_init
Create Date: 2026-01-27

"""
from __future__ import annotations

from alembic import op


# NOTE: revision id must fit into alembic_version.version_num (usually VARCHAR(32)).
revision = "0002_master_desc_exp"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for safety if previous attempt added columns but failed before updating alembic_version.
    op.execute('ALTER TABLE masters ADD COLUMN IF NOT EXISTS description VARCHAR(2000)')
    op.execute('ALTER TABLE masters ADD COLUMN IF NOT EXISTS experience_years INTEGER')


def downgrade() -> None:
    op.execute('ALTER TABLE masters DROP COLUMN IF EXISTS experience_years')
    op.execute('ALTER TABLE masters DROP COLUMN IF EXISTS description')
