-- 006: the judge's recommendation (action + act-by date) stored with the alert, with how it was produced and checked.

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_source      TEXT;          -- model | cache | fallback
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_model       TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_action_type TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_reasoning   TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_claims      JSONB;         -- [{statement, evidence_ids}]
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judge_issues      JSONB;         -- why the model answer was rejected (fallback), or []
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS judged_at         TIMESTAMPTZ;
