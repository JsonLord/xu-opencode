-- OpenCode Tables for Supabase
-- Run this in Supabase SQL Editor

-- Sessions table
CREATE TABLE IF NOT EXISTS opencode_sessions (
  id TEXT PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  agent_id TEXT DEFAULT 'build',
  provider_id TEXT,
  model_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opencode_sessions_user_id ON opencode_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_opencode_sessions_updated_at ON opencode_sessions(updated_at DESC);

-- Messages table
CREATE TABLE IF NOT EXISTS opencode_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES opencode_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT,
  provider_id TEXT,
  model_id TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opencode_messages_session_id ON opencode_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_opencode_messages_created_at ON opencode_messages(session_id, created_at);

-- Message parts (text, tool_call, tool_result)
CREATE TABLE IF NOT EXISTS opencode_message_parts (
  id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES opencode_messages(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('text', 'tool_call', 'tool_result')),
  content TEXT,
  tool_call_id TEXT,
  tool_name TEXT,
  tool_args JSONB,
  tool_output TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opencode_message_parts_message_id ON opencode_message_parts(message_id);

-- Usage tracking (replaces sandbox_usage)
CREATE TABLE IF NOT EXISTS opencode_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  request_count INTEGER DEFAULT 0,
  UNIQUE(user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_opencode_usage_user_date ON opencode_usage(user_id, usage_date);

-- Row Level Security
ALTER TABLE opencode_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE opencode_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE opencode_message_parts ENABLE ROW LEVEL SECURITY;
ALTER TABLE opencode_usage ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own data
CREATE POLICY "Users can CRUD their own sessions"
  ON opencode_sessions FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD messages in their sessions"
  ON opencode_messages FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM opencode_sessions
      WHERE opencode_sessions.id = opencode_messages.session_id
      AND opencode_sessions.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can CRUD parts in their messages"
  ON opencode_message_parts FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM opencode_messages
      JOIN opencode_sessions ON opencode_sessions.id = opencode_messages.session_id
      WHERE opencode_messages.id = opencode_message_parts.message_id
      AND opencode_sessions.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can access their own usage"
  ON opencode_usage FOR ALL
  USING (auth.uid() = user_id);

-- Function to increment usage (atomic)
CREATE OR REPLACE FUNCTION increment_opencode_usage(
  p_user_id UUID,
  p_input_tokens INTEGER DEFAULT 0,
  p_output_tokens INTEGER DEFAULT 0
)
RETURNS void AS $$
BEGIN
  INSERT INTO opencode_usage (user_id, usage_date, input_tokens, output_tokens, request_count)
  VALUES (p_user_id, CURRENT_DATE, p_input_tokens, p_output_tokens, 1)
  ON CONFLICT (user_id, usage_date)
  DO UPDATE SET
    input_tokens = opencode_usage.input_tokens + EXCLUDED.input_tokens,
    output_tokens = opencode_usage.output_tokens + EXCLUDED.output_tokens,
    request_count = opencode_usage.request_count + 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get daily usage
CREATE OR REPLACE FUNCTION get_opencode_usage(p_user_id UUID)
RETURNS TABLE(input_tokens INTEGER, output_tokens INTEGER, request_count INTEGER) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    COALESCE(u.input_tokens, 0)::INTEGER,
    COALESCE(u.output_tokens, 0)::INTEGER,
    COALESCE(u.request_count, 0)::INTEGER
  FROM opencode_usage u
  WHERE u.user_id = p_user_id AND u.usage_date = CURRENT_DATE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER opencode_sessions_updated_at
  BEFORE UPDATE ON opencode_sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
