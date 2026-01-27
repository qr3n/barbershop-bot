"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-01-27

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admins_telegram_id", "admins", ["telegram_id"], unique=True)

    op.create_table(
        "masters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "working_hours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
    )
    op.create_index("ix_working_hours_master_id", "working_hours", ["master_id"], unique=False)
    op.create_index("ix_working_hours_master_day", "working_hours", ["master_id", "day_of_week"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Enum("booked", "cancelled", name="appointmentstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_appointments_master_id", "appointments", ["master_id"], unique=False)
    op.create_index("ix_appointments_customer_telegram_id", "appointments", ["customer_telegram_id"], unique=False)
    op.create_index("ix_appointments_start_at", "appointments", ["start_at"], unique=False)
    op.create_index("ix_appointments_end_at", "appointments", ["end_at"], unique=False)
    op.create_index(
        "ix_appointments_master_time",
        "appointments",
        ["master_id", "start_at", "end_at"],
        unique=False,
    )

    op.create_table(
        "make_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum("created", "sent", "failed", "completed", name="makerequeststatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_make_requests_correlation_id", "make_requests", ["correlation_id"], unique=True)
    op.create_index("ix_make_requests_chat_id", "make_requests", ["chat_id"], unique=False)
    op.create_index("ix_make_requests_user_id", "make_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_make_requests_user_id", table_name="make_requests")
    op.drop_index("ix_make_requests_chat_id", table_name="make_requests")
    op.drop_index("ix_make_requests_correlation_id", table_name="make_requests")
    op.drop_table("make_requests")

    op.drop_index("ix_appointments_master_time", table_name="appointments")
    op.drop_index("ix_appointments_end_at", table_name="appointments")
    op.drop_index("ix_appointments_start_at", table_name="appointments")
    op.drop_index("ix_appointments_customer_telegram_id", table_name="appointments")
    op.drop_index("ix_appointments_master_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("ix_working_hours_master_day", table_name="working_hours")
    op.drop_index("ix_working_hours_master_id", table_name="working_hours")
    op.drop_table("working_hours")

    op.drop_table("masters")

    op.drop_index("ix_admins_telegram_id", table_name="admins")
    op.drop_table("admins")

    op.execute("DROP TYPE IF EXISTS appointmentstatus")
    op.execute("DROP TYPE IF EXISTS makerequeststatus")
