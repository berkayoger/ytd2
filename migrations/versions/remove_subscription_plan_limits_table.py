"""
Migration: Drop subscription_plan_limits table
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_subscription_plan_limits'
down_revision = 'previous_revision_id'
branch_labels = None
depends_on = None

def upgrade():
    op.drop_table('subscription_plan_limits')

def downgrade():
    op.create_table(
        'subscription_plan_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_name', sa.String(length=50), nullable=False),
        sa.Column('limits_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_name')
    )

