CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    mrn TEXT UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth DATE,
    gender TEXT,
    room TEXT,
    bed TEXT,
    admission_date DATETIME,
    discharge_date DATETIME,
    primary_diagnosis TEXT,
    allergies TEXT,
    code_status TEXT DEFAULT 'Full Code',
    insurance TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_patients_mrn ON patients(mrn);
CREATE INDEX IF NOT EXISTS idx_patients_room ON patients(room);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_patients_active ON patients(is_active);

CREATE TABLE IF NOT EXISTS visits (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    visit_type TEXT,
    admission_date DATETIME NOT NULL,
    discharge_date DATETIME,
    attending_physician TEXT,
    department TEXT,
    chief_complaint TEXT,
    diagnosis_codes TEXT,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id);
CREATE INDEX IF NOT EXISTS idx_visits_status ON visits(status);
CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(admission_date);

CREATE TABLE IF NOT EXISTS vitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    visit_id TEXT,
    vital_type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    timestamp DATETIME NOT NULL,
    source TEXT DEFAULT 'manual',
    recorded_by TEXT,
    notes TEXT,
    is_valid INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE INDEX IF NOT EXISTS idx_vitals_patient ON vitals(patient_id);
CREATE INDEX IF NOT EXISTS idx_vitals_patient_type ON vitals(patient_id, vital_type);
CREATE INDEX IF NOT EXISTS idx_vitals_timestamp ON vitals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vitals_patient_timestamp ON vitals(patient_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS vital_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL UNIQUE,
    systolic REAL,
    diastolic REAL,
    heart_rate REAL,
    temperature REAL,
    spo2 REAL,
    respiratory_rate REAL,
    weight REAL,
    height REAL,
    glucose REAL,
    baseline_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS medications (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    name TEXT NOT NULL,
    generic_name TEXT,
    dose TEXT,
    unit TEXT,
    route TEXT,
    frequency TEXT,
    scheduled_times TEXT,
    start_date DATETIME,
    end_date DATETIME,
    prescriber TEXT,
    indication TEXT,
    instructions TEXT,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);
CREATE INDEX IF NOT EXISTS idx_medications_status ON medications(status);
CREATE INDEX IF NOT EXISTS idx_medications_patient_status ON medications(patient_id, status);

CREATE TABLE IF NOT EXISTS medication_administrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    medication_id TEXT,
    medication_name TEXT NOT NULL,
    dose TEXT,
    unit TEXT,
    route TEXT,
    action TEXT NOT NULL,
    scheduled_time DATETIME,
    actual_time DATETIME NOT NULL,
    recorded_by TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (medication_id) REFERENCES medications(id)
);

CREATE INDEX IF NOT EXISTS idx_med_admin_patient ON medication_administrations(patient_id);
CREATE INDEX IF NOT EXISTS idx_med_admin_medication ON medication_administrations(medication_id);
CREATE INDEX IF NOT EXISTS idx_med_admin_time ON medication_administrations(actual_time DESC);

CREATE TABLE IF NOT EXISTS medication_holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    medication_id TEXT,
    medication_name TEXT NOT NULL,
    reason TEXT,
    hold_start DATETIME NOT NULL,
    hold_end DATETIME,
    recorded_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (medication_id) REFERENCES medications(id)
);

CREATE TABLE IF NOT EXISTS clinical_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    visit_id TEXT,
    note_type TEXT,
    content TEXT NOT NULL,
    author TEXT,
    timestamp DATETIME NOT NULL,
    is_signed INTEGER DEFAULT 0,
    signed_by TEXT,
    signed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE INDEX IF NOT EXISTS idx_notes_patient ON clinical_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_notes_timestamp ON clinical_notes(timestamp DESC);

CREATE TABLE IF NOT EXISTS change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    significance TEXT,
    detected_at DATETIME NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_changelog_patient ON change_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_changelog_type ON change_log(change_type);
CREATE INDEX IF NOT EXISTS idx_changelog_unack ON change_log(acknowledged) WHERE acknowledged = 0;

CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    voice_enabled INTEGER DEFAULT 1,
    notification_sound INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'light',
    vital_display_format TEXT DEFAULT 'detailed',
    default_view TEXT DEFAULT 'dashboard',
    quick_phrases TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    current_patient_id TEXT,
    last_activity DATETIME,
    context_data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (current_patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_session_user ON session_context(user_id);

CREATE VIEW IF NOT EXISTS v_latest_vitals AS
SELECT 
    v.patient_id,
    MAX(CASE WHEN v.vital_type = 'systolic' THEN v.value END) as systolic,
    MAX(CASE WHEN v.vital_type = 'diastolic' THEN v.value END) as diastolic,
    MAX(CASE WHEN v.vital_type = 'heart_rate' THEN v.value END) as heart_rate,
    MAX(CASE WHEN v.vital_type = 'temperature' THEN v.value END) as temperature,
    MAX(CASE WHEN v.vital_type = 'spo2' THEN v.value END) as spo2,
    MAX(CASE WHEN v.vital_type = 'respiratory_rate' THEN v.value END) as respiratory_rate,
    MAX(CASE WHEN v.vital_type = 'weight' THEN v.value END) as weight,
    MAX(CASE WHEN v.vital_type = 'glucose' THEN v.value END) as glucose,
    MAX(v.timestamp) as last_recorded
FROM vitals v
WHERE v.is_valid = 1
AND v.timestamp = (
    SELECT MAX(v2.timestamp) 
    FROM vitals v2 
    WHERE v2.patient_id = v.patient_id 
    AND v2.vital_type = v.vital_type
    AND v2.is_valid = 1
)
GROUP BY v.patient_id;

CREATE VIEW IF NOT EXISTS v_active_medications AS
SELECT 
    m.*,
    p.first_name || ' ' || p.last_name as patient_name,
    (SELECT MAX(actual_time) 
     FROM medication_administrations ma 
     WHERE ma.medication_id = m.id 
     AND ma.action = 'given') as last_given
FROM medications m
JOIN patients p ON m.patient_id = p.id
WHERE m.status = 'active'
AND (m.end_date IS NULL OR m.end_date > CURRENT_TIMESTAMP);