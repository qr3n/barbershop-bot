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
    # Create bot_settings table (idempotent)
    op.execute('''
        CREATE TABLE IF NOT EXISTS bot_settings (
            id SERIAL PRIMARY KEY,
            bot_token VARCHAR(200),
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    ''')
    
    # Create enum type if not exists
    op.execute('''
        DO $$ BEGIN
            CREATE TYPE botloglevel AS ENUM ('info', 'warning', 'error');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    ''')
    
    # Create bot_logs table (idempotent)
    op.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id SERIAL PRIMARY KEY,
            level botloglevel NOT NULL DEFAULT 'info',
            message VARCHAR(1000) NOT NULL,
            details VARCHAR(5000),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    ''')
    
    # Create index (idempotent)
    op.execute('CREATE INDEX IF NOT EXISTS ix_bot_logs_created_at ON bot_logs (created_at)')


def downgrade() -> None:
    op.drop_index('ix_bot_logs_created_at', table_name='bot_logs')
    op.drop_table('bot_logs')
    op.drop_table('bot_settings')
    op.execute('DROP TYPE IF EXISTS botloglevel')
