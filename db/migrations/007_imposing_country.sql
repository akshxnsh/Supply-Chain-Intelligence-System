-- 007: which country imposes a duty / trade rule (the reader reports it), and the trader's own import country.
-- A duty only costs an importer when it is imposed by the country the goods are imported INTO.

ALTER TABLE events ADD COLUMN IF NOT EXISTS imposing_country TEXT;
ALTER TABLE trader_settings ADD COLUMN IF NOT EXISTS importing_country TEXT NOT NULL DEFAULT 'United States';
