import psycopg2
import sys

def wipe_database():
    """Connects to the PostgreSQL database and drops specified tables."""
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host="127.0.0.1",
            port="5432",
            database="transcriber_db",
            user="gojack10",
            password="moso10"
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