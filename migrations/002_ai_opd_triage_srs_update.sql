CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE user_role AS ENUM ('patient', 'opd_nurse', 'administrator');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE urgency_level AS ENUM ('high', 'medium', 'low', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE assessment_status AS ENUM ('pending_review', 'approved', 'modified', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE appointment_status AS ENUM ('pending', 'confirmed', 'alternative_suggested', 'cancelled', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE department_availability_status AS ENUM ('available', 'limited', 'unavailable');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role user_role NOT NULL DEFAULT 'patient',
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    full_name VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS patient_user_id UUID REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS availability_status department_availability_status NOT NULL DEFAULT 'available',
    ADD COLUMN IF NOT EXISTS accepting_appointments BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS unavailable_reason TEXT,
    ADD COLUMN IF NOT EXISTS next_available_date DATE,
    ADD COLUMN IF NOT EXISTS capacity_per_day INTEGER CHECK (capacity_per_day IS NULL OR capacity_per_day >= 0);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = 'departments'
            AND column_name = 'availability_status'
            AND udt_name <> 'department_availability_status'
    ) THEN
        ALTER TABLE departments ALTER COLUMN availability_status DROP DEFAULT;
        ALTER TABLE departments
            ALTER COLUMN availability_status TYPE department_availability_status
            USING (
                CASE availability_status::text
                    WHEN 'open' THEN 'available'
                    WHEN 'full' THEN 'limited'
                    WHEN 'closed' THEN 'unavailable'
                    ELSE availability_status::text
                END
            )::department_availability_status;
        ALTER TABLE departments
            ALTER COLUMN availability_status SET DEFAULT 'available'::department_availability_status;
    END IF;
END $$;

ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS assessment_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    source_assessment_id UUID REFERENCES severity_assessments(id) ON DELETE SET NULL,
    recommendation_id UUID REFERENCES department_recommendations(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    urgency urgency_level NOT NULL DEFAULT 'unknown',
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    ai_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    status assessment_status NOT NULL DEFAULT 'pending_review',
    final_urgency urgency_level,
    final_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    nurse_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    nurse_notes TEXT,
    rejection_reason TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS appointment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    assessment_result_id UUID REFERENCES assessment_results(id) ON DELETE SET NULL,
    patient_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    requested_date DATE,
    requested_time VARCHAR(20),
    reason TEXT,
    status appointment_status NOT NULL DEFAULT 'pending',
    confirmed_date DATE,
    confirmed_time VARCHAR(20),
    alternative_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    nurse_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    nurse_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS routing_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_result_id UUID NOT NULL REFERENCES assessment_results(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    nurse_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    original_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    corrected_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    original_urgency urgency_level,
    corrected_urgency urgency_level,
    feedback_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE routing_feedback
    ADD COLUMN IF NOT EXISTS assessment_result_id UUID REFERENCES assessment_results(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS nurse_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS original_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS corrected_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS original_urgency urgency_level,
    ADD COLUMN IF NOT EXISTS corrected_urgency urgency_level,
    ADD COLUMN IF NOT EXISTS feedback_text TEXT;

UPDATE routing_feedback
SET feedback_text = 'Legacy routing feedback'
WHERE feedback_text IS NULL;

ALTER TABLE routing_feedback
    ALTER COLUMN feedback_text SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = 'routing_feedback'
            AND column_name = 'nurse_id'
    ) THEN
        ALTER TABLE routing_feedback ALTER COLUMN nurse_id DROP NOT NULL;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = 'routing_feedback'
            AND column_name = 'feedback_type'
    ) THEN
        ALTER TABLE routing_feedback ALTER COLUMN feedback_type DROP NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_patient_user_id ON sessions(patient_user_id);
CREATE INDEX IF NOT EXISTS idx_departments_availability_status ON departments(availability_status);
CREATE INDEX IF NOT EXISTS idx_assessment_results_session_id ON assessment_results(session_id);
CREATE INDEX IF NOT EXISTS idx_assessment_results_status ON assessment_results(status);
CREATE INDEX IF NOT EXISTS idx_assessment_results_urgency ON assessment_results(urgency);
CREATE INDEX IF NOT EXISTS idx_assessment_results_department_id ON assessment_results(department_id);
CREATE INDEX IF NOT EXISTS idx_assessment_results_created_at ON assessment_results(created_at);
CREATE INDEX IF NOT EXISTS idx_appointment_requests_session_id ON appointment_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_appointment_requests_status ON appointment_requests(status);
CREATE INDEX IF NOT EXISTS idx_appointment_requests_department_id ON appointment_requests(department_id);
CREATE INDEX IF NOT EXISTS idx_appointment_requests_requested_date ON appointment_requests(requested_date);
CREATE INDEX IF NOT EXISTS idx_routing_feedback_assessment_result_id ON routing_feedback(assessment_result_id);
CREATE INDEX IF NOT EXISTS idx_routing_feedback_session_id ON routing_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_assessment_results_updated_at ON assessment_results;
CREATE TRIGGER trg_assessment_results_updated_at BEFORE UPDATE ON assessment_results FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_appointment_requests_updated_at ON appointment_requests;
CREATE TRIGGER trg_appointment_requests_updated_at BEFORE UPDATE ON appointment_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO departments (code, name_en, name_th, description_en) VALUES
('dermatology', 'Dermatology', 'ผิวหนัง', 'For skin, hair, nail, rash, allergy, or wound symptoms.'),
('ophthalmology', 'Ophthalmology', 'จักษุ', 'For eye pain, vision changes, redness, or eye injury.'),
('obstetrics_gynecology', 'Obstetrics and Gynecology', 'สูตินรีเวช', 'For pregnancy, menstrual, or reproductive health concerns.'),
('dental', 'Dental', 'ทันตกรรม', 'For tooth, gum, jaw, or oral health concerns.'),
('psychiatry', 'Psychiatry', 'จิตเวช', 'For mental health, anxiety, mood, sleep, or crisis screening.')
ON CONFLICT (code) DO UPDATE SET
    name_en = EXCLUDED.name_en,
    name_th = EXCLUDED.name_th,
    description_en = EXCLUDED.description_en;

CREATE OR REPLACE VIEW opd_assessment_summary AS
SELECT
    s.id AS session_id,
    s.language,
    s.status AS session_status,
    s.patient_user_id,
    s.started_at,
    s.ended_at,
    latest_result.id AS assessment_result_id,
    latest_result.urgency,
    COALESCE(latest_result.final_urgency, latest_result.urgency) AS final_urgency,
    latest_result.status AS review_status,
    d.id AS department_id,
    d.name_en AS department_name_en,
    d.name_th AS department_name_th,
    COUNT(DISTINCT m.id) AS message_count,
    COUNT(DISTINCT ap.id) AS appointment_count
FROM sessions s
LEFT JOIN messages m ON m.session_id = s.id
LEFT JOIN LATERAL (
    SELECT ar.*
    FROM assessment_results ar
    WHERE ar.session_id = s.id
    ORDER BY ar.created_at DESC
    LIMIT 1
) latest_result ON TRUE
LEFT JOIN departments d ON d.id = COALESCE(latest_result.final_department_id, latest_result.department_id)
LEFT JOIN appointment_requests ap ON ap.session_id = s.id
GROUP BY
    s.id,
    s.language,
    s.status,
    s.patient_user_id,
    s.started_at,
    s.ended_at,
    latest_result.id,
    latest_result.urgency,
    latest_result.final_urgency,
    latest_result.status,
    d.id,
    d.name_en,
    d.name_th;
