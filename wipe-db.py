import psycopg2
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def wipe_database():
    """Connects to the PostgreSQL database and drops specified tables."""
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "transcriber_db"),
            user=os.getenv("DB_USER", "gojack10"),
            password=os.getenv("DB_PASSWORD", "moso10")
        )
        cursor = conn.cursor()

        # Drop tables if they exist
        cursor.execute("DROP TABLE IF EXISTS transcribed CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS downloaded_videos CASCADE;")
        conn.commit()
        print("Successfully wiped 'transcribed' and 'downloaded_videos' tables.")

    except psycopg2.Error as e:
        print(f"Error wiping PostgreSQL database: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    wipe_database()