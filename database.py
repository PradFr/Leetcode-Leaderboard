import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean,
    Text, DateTime, ForeignKey, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Profiles (auth users — new table) ───────────────────────────────────────
class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default="student")
    leetcode_username = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Classes (existing table, extended) ──────────────────────────────────────
class Class(Base):
    __tablename__ = "classes"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    created_by = Column(String)   # stored as text (UUID string)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invites = relationship("Invite", back_populates="cls", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="cls")


# ─── Invites (existing table, with token column added) ───────────────────────
class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    class_id = Column(String, ForeignKey("public.classes.id", ondelete="CASCADE"))
    token = Column(String, unique=True)
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cls = relationship("Class", back_populates="invites")


# ─── Students (existing table — holds stats + membership in one) ──────────────
class Student(Base):
    __tablename__ = "students"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    class_id = Column(String, ForeignKey("public.classes.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String, unique=True)   # Supabase auth UID as text
    leetcode_username = Column(String)
    display_name = Column(String)
    avatar_url = Column(String)
    solved_easy = Column(Integer, default=0)
    solved_medium = Column(Integer, default=0)
    solved_hard = Column(Integer, default=0)
    solved_total = Column(Integer, default=0)
    points = Column(Integer, default=0)
    ranking = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    cls = relationship("Class", back_populates="students")


def ensure_tables():
    """Create the new 'profiles' table and add missing columns."""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    existing = inspector.get_table_names(schema="public")

    with engine.begin() as conn:
        if "profiles" not in existing:
            conn.execute(text("""
                CREATE TABLE public.profiles (
                  id UUID PRIMARY KEY,
                  email TEXT NOT NULL,
                  full_name TEXT,
                  role TEXT DEFAULT 'student',
                  leetcode_username TEXT,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            print("Created profiles table.")

        # Add description column to classes if missing
        cols = [c["name"] for c in inspector.get_columns("classes", schema="public")]
        if "description" not in cols:
            conn.execute(text("ALTER TABLE public.classes ADD COLUMN description TEXT"))
        if "created_by" not in cols:
            conn.execute(text("ALTER TABLE public.classes ADD COLUMN created_by TEXT"))

        # Add token column to invites if missing
        inv_cols = [c["name"] for c in inspector.get_columns("invites", schema="public")]
        if "token" not in inv_cols:
            conn.execute(text("ALTER TABLE public.invites ADD COLUMN token TEXT UNIQUE"))

    print("Schema ready.")
