-- Fase 2: pemetaan kode terminologi.
ALTER TABLE terminology_codes ADD COLUMN search_text text NOT NULL DEFAULT '';
CREATE INDEX terminology_search_fts_idx ON terminology_codes USING gin (to_tsvector('simple', search_text));
ALTER TABLE code_suggestions ADD COLUMN reason text;
ALTER TABLE code_suggestions ADD COLUMN system_version text;
ALTER TABLE code_suggestions ADD CONSTRAINT code_suggestions_item_system_uq UNIQUE (item_id, system);
