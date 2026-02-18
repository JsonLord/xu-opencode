-- Migration: Add reasoning type and tool_status to opencode_message_parts
-- Run this in Supabase SQL Editor

-- 1. Add tool_status column
ALTER TABLE opencode_message_parts
ADD COLUMN IF NOT EXISTS tool_status TEXT;

-- 2. Update type check constraint to include 'reasoning'
-- First, drop the existing constraint
ALTER TABLE opencode_message_parts
DROP CONSTRAINT IF EXISTS opencode_message_parts_type_check;

-- Then, create new constraint with 'reasoning' type included
ALTER TABLE opencode_message_parts
ADD CONSTRAINT opencode_message_parts_type_check
CHECK (type IN ('text', 'tool_call', 'tool_result', 'reasoning'));

-- 3. Add index for tool_status (optional, for filtering)
CREATE INDEX IF NOT EXISTS idx_opencode_message_parts_tool_status
ON opencode_message_parts(tool_status)
WHERE tool_status IS NOT NULL;

-- Verify the changes
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'opencode_message_parts';
