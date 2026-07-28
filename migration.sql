-- Complete Schema for fresh Supabase Setup

CREATE TABLE IF NOT EXISTS public.profiles (
  id          UUID PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  full_name   TEXT,
  role        TEXT DEFAULT 'admin' CHECK (role IN ('admin')),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.classes (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_by  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.invites (
  id          TEXT PRIMARY KEY,
  class_id    TEXT REFERENCES public.classes(id) ON DELETE CASCADE,
  token       TEXT UNIQUE,
  expires_at  TIMESTAMPTZ,
  is_active   BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.students (
  id                TEXT PRIMARY KEY,
  class_id          TEXT REFERENCES public.classes(id) ON DELETE SET NULL,
  leetcode_username TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  avatar_url        TEXT,
  solved_easy       INTEGER DEFAULT 0,
  solved_medium     INTEGER DEFAULT 0,
  solved_hard       INTEGER DEFAULT 0,
  solved_total      INTEGER DEFAULT 0,
  points            INTEGER DEFAULT 0,
  ranking           INTEGER DEFAULT 0,
  last_updated      TIMESTAMPTZ DEFAULT NOW(),
  joined_at         TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(class_id, leetcode_username)
);

-- Disable RLS (Since we rely on server-side FastAPI endpoints to handle logic/auth)
ALTER TABLE public.profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.classes  DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.invites  DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.students DISABLE ROW LEVEL SECURITY;

GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
