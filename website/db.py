from psycopg2 import pool
import psycopg2.extras
import os
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

dbConnectionPool = None  

def init_db_pool():
    global dbConnectionPool

    databaseURL = os.getenv("DATABASE_URL")

    if databaseURL:
        dbConnectionPool = pool.ThreadedConnectionPool(1, 20, dsn=databaseURL)
    else:
        dbConnectionPool = pool.ThreadedConnectionPool(
            1,
            20,
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

def return_db(connection, discard: bool = False):
    if dbConnectionPool is not None:
        dbConnectionPool.putconn(connection, close=discard)

def init_db():
    connection = get_db()
    try:
        cursor = connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hashed TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT,
            device_id TEXT UNIQUE NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
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
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_id TEXT NOT NULL,
            power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            current DOUBLE PRECISION,
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
            token_hash TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_notifications_log (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT,
            sent_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data_daily_agg  (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_id TEXT NOT NULL,
            power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            current DOUBLE PRECISION,
            light DOUBLE PRECISION,
            light_percentage DOUBLE PRECISION,
            temp DOUBLE PRECISION,
            efficiency DOUBLE PRECISION,
            health DOUBLE PRECISION,
            log_date DATE NOT NULL,
            CONSTRAINT unique_device_date UNIQUE (device_id, log_date),
            FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE     
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data_hourly_agg (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_id TEXT NOT NULL,
            power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            current DOUBLE PRECISION,
            light DOUBLE PRECISION,
            light_percentage DOUBLE PRECISION,
            temp DOUBLE PRECISION,
            efficiency DOUBLE PRECISION,
            health DOUBLE PRECISION,
            log_time TIMESTAMPTZ NOT NULL,
            CONSTRAINT unique_device_hour UNIQUE (device_id, log_time),
            FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE     
        )
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_device_time 
            ON sensor_data_hourly_agg(device_id, log_time DESC)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_device_date 
            ON sensor_data_daily_agg(device_id, log_date DESC)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_device_time
            ON sensor_data(device_id, recorded_at DESC);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_devices_user
            ON devices(user_id);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_push_subs_user
            ON push_subscriptions(user_id);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_push_log_device_type_time
            ON push_notifications_log(device_id, alert_type, sent_at DESC);
        """)

        connection.commit()

    finally:
        return_db(connection)
        
def _is_connection_alive(connection) -> bool:
    try:
        connection.poll()
        return True
    except Exception:
        return False

@contextmanager
def get_cursor():
    global dbConnectionPool
    connection = None
    
    try:
        connection = get_db()
        if not _is_connection_alive(connection):
            return_db(connection, discard=True)
            connection = get_db()
    except Exception:
        init_db_pool()
        connection = get_db()

    try:
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cursor
        connection.commit()
    except Exception:
        if connection:
            try:
                connection.rollback()
            except Exception:
                return_db(connection, discard=True)
                connection = None
                raise
        raise
    finally:
        if connection:
            try:
                cursor.close()
            except Exception:
                pass
            return_db(connection)