"""Add custom features and plan discount fields

Revision ID: 20251010_01
Revises: 20250901_01
Create Date: 2025-10-10
"""

from alembic import op
import sqlalchemy as sa

revision = '20251010_01'
down_revision = '20250901_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('custom_features', sa.Text(), nullable=True))
    op.add_column('plans', sa.Column('discount_price', sa.Float(), nullable=True))
    op.add_column('plans', sa.Column('discount_start', sa.DateTime(), nullable=True))
    op.add_column('plans', sa.Column('discount_end', sa.DateTime(), nullable=True))
    op.add_column('plans', sa.Column('is_public', sa.Boolean(), nullable=True, server_default=sa.text('1')))


def downgrade():
    op.drop_column('plans', 'is_public')
    op.drop_column('plans', 'discount_end')
    op.drop_column('plans', 'discount_start')
    op.drop_column('plans', 'discount_price')
    op.drop_column('users', 'custom_features')
