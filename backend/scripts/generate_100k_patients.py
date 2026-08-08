import sqlite3
import random
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

DB_PATH = settings.DATA_DIR / "clinical.db"

def generate_100k_patients():
    print(f"Generating 1 Lakh (100,000) synthetic patients...")
    print(f"Database Path: {DB_PATH}")
    
    start_time = time.time()
    
    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure table exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT,
        age INTEGER,
        gender TEXT,
        room TEXT,
        primary_diagnosis TEXT,
        allergies TEXT,
        admission_date TEXT,
        status TEXT
    )
    ''')
    
    from faker import Faker
    
    fake = Faker()
    patients = []
    now_str = datetime.utcnow().isoformat()
    
    # Common medical data for randomization
    diagnoses = ["Hypertension", "Type 2 Diabetes", "Pneumonia", "Congestive Heart Failure", "Asthma", "COPD", "Sepsis", "Stroke", "Myocardial Infarction"]
    allergies_list = ["None", "Penicillin", "Sulfa", "Latex", "Peanuts", "Aspirin", "Iodine"]
    
    # Generate 100,000 records
    for i in range(100000):
        pid = f"p100k_{i}"
        mrn = f"MRN{100000+i}"
        first_name = fake.first_name()
        last_name = fake.last_name()
        dob = fake.date_of_birth(minimum_age=18, maximum_age=95).strftime("%Y-%m-%d")
        gender = random.choice(["M", "F"])
        room = f"{random.randint(1, 9)}{random.randint(0, 9)}{random.randint(0, 9)}"
        diag = random.choice(diagnoses)
        allergies = random.choice(allergies_list)
        admission_date = fake.date_time_between(start_date="-30d", end_date="now").isoformat()
        
        patients.append((
            pid, mrn, first_name, last_name, dob, gender, room, "1", 
            admission_date, None, diag, allergies, "FULL", "Medicare", 
            fake.name(), fake.phone_number(), now_str, now_str, True
        ))
        
        # Batch insert every 10,000 records to save memory
        if len(patients) >= 10000:
            cursor.executemany('''
            INSERT OR REPLACE INTO patients 
            (id, mrn, first_name, last_name, date_of_birth, gender, room, bed, 
             admission_date, discharge_date, primary_diagnosis, allergies, code_status, 
             insurance, emergency_contact_name, emergency_contact_phone, created_at, 
             updated_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', patients)
            conn.commit()
            print(f"Inserted {i+1} records...")
            patients = []
            
    # Insert any remaining
    if patients:
        cursor.executemany('''
        INSERT OR REPLACE INTO patients 
        (id, mrn, first_name, last_name, date_of_birth, gender, room, bed, 
         admission_date, discharge_date, primary_diagnosis, allergies, code_status, 
         insurance, emergency_contact_name, emergency_contact_phone, created_at, 
         updated_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', patients)
        conn.commit()
        
    elapsed = time.time() - start_time
    print(f"[SUCCESS] Successfully generated and inserted 100,000 patients in {elapsed:.2f} seconds!")
    
    # Verification
    cursor.execute("SELECT COUNT(*) FROM patients")
    count = cursor.fetchone()[0]
    print(f"Total Database Scale: {count} total patient records.")
    
    conn.close()

if __name__ == "__main__":
    generate_100k_patients()
