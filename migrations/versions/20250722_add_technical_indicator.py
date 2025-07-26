"""Add technical_indicators table

Revision ID: 20250722_01
Revises: 20250702_01
Create Date: 2025-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = '20250722_01'
down_revision = '20250702_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'technical_indicators',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=10), nullable=False),
        sa.Column('rsi', sa.Float(), nullable=True),
        sa.Column('macd', sa.Float(), nullable=True),
        sa.Column('signal', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
    )
    op.create_index('ix_technical_indicators_symbol', 'technical_indicators', ['symbol'])


def downgrade():
    op.drop_index('ix_technical_indicators_symbol', table_name='technical_indicators')
    op.drop_table('technical_indicators')
