"""master photo path

Revision ID: 0003_master_photo_path
Revises: 0002_master_desc_exp
Create Date: 2026-01-27

"""
from __future__ import annotations

from alembic import op

# NOTE: revision id must fit into alembic_version.version_num (usually VARCHAR(32)).
revision = "0003_master_photo_path"
down_revision = "0002_master_desc_exp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for safety if previous attempt added column but failed before updating alembic_version.
    op.execute('ALTER TABLE masters ADD COLUMN IF NOT EXISTS photo_path VARCHAR(500)')


def downgrade() -> None:
    op.execute('ALTER TABLE masters DROP COLUMN IF EXISTS photo_path')
