from datetime import datetime, date
from typing import Optional, List
from sqlmodel import SQLModel, Field, create_engine, Session, select
import uuid
import os

from config import settings


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Patient(SQLModel, table=True):
    __tablename__ = "patients"
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    mrn: Optional[str] = Field(default=None, index=True)
    first_name: str
    last_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    room: Optional[str] = Field(default=None, index=True)
    bed: Optional[str] = None
    admission_date: Optional[datetime] = None
    discharge_date: Optional[datetime] = None
    primary_diagnosis: Optional[str] = None
    allergies: Optional[str] = None
    code_status: str = "Full Code"
    insurance: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class Visit(SQLModel, table=True):
    __tablename__ = "visits"
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    visit_type: Optional[str] = None
    admission_date: datetime
    discharge_date: Optional[datetime] = None
    attending_physician: Optional[str] = None
    department: Optional[str] = None
    chief_complaint: Optional[str] = None
    diagnosis_codes: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Vital(SQLModel, table=True):
    __tablename__ = "vitals"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    visit_id: Optional[str] = Field(default=None, foreign_key="visits.id")
    vital_type: str
    value: float
    unit: Optional[str] = None
    timestamp: datetime
    source: str = "manual"
    recorded_by: Optional[str] = None
    notes: Optional[str] = None
    is_valid: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VitalBaseline(SQLModel, table=True):
    __tablename__ = "vital_baselines"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id")
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    heart_rate: Optional[float] = None
    temperature: Optional[float] = None
    spo2: Optional[float] = None
    respiratory_rate: Optional[float] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    glucose: Optional[float] = None
    baseline_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Medication(SQLModel, table=True):
    __tablename__ = "medications"
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    name: str
    generic_name: Optional[str] = None
    dose: Optional[str] = None
    unit: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    scheduled_times: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    prescriber: Optional[str] = None
    indication: Optional[str] = None
    instructions: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MedicationAdministration(SQLModel, table=True):
    __tablename__ = "medication_administrations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    medication_id: Optional[str] = Field(default=None, foreign_key="medications.id")
    medication_name: str
    dose: Optional[str] = None
    unit: Optional[str] = None
    route: Optional[str] = None
    action: str
    scheduled_time: Optional[datetime] = None
    actual_time: datetime
    recorded_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MedicationHold(SQLModel, table=True):
    __tablename__ = "medication_holds"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id")
    medication_id: Optional[str] = Field(default=None, foreign_key="medications.id")
    medication_name: str
    reason: Optional[str] = None
    hold_start: datetime
    hold_end: Optional[datetime] = None
    recorded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClinicalNote(SQLModel, table=True):
    __tablename__ = "clinical_notes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    visit_id: Optional[str] = Field(default=None, foreign_key="visits.id")
    note_type: Optional[str] = None
    content: str
    author: Optional[str] = None
    timestamp: datetime
    is_signed: bool = False
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChangeLog(SQLModel, table=True):
    __tablename__ = "change_log"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    change_type: str
    entity_type: str
    entity_id: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    significance: Optional[str] = None
    detected_at: datetime
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserPreference(SQLModel, table=True):
    __tablename__ = "user_preferences"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True)
    display_name: Optional[str] = None
    voice_enabled: bool = True
    notification_sound: bool = True
    theme: str = "light"
    vital_display_format: str = "detailed"
    default_view: str = "dashboard"
    quick_phrases: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionContext(SQLModel, table=True):
    __tablename__ = "session_context"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True)
    user_id: Optional[str] = None
    current_patient_id: Optional[str] = Field(default=None, foreign_key="patients.id")
    last_activity: Optional[datetime] = None
    context_data: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    title: str = "New conversation"
    is_archived: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    session_id: str = Field(foreign_key="chat_sessions.id", index=True)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    role: str
    content: str
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


engine = None


def get_engine():
    global engine
    if engine is None:
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        db_url = f"sqlite:///{settings.DB_PATH}"
        print(f"Creating database at: {settings.DB_PATH}")
        engine = create_engine(
            db_url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False}
        )
    return engine


def init_database():
    db_engine = get_engine()
    
    print("Creating tables...")
    SQLModel.metadata.create_all(db_engine)
    
    print("Creating indexes...")
    _create_indexes(db_engine)
    
    print("Seeding sample data...")
    _seed_sample_data()
    
    print("Database initialization complete")


def _create_indexes(db_engine):
    from sqlalchemy import text
    
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_vitals_patient_type ON vitals(patient_id, vital_type)",
        "CREATE INDEX IF NOT EXISTS idx_vitals_timestamp ON vitals(timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_vitals_patient_timestamp ON vitals(patient_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_medications_patient_status ON medications(patient_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_med_admin_patient ON medication_administrations(patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_med_admin_time ON medication_administrations(actual_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_notes_patient ON clinical_notes(patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_changelog_patient ON change_log(patient_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_patient_updated ON chat_sessions(patient_id, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at)",
    ]
    
    with db_engine.connect() as conn:
        for statement in index_statements:
            try:
                conn.execute(text(statement))
            except Exception as e:
                print(f"Index creation warning: {e}")
        conn.commit()


def get_session():
    db_engine = get_engine()
    with Session(db_engine) as session:
        yield session


def _seed_sample_data():
    db_engine = get_engine()
    
    with Session(db_engine) as session:
        existing = session.exec(select(Patient)).first()
        if existing:
            print("Sample data already exists, skipping seed")
            return
        
        print("Creating sample patients...")
        
        patients = [
            Patient(
                id="p1",
                mrn="MRN001234",
                first_name="John",
                last_name="Smith",
                date_of_birth=date(1955, 3, 15),
                gender="Male",
                room="101",
                bed="A",
                admission_date=datetime(2025, 1, 10, 8, 0),
                primary_diagnosis="Hypertension, Type 2 Diabetes",
                allergies="Penicillin",
                code_status="Full Code",
                is_active=True
            ),
            Patient(
                id="p2",
                mrn="MRN001235",
                first_name="Mary",
                last_name="Johnson",
                date_of_birth=date(1962, 7, 22),
                gender="Female",
                room="102",
                bed="A",
                admission_date=datetime(2025, 1, 12, 10, 30),
                primary_diagnosis="COPD Exacerbation",
                allergies="Sulfa drugs",
                code_status="Full Code",
                is_active=True
            ),
            Patient(
                id="p3",
                mrn="MRN001236",
                first_name="Robert",
                last_name="Williams",
                date_of_birth=date(1948, 11, 8),
                gender="Male",
                room="103",
                bed="A",
                admission_date=datetime(2025, 1, 14, 14, 0),
                primary_diagnosis="CHF, Atrial Fibrillation",
                allergies="None known",
                code_status="DNR",
                is_active=True
            ),
        ]
        
        for patient in patients:
            session.add(patient)
        
        session.commit()
        print(f"Created {len(patients)} patients")
        
        vitals_data = [
            ("p1", "systolic", 142, datetime(2025, 1, 15, 8, 0)),
            ("p1", "diastolic", 88, datetime(2025, 1, 15, 8, 0)),
            ("p1", "heart_rate", 78, datetime(2025, 1, 15, 8, 0)),
            ("p1", "temperature", 36.8, datetime(2025, 1, 15, 8, 0)),
            ("p1", "spo2", 97, datetime(2025, 1, 15, 8, 0)),
            ("p1", "respiratory_rate", 16, datetime(2025, 1, 15, 8, 0)),
            ("p1", "systolic", 138, datetime(2025, 1, 14, 8, 0)),
            ("p1", "diastolic", 85, datetime(2025, 1, 14, 8, 0)),
            ("p1", "heart_rate", 75, datetime(2025, 1, 14, 8, 0)),
            ("p1", "systolic", 145, datetime(2025, 1, 13, 8, 0)),
            ("p1", "diastolic", 90, datetime(2025, 1, 13, 8, 0)),
            ("p1", "heart_rate", 80, datetime(2025, 1, 13, 8, 0)),
            ("p2", "systolic", 128, datetime(2025, 1, 15, 8, 0)),
            ("p2", "diastolic", 76, datetime(2025, 1, 15, 8, 0)),
            ("p2", "heart_rate", 92, datetime(2025, 1, 15, 8, 0)),
            ("p2", "spo2", 91, datetime(2025, 1, 15, 8, 0)),
            ("p2", "respiratory_rate", 22, datetime(2025, 1, 15, 8, 0)),
            ("p2", "temperature", 37.2, datetime(2025, 1, 15, 8, 0)),
            ("p3", "systolic", 118, datetime(2025, 1, 15, 8, 0)),
            ("p3", "diastolic", 72, datetime(2025, 1, 15, 8, 0)),
            ("p3", "heart_rate", 88, datetime(2025, 1, 15, 8, 0)),
            ("p3", "weight", 82.5, datetime(2025, 1, 15, 8, 0)),
            ("p3", "spo2", 95, datetime(2025, 1, 15, 8, 0)),
        ]
        
        for patient_id, vital_type, value, timestamp in vitals_data:
            vital = Vital(
                patient_id=patient_id,
                vital_type=vital_type,
                value=value,
                timestamp=timestamp,
                source="seed"
            )
            session.add(vital)
        
        session.commit()
        print(f"Created {len(vitals_data)} vital records")
        
        medications_data = [
            ("p1", "Lisinopril", "10mg", "oral", "daily", '["08:00"]'),
            ("p1", "Metformin", "500mg", "oral", "bid", '["08:00", "20:00"]'),
            ("p1", "Aspirin", "81mg", "oral", "daily", '["08:00"]'),
            ("p2", "Albuterol", "2 puffs", "inhalation", "q4h prn", None),
            ("p2", "Prednisone", "40mg", "oral", "daily", '["08:00"]'),
            ("p2", "Azithromycin", "500mg", "oral", "daily", '["12:00"]'),
            ("p3", "Furosemide", "40mg", "oral", "bid", '["08:00", "14:00"]'),
            ("p3", "Metoprolol", "25mg", "oral", "bid", '["08:00", "20:00"]'),
            ("p3", "Warfarin", "5mg", "oral", "daily", '["18:00"]'),
        ]
        
        for patient_id, name, dose, route, frequency, times in medications_data:
            med = Medication(
                patient_id=patient_id,
                name=name,
                dose=dose,
                route=route,
                frequency=frequency,
                scheduled_times=times,
                start_date=datetime.utcnow(),
                status="active"
            )
            session.add(med)
        
        session.commit()
        print(f"Created {len(medications_data)} medication records")
        
        baselines = [
            VitalBaseline(
                patient_id="p1",
                systolic=135,
                diastolic=82,
                heart_rate=75,
                temperature=36.6,
                spo2=98,
                baseline_date=datetime(2025, 1, 10)
            ),
            VitalBaseline(
                patient_id="p2",
                systolic=125,
                diastolic=78,
                heart_rate=88,
                spo2=94,
                respiratory_rate=18,
                baseline_date=datetime(2025, 1, 12)
            ),
            VitalBaseline(
                patient_id="p3",
                systolic=122,
                diastolic=74,
                heart_rate=82,
                weight=84.0,
                baseline_date=datetime(2025, 1, 14)
            ),
        ]
        
        for baseline in baselines:
            session.add(baseline)
        
        session.commit()
        print(f"Created {len(baselines)} baseline records")


from sqlmodel import select
