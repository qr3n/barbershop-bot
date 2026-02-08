"""Bot settings and logs tables

Revision ID: 0004
Revises: 0003_master_photo_path
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003_master_photo_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create bot_settings table
    op.create_table(
        'bot_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bot_token', sa.String(200), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create bot_logs table
    op.create_table(
        'bot_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('level', sa.Enum('info', 'warning', 'error', name='botloglevel'), nullable=False, server_default='info'),
        sa.Column('message', sa.String(1000), nullable=False),
        sa.Column('details', sa.String(5000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )
    
    op.create_index('ix_bot_logs_created_at', 'bot_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_bot_logs_created_at', table_name='bot_logs')
    op.drop_table('bot_logs')
    op.drop_table('bot_settings')
    op.execute('DROP TYPE IF EXISTS botloglevel')
