-- Add review enforcement rules on template fields
ALTER TABLE template_fields
ADD COLUMN IF NOT EXISTS review_enforced BOOLEAN DEFAULT FALSE;

ALTER TABLE template_fields
ADD COLUMN IF NOT EXISTS review_allowed_values JSONB;

-- Default rule: inspection_report conclusion must be 合格/不合格
UPDATE template_fields
SET review_enforced = TRUE,
    review_allowed_values = '["合格","不合格"]'::jsonb
WHERE field_key = 'inspection_conclusion'
  AND template_id IN (
      SELECT id FROM document_templates WHERE code = 'inspection_report'
  );
