import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

# Load environment variables from .env file
load_dotenv()

# Import the Base and table models from the main application
# This ensures we are using the same table definitions
from transcriber import Base, DATABASE_URL


def wipe_and_recreate_database():
    """
    Connects to the database defined by DATABASE_URL and safely drops and recreates
    all tables defined in the application's SQLAlchemy models.
    """
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")

    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            print("Successfully connected to the database.")

            # Drop all tables defined in the Base metadata
            print("Dropping all tables...")
            Base.metadata.drop_all(engine)
            print("Tables dropped successfully.")

            # Recreate all tables
            print("Recreating all tables from the current models...")
            Base.metadata.create_all(engine)
            print("Tables recreated successfully. Database is now in sync with models.")

    except OperationalError as e:
        print(f"ERROR: Could not connect to the database.")
        print(f"Please check your DATABASE_URL and ensure the database server is running.")
        print(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("WARNING: This script will completely wipe and recreate your database tables.")
    # Add a confirmation step to prevent accidental data loss
    if input("Are you sure you want to continue? (yes/no): ").lower() != "yes":
        print("Operation cancelled.")
        sys.exit(0)
    
    wipe_and_recreate_database()