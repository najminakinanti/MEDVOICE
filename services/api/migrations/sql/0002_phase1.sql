-- Fase 1: segmen bukti dari kode, asal kalimat SOAP (AI vs dokter), butir yang dibuang parser.
ALTER TABLE extraction_items ADD COLUMN segment_idxs integer[] NOT NULL DEFAULT '{}';
ALTER TABLE extractions ADD COLUMN dropped_items integer NOT NULL DEFAULT 0;
ALTER TABLE soap_sentences ADD COLUMN origin text NOT NULL DEFAULT 'ai'
    CHECK (origin IN ('ai','dokter_edit','dokter_baru'));
ALTER TABLE soap_sentences ADD COLUMN ai_text text;   -- teks asli AI bila kalimat diedit dokter
ALTER TABLE soap_sentences DROP CONSTRAINT IF EXISTS soap_sentences_section_check;
ALTER TABLE soap_sentences ADD CONSTRAINT soap_sentences_section_check CHECK (section IN ('S','O','A','P'));
