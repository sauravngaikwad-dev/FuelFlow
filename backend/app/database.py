from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# SQLite connection args for multithreaded FastAPI requests
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

# Enable Foreign Key enforcement in SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency for obtaining database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all registered database tables in persistent storage."""
    # Import all models to ensure they are registered with Base metadata
    import app.models.entities  # noqa: F401
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)

    # SQLite migration safeguards for existing databases
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            try:
                res = conn.execute(text("PRAGMA table_info(bookings);")).fetchall()
                cols = [r[1] for r in res]
                if cols and "user_id" not in cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN user_id INTEGER REFERENCES users(id);"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bookings_user_id ON bookings(user_id);"))
                    conn.commit()

                # Migration safeguards for camera_configs Phase 4 fields
                c_res = conn.execute(text("PRAGMA table_info(camera_configs);")).fetchall()
                c_cols = [r[1] for r in c_res]
                if c_cols:
                    if "connection_status" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN connection_status VARCHAR(50) DEFAULT 'DISCONNECTED';"))
                    if "last_error" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN last_error VARCHAR(500);"))
                    if "current_queue_count" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN current_queue_count INTEGER;"))
                    if "current_vehicles_total" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN current_vehicles_total INTEGER;"))
                    if "waiting_time_seconds" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN waiting_time_seconds FLOAT;"))
                    if "last_frame_timestamp" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN last_frame_timestamp DATETIME;"))
                    if "frame_sampling_rate" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN frame_sampling_rate INTEGER DEFAULT 5;"))
                    if "camera_name" not in c_cols:
                        conn.execute(text("ALTER TABLE camera_configs ADD COLUMN camera_name VARCHAR(100) DEFAULT 'Main Forecourt Camera';"))
                    conn.commit()
            except Exception:
                pass
