-- Add field-level extraction hints for prompt rules
ALTER TABLE template_fields
ADD COLUMN IF NOT EXISTS extraction_hint TEXT;

-- Initialize sdcm to be numeric-only
UPDATE template_fields
SET extraction_hint = '仅数值，不带单位'
WHERE field_key = 'sdcm';
