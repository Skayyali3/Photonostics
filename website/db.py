from psycopg2 import pool
import psycopg2.extras
import os
from dotenv import load_dotenv
from contextlib import contextmanager
import urllib.parse as urlparse

load_dotenv()

dbConnectionPool = None  

def init_db_pool():
    global dbConnectionPool

    databaseURL = os.getenv("DATABASE_URL")

    if databaseURL:
        dbConnectionPool = pool.SimpleConnectionPool(1, 10, dsn=databaseURL)
    else:
        dbConnectionPool = pool.SimpleConnectionPool(
            1,
            10,
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5432),
            database=os.getenv("DB_NAME", "photonvhealth"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )

def get_db():
    if dbConnectionPool is None:
        init_db_pool()
    return dbConnectionPool.getconn()

def return_db(connection):
    if dbConnectionPool is not None:
        dbConnectionPool.putconn(connection)

def init_db():
    connection = get_db()
    try:
        cursor = connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hashed TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            device_id TEXT UNIQUE NOT NULL, 
            nickname TEXT, 
            max_power INTEGER,
            baseline_power DOUBLE PRECISION DEFAULT 0,
            baseline_light DOUBLE PRECISION DEFAULT 0,
            renew_baseline BOOLEAN DEFAULT FALSE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            power DOUBLE PRECISION,
            light DOUBLE PRECISION,
            light_percentage DOUBLE PRECISION,
            temp DOUBLE PRECISION,
            efficiency DOUBLE PRECISION,
            health DOUBLE PRECISION,
            recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_device_time
            ON sensor_data(device_id, recorded_at DESC);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_devices_user
            ON devices(user_id);
        """)

        connection.commit()

    finally:
        return_db(connection)
        
@contextmanager
def get_cursor():
    connection = get_db()
    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        return_db(connection)