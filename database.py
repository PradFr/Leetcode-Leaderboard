import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean,
    Text, DateTime, ForeignKey, func, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.pool import NullPool

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is missing!")

# SQLAlchemy 2.0 requires postgresql:// instead of postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if os.getenv("VERCEL"):
    engine = create_engine(DATABASE_URL, poolclass=NullPool)
else:
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
    leetcode_username = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assignments = relationship("StaffAssignment", back_populates="profile", cascade="all, delete-orphan")


# -----------------------------------------------------------------------------
# Staff Assignments (Role-Based Permissions for Classes/Categories)
# -----------------------------------------------------------------------------
class StaffAssignment(Base):
    __tablename__ = "staff_assignments"
    __table_args__ = {"schema": "public"}

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("public.profiles.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String, ForeignKey("public.classes.id", ondelete="CASCADE"), nullable=True)
    category_id = Column(String, ForeignKey("public.categories.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="assignments")
    cls = relationship("Class")
    category = relationship("Category")


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
    user_id = Column(String, nullable=True)
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
    last_active = Column(DateTime(timezone=True), server_default=func.now(), default=func.now())
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    email = Column(String, nullable=True)
    department = Column(String, nullable=True)
    batch_year = Column(String, nullable=True)
    is_approved = Column(Boolean, default=True)
    role = Column(String, default="student")

    cls = relationship("Class", back_populates="students")


# -----------------------------------------------------------------------------
# Test Results
# -----------------------------------------------------------------------------
class TestResult(Base):
    __tablename__ = "test_results"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(String, ForeignKey("public.classes.id", ondelete="CASCADE"), nullable=False)
    test_name = Column(String, nullable=False)
    columns = Column(JSONB, nullable=False)
    data = Column(JSONB, nullable=False)
    uploaded_by = Column(String, nullable=True)
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    cls = relationship("Class")


# -----------------------------------------------------------------------------
# Audit Logs
# -----------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(String, nullable=True)
    actor_email = Column(String, nullable=True)
    actor_name = Column(String, nullable=True)
    action_type = Column(String, nullable=False)  # class_created, student_added, staff_assigned, etc.
    target_type = Column(String, nullable=True)  # class, category, student, staff, test, invite
    target_id = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# -----------------------------------------------------------------------------
# Refresh Logs (Auto-Refresh Execution Tracking)
# -----------------------------------------------------------------------------
class RefreshLog(Base):
    __tablename__ = "refresh_logs"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="completed")  # completed, partial, failed
    total_students = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)
    error_details = Column(JSONB, nullable=True)
    triggered_by = Column(String, default="scheduled")  # scheduled, manual: admin@college.edu


from sqlalchemy import text

def ensure_tables():
    """Create tables if they don't exist and patch legacy schemas"""
    Base.metadata.create_all(engine)
    statements = [
        "ALTER TABLE public.students ALTER COLUMN user_id DROP NOT NULL;",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS register_number VARCHAR;",
        "ALTER TABLE public.classes ADD COLUMN IF NOT EXISTS category_id VARCHAR(32) REFERENCES public.categories(id) ON DELETE CASCADE;",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW();",
        "UPDATE public.students SET last_active = COALESCE(last_updated, joined_at, NOW()) WHERE last_active IS NULL;",
    ]
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:
            # Ignore expected benign errors (e.g. constraints or columns already existing)
            pass
    print("Schema ready.")
