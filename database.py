import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean,
    Text, DateTime, ForeignKey, func, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID

load_dotenv(override=True)

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


# ─── Profiles (Admins only) ──────────────────────────────────────────────────
class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True)
    full_name = Column(String)
    role = Column(String, default="admin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# -----------------------------------------------------------------------------
# Categories
# -----------------------------------------------------------------------------
class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    classes = relationship("Class", back_populates="category", cascade="all, delete-orphan")


# -----------------------------------------------------------------------------
# Classes
# -----------------------------------------------------------------------------
class Class(Base):
    __tablename__ = "classes"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String, nullable=False)
    description = Column(Text)
    category_id = Column(String, ForeignKey("public.categories.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category", back_populates="classes")
    invites = relationship("Invite", back_populates="cls", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="cls")


# -----------------------------------------------------------------------------
# Invites
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
# Students (No auth user required)
# -----------------------------------------------------------------------------
class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint('class_id', 'leetcode_username', name='_class_leetcode_uc'),
        {"schema": "public"}
    )

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    class_id = Column(String, ForeignKey("public.classes.id", ondelete="SET NULL"), nullable=True)
    leetcode_username = Column(String, nullable=False)
    register_number = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
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


from sqlalchemy import text

def ensure_tables():
    """Create tables if they don't exist and patch legacy schemas"""
    Base.metadata.create_all(engine)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE public.students ALTER COLUMN user_id DROP NOT NULL;"))
            
            try:
                conn.execute(text("ALTER TABLE public.students ADD COLUMN register_number VARCHAR;"))
            except Exception:
                pass # Already exists
            
            # Add category_id if it doesn't exist
            try:
                conn.execute(text("ALTER TABLE public.classes ADD COLUMN category_id VARCHAR(32) REFERENCES public.categories(id) ON DELETE CASCADE;"))
            except Exception:
                pass # Already exists
            
            conn.commit()
    except Exception as e:
        print(f"Migration error (ignoring): {e}")
    print("Schema ready.")
