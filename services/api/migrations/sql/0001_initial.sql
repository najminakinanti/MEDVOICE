-- Skema awal MedVoice. Semua tabel data punya client_id (multi-tenant).
-- Tidak menyimpan nama/NIK pasien: hanya no_rawat (rujukan ke SIMRS).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- ===== Client & API key =====
CREATE TABLE clients (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL UNIQUE,
    allowed_origins     text[] NOT NULL DEFAULT '{}',          -- CORS per client
    rate_limit_per_min  integer NOT NULL DEFAULT 60 CHECK (rate_limit_per_min > 0),
    monthly_quota       integer CHECK (monthly_quota IS NULL OR monthly_quota > 0),
    webhook_url         text,
    webhook_secret_hash text,
    simrs_adapter       text NOT NULL DEFAULT 'mock',          -- nama adapter SIMRS
    active              boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id    uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    key_prefix   text NOT NULL,                                -- 8 char awal, untuk identifikasi
    key_hash     text NOT NULL UNIQUE,                         -- hash saja; kunci asli tidak disimpan
    label        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);
CREATE INDEX api_keys_client_idx ON api_keys(client_id);

-- ===== Dokter (user) =====
CREATE TABLE doctors (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id      uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    simrs_user_id  text NOT NULL,                              -- kode dokter di SIMRS
    username       text NOT NULL,
    password_hash  text,                                       -- NULL bila login lewat SSO/SIMRS
    display_name   text NOT NULL,
    active         boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (client_id, username),
    UNIQUE (client_id, simrs_user_id)
);

-- ===== Sesi konsultasi =====
CREATE TYPE session_status AS ENUM
    ('recording','processing','review','approved','submitted','failed','cancelled');

CREATE TABLE consult_sessions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id        uuid NOT NULL REFERENCES clients(id),
    doctor_id        uuid NOT NULL REFERENCES doctors(id),
    no_rawat         text NOT NULL,
    status           session_status NOT NULL DEFAULT 'recording',
    consent_at       timestamptz NOT NULL,                     -- consent wajib tercatat sebelum rekam
    consent_by       text NOT NULL,                            -- siapa yang mencatat consent
    consent_note     text,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    audio_deleted_at timestamptz,                              -- bukti audio sudah dihapus
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX consult_sessions_lookup_idx ON consult_sessions(client_id, doctor_id, no_rawat);

-- ===== Job asinkron =====
CREATE TYPE job_status AS ENUM ('queued','running','succeeded','failed');

CREATE TABLE jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    session_id    uuid NOT NULL REFERENCES consult_sessions(id) ON DELETE CASCADE,
    kind          text NOT NULL CHECK (kind IN ('stt','extract','validate','soap','map_codes')),
    status        job_status NOT NULL DEFAULT 'queued',
    attempts      integer NOT NULL DEFAULT 0,
    error_code    text,                                        -- kode saja, bukan isi transkrip
    webhook_state text CHECK (webhook_state IN ('pending','sent','failed')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    finished_at   timestamptz
);
CREATE INDEX jobs_session_idx ON jobs(session_id);
CREATE INDEX jobs_status_idx ON jobs(status) WHERE status IN ('queued','running');

-- ===== Transkrip =====
CREATE TABLE transcripts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    session_id    uuid NOT NULL REFERENCES consult_sessions(id) ON DELETE CASCADE,
    stt_model     text NOT NULL,
    language      text,
    is_empty      boolean NOT NULL DEFAULT false,              -- STT kosong -> isi manual
    purge_after   timestamptz,                                 -- kebijakan retensi
    purged_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX transcripts_session_idx ON transcripts(session_id);

CREATE TABLE transcript_segments (
    id            bigserial PRIMARY KEY,
    transcript_id uuid NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    idx           integer NOT NULL,
    start_ms      integer NOT NULL CHECK (start_ms >= 0),
    end_ms        integer NOT NULL CHECK (end_ms >= start_ms),
    speaker       text NOT NULL CHECK (speaker IN ('dokter','pasien','tidak_diketahui')),
    text          text NOT NULL,                               -- SENSITIF: jangan di-log; enkripsi disk/kolom
    UNIQUE (transcript_id, idx)
);

-- ===== Ekstraksi klinis =====
CREATE TYPE item_status AS ENUM
    ('dinyatakan_dokter','dilaporkan_pasien','dinegasi','direncanakan');
CREATE TYPE validator_verdict AS ENUM ('diterima','ditandai','ditolak');

CREATE TABLE extractions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id      uuid NOT NULL REFERENCES clients(id),
    session_id     uuid NOT NULL REFERENCES consult_sessions(id) ON DELETE CASCADE,
    transcript_id  uuid NOT NULL REFERENCES transcripts(id),
    llm_model      text NOT NULL,
    prompt_version text NOT NULL,
    parse_attempts integer NOT NULL DEFAULT 1,
    manual_input   boolean NOT NULL DEFAULT false,             -- JSON LLM rusak 2x -> input manual
    low_quality    boolean NOT NULL DEFAULT false,             -- banyak butir ditolak
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE extraction_items (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id    uuid NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    field            text NOT NULL,                            -- keluhan_utama, obat, diagnosis, ...
    value            jsonb NOT NULL,                           -- nilai terstruktur (mis. nama obat + dosis)
    status           item_status NOT NULL,
    evidence         text NOT NULL,                            -- kutipan persis dari transkrip
    start_ms         integer NOT NULL,
    end_ms           integer NOT NULL,
    verdict          validator_verdict,                        -- diisi validator (kode, bukan LLM)
    verdict_reasons  jsonb NOT NULL DEFAULT '[]'
);
CREATE INDEX extraction_items_ext_idx ON extraction_items(extraction_id);

CREATE TABLE missed_items (                                    -- daftar "terlewat"
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id  uuid NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    kind           text NOT NULL,                              -- obat | angka_satuan | istilah_vocab
    mention        text NOT NULL,
    start_ms       integer NOT NULL,
    end_ms         integer NOT NULL
);

-- ===== SOAP =====
CREATE TABLE soap_notes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id    uuid NOT NULL REFERENCES clients(id),
    session_id   uuid NOT NULL REFERENCES consult_sessions(id) ON DELETE CASCADE,
    version      integer NOT NULL,
    source       text NOT NULL CHECK (source IN ('ai','dokter')),  -- versi AI vs versi final dokter
    created_by   uuid REFERENCES doctors(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    approved_by  uuid REFERENCES doctors(id),
    approved_at  timestamptz,
    UNIQUE (session_id, version),
    CHECK ((approved_by IS NULL) = (approved_at IS NULL)),
    CHECK (source = 'dokter' OR approved_at IS NULL)           -- versi AI murni tidak bisa di-approve
);

CREATE TABLE soap_sentences (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    soap_id       uuid NOT NULL REFERENCES soap_notes(id) ON DELETE CASCADE,
    section       char(1) NOT NULL CHECK (section IN ('S','O','A','P')),
    idx           integer NOT NULL,
    text          text NOT NULL,
    evidence_item_ids uuid[] NOT NULL DEFAULT '{}',            -- tautan ke butir ekstraksi -> kutipan
    is_ai_suspicion   boolean NOT NULL DEFAULT false,          -- dugaan AI, dipisah & berlabel
    flagged       boolean NOT NULL DEFAULT false,
    UNIQUE (soap_id, section, idx)
);

-- ===== Kode terminologi (hasil pemetaan) =====
CREATE TABLE code_suggestions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    session_id    uuid NOT NULL REFERENCES consult_sessions(id) ON DELETE CASCADE,
    item_id       uuid NOT NULL REFERENCES extraction_items(id) ON DELETE CASCADE,
    system        text NOT NULL CHECK (system IN ('ICD10','KFA','LOINC','ICD9CM','KPTL')),
    candidates    jsonb NOT NULL DEFAULT '[]',
    suggested_code text,
    confidence    real CHECK (confidence BETWEEN 0 AND 1),
    state         text NOT NULL CHECK (state IN ('saran','terisi','kosong','dipilih_dokter')),
    final_code    text,
    decided_by    uuid REFERENCES doctors(id),
    decided_at    timestamptz
);

-- ===== Tabel kode resmi =====
CREATE TABLE terminology_systems (
    id          serial PRIMARY KEY,
    code        text NOT NULL,                                 -- ICD10, KFA, LOINC, ICD9CM, KPTL
    version     text NOT NULL,
    source_url  text NOT NULL,                                 -- sumber resmi, wajib dicatat
    checksum    text,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code, version)
);

CREATE TABLE terminology_codes (
    id                 bigserial PRIMARY KEY,
    system_id          integer NOT NULL REFERENCES terminology_systems(id) ON DELETE CASCADE,
    code               text NOT NULL,
    display            text NOT NULL,
    display_normalized text NOT NULL,                          -- lowercase, tanpa tanda baca
    attrs              jsonb NOT NULL DEFAULT '{}',
    embedding          vector(1024),                           -- bge-m3 = 1024 dimensi
    active             boolean NOT NULL DEFAULT true,
    UNIQUE (system_id, code)
);
CREATE INDEX terminology_trgm_idx ON terminology_codes USING gin (display_normalized gin_trgm_ops);
CREATE INDEX terminology_fts_idx  ON terminology_codes USING gin (to_tsvector('simple', display_normalized));
CREATE INDEX terminology_vec_idx  ON terminology_codes USING hnsw (embedding vector_cosine_ops);

-- ===== Pengiriman ke SIMRS =====
CREATE TABLE simrs_submissions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    session_id    uuid NOT NULL REFERENCES consult_sessions(id),
    soap_id       uuid NOT NULL REFERENCES soap_notes(id),
    adapter       text NOT NULL,
    status        text NOT NULL CHECK (status IN ('pending','succeeded','failed')),
    response_code integer,
    error_code    text,
    submitted_at  timestamptz NOT NULL DEFAULT now()
);

-- Guard: hanya SOAP yang sudah di-approve dokter yang boleh dikirim.
CREATE FUNCTION enforce_approved_before_submit() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM soap_notes WHERE id = NEW.soap_id AND approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'SOAP % belum di-approve dokter', NEW.soap_id;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER simrs_submissions_guard BEFORE INSERT ON simrs_submissions
    FOR EACH ROW EXECUTE FUNCTION enforce_approved_before_submit();

-- ===== Audit log (append-only) =====
CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    client_id   uuid REFERENCES clients(id),
    actor_type  text NOT NULL CHECK (actor_type IN ('dokter','api_client','system','ai')),
    actor_id    text,
    session_id  uuid,
    action      text NOT NULL,
    entity      text,
    entity_id   text,
    before      jsonb,                                         -- tidak boleh berisi isi transkrip mentah
    after       jsonb,
    ip          inet
);
CREATE INDEX audit_log_session_idx ON audit_log(session_id, ts);
CREATE INDEX audit_log_client_idx ON audit_log(client_id, ts);

CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log bersifat append-only';
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
