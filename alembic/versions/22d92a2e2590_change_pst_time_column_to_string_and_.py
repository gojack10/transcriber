"""Change pst_time column to string and reposition after utc_time

Revision ID: 22d92a2e2590
Revises: 3ecf12a34a6d
Create Date: 2025-06-25 14:21:40.263756

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from zoneinfo import ZoneInfo
import pytz


# revision identifiers, used by Alembic.
revision: str = '22d92a2e2590'
down_revision: Union[str, None] = '3ecf12a34a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def format_utc_to_pst_string(utc_datetime: datetime) -> str:
    """
    Converts a UTC datetime to PST/PDT and formats it as full date and 12-hour time with AM/PM.
    Helper function for migration.
    """
    if utc_datetime.tzinfo is None:
        utc_datetime = pytz.utc.localize(utc_datetime)
    elif utc_datetime.tzinfo != pytz.utc:
        utc_datetime = utc_datetime.astimezone(pytz.utc)

    pst_tz = ZoneInfo("America/Los_Angeles")
    pst_datetime = utc_datetime.astimezone(pst_tz)
    return pst_datetime.strftime("%Y-%m-%d %I:%M:%S %p")


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add a temporary column for the new string-based pst_time
    op.add_column('transcribed', sa.Column('pst_time_temp', sa.String(), nullable=True))

    # Step 2: Populate the temporary column with formatted PST times
    # Get connection to execute raw SQL
    connection = op.get_bind()

    # Fetch all records with their UTC times
    result = connection.execute(text("SELECT id, utc_time FROM transcribed"))
    records = result.fetchall()

    # Update each record with formatted PST time
    for record in records:
        record_id, utc_time = record
        if utc_time:
            # Convert UTC to formatted PST string
            pst_string = format_utc_to_pst_string(utc_time)
            connection.execute(
                text("UPDATE transcribed SET pst_time_temp = :pst_time WHERE id = :id"),
                {"pst_time": pst_string, "id": record_id}
            )

    # Step 3: Drop the old pst_time column
    op.drop_column('transcribed', 'pst_time')

    # Step 4: Rename the temporary column to pst_time
    op.alter_column('transcribed', 'pst_time_temp', new_column_name='pst_time')


def downgrade() -> None:
    """Downgrade schema."""
    # Step 1: Add back the DateTime column
    op.add_column('transcribed', sa.Column('pst_time_temp', sa.DateTime(timezone=True), nullable=True))

    # Step 2: Convert string times back to DateTime (best effort)
    connection = op.get_bind()
    result = connection.execute(text("SELECT id, utc_time, pst_time FROM transcribed"))
    records = result.fetchall()

    for record in records:
        record_id, utc_time, pst_time_str = record
        if utc_time:
            # Convert UTC to PST DateTime
            if isinstance(utc_time, str):
                utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))

            if utc_time.tzinfo is None:
                utc_time = pytz.utc.localize(utc_time)

            pst_datetime = utc_time.astimezone(ZoneInfo("America/Los_Angeles"))
            connection.execute(
                text("UPDATE transcribed SET pst_time_temp = :pst_time WHERE id = :id"),
                {"pst_time": pst_datetime, "id": record_id}
            )

    # Step 3: Drop the string column
    op.drop_column('transcribed', 'pst_time')

    # Step 4: Rename back
    op.alter_column('transcribed', 'pst_time_temp', new_column_name='pst_time')
