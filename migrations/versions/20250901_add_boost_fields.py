"""Add boost columns to users

Revision ID: 20250901_01
Revises: 20250722_01
Create Date: 2025-09-01
"""

from alembic import op
import sqlalchemy as sa

revision = '20250901_01'
down_revision = '20250722_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('boost_features', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('boost_expire_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'boost_expire_at')
    op.drop_column('users', 'boost_features')
