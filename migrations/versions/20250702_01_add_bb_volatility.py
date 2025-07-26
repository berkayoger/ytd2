"""Add bb fields, volatility, and forecast columns

Revision ID: 20250702_01
Revises: 
Create Date: 2025-07-02
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250702_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dbh_data', sa.Column('bb_upper', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('bb_lower', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('forecast_next_day', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('forecast_upper_bound', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('forecast_lower_bound', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('forecast_explanation', sa.Text(), nullable=True))
    op.add_column('dbh_data', sa.Column('volatility', sa.Float(), nullable=True))
    op.drop_column('dbh_data', 'bollinger_upper')
    op.drop_column('dbh_data', 'bollinger_lower')
    op.drop_column('dbh_data', 'forecast_prophet')


def downgrade():
    op.add_column('dbh_data', sa.Column('bollinger_upper', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('bollinger_lower', sa.Float(), nullable=True))
    op.add_column('dbh_data', sa.Column('forecast_prophet', sa.Float(), nullable=True))
    op.drop_column('dbh_data', 'bb_upper')
    op.drop_column('dbh_data', 'bb_lower')
    op.drop_column('dbh_data', 'forecast_next_day')
    op.drop_column('dbh_data', 'forecast_upper_bound')
    op.drop_column('dbh_data', 'forecast_lower_bound')
    op.drop_column('dbh_data', 'forecast_explanation')
    op.drop_column('dbh_data', 'volatility')
