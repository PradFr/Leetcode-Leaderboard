-- Alter existing schema to add missing columns needed by the app
-- Run in Supabase Dashboard > SQL Editor

-- Add description + invite_token to classes
ALTER TABLE public.classes ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE public.classes ADD COLUMN IF NOT EXISTS created_by TEXT;

-- Add profiles table (for auth users)
CREATE TABLE IF NOT EXISTS public.profiles (
  id          UUID PRIMARY KEY,
  email       TEXT NOT NULL,
  full_name   TEXT,
  role        TEXT DEFAULT 'student' CHECK (role IN ('admin', 'student')),
  leetcode_username TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Add invite_token to invites table (instead of our own classes.invite_token)
ALTER TABLE public.invites ADD COLUMN IF NOT EXISTS token TEXT UNIQUE;

-- Generate tokens for existing invites that don't have one
UPDATE public.invites SET token = gen_random_uuid()::text WHERE token IS NULL;

-- Disable RLS
ALTER TABLE public.profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.classes  DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.invites  DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.students DISABLE ROW LEVEL SECURITY;

GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres;
