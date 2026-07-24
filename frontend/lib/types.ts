export interface Patient {
    id: string
    mrn: string
    first_name: string
    last_name: string
    name: string
    date_of_birth: string
    age: number
    gender: string
    room: string
    bed: string
    admission_date: string
    discharge_date: string | null
    primary_diagnosis: string
    allergies: string
    code_status: string
    insurance: string
    emergency_contact_name: string
    emergency_contact_phone: string
    is_active: boolean
    created_at: string
    updated_at: string
  }
  
  export interface VitalReading {
    id: number
    patient_id: string
    vital_type: string
    value: number
    unit: string
    timestamp: string
    source: string
    recorded_by: string | null
    notes: string | null
    is_valid: boolean
    created_at: string
  }
  
  export interface VitalDelta {
    current: number
    significance: string
    vs_yesterday?: {
      value: number
      absolute_change: number
      percent_change: number
    }
    vs_7day_avg?: {
      value: number
      absolute_change: number
      percent_change: number
    }
    vs_baseline?: {
      value: number
      absolute_change: number
      percent_change: number
    }
    trend: 'stable' | 'increasing' | 'decreasing' | 'rapidly_increasing' | 'rapidly_decreasing'
  }
  
  export interface DeltaMetrics {
    patient_id: string
    has_data: boolean
    timestamp: string
    current: {
      systolic?: number
      diastolic?: number
      heart_rate?: number
      temperature?: number
      spo2?: number
      respiratory_rate?: number
      weight?: number
      glucose?: number
      timestamp?: string
    }
    deltas: {
      bp_systolic?: VitalDelta
      bp_diastolic?: VitalDelta
      heart_rate?: VitalDelta
      temperature?: VitalDelta
      spo2?: VitalDelta
      respiratory_rate?: VitalDelta
      weight?: VitalDelta
      glucose?: VitalDelta
    }
    alerts: string[]
    clinical_status: Record<string, string>
  }
  
  export interface Medication {
    id: string
    patient_id: string
    name: string
    generic_name: string | null
    dose: string
    unit: string | null
    route: string
    frequency: string
    scheduled_times: string[]
    start_date: string
    end_date: string | null
    prescriber: string | null
    indication: string | null
    instructions: string | null
    status: string
    last_given?: string
  }
  
  export interface MedicationAdministration {
    id: number
    medication_id: string
    medication_name: string
    dose: string
    route: string
    action: string
    actual_time: string
    recorded_by: string | null
    notes: string | null
  }
  
  export interface ChatMessage {
    id: string
    role: 'user' | 'assistant'
    content: string
    timestamp: Date
    data?: Record<string, any>
    type?: string
  }
  
  export interface Notification {
    id: string
    type: string
    priority: 'low' | 'medium' | 'high' | 'critical'
    title: string
    message: string
    patient_id: string | null
    data: Record<string, any>
    created_at: string
    expires_at: string | null
    acknowledged: boolean
    acknowledged_at: string | null
    acknowledged_by: string | null
  }
  
  export interface ApiResponse<T = any> {
    success: boolean
    message: string
    type: string
    data: T
    timestamp: string
    broadcast?: boolean
    broadcast_data?: any
    patient_id?: string
    requires_patient?: boolean
  }
  
  export interface Visit {
    id: string
    patient_id: string
    visit_type: string
    admission_date: string
    discharge_date: string | null
    attending_physician: string | null
    department: string | null
    chief_complaint: string | null
    diagnosis_codes: string[]
    status: string
    created_at: string
    updated_at: string
  }
  
  export interface ClinicalNote {
    id: number
    patient_id: string
    visit_id: string | null
    note_type: string
    content: string
    author: string | null
    timestamp: string
    is_signed: boolean
    signed_by: string | null
    signed_at: string | null
  }
  
  export interface ChangeLogEntry {
    id: number
    patient_id: string
    change_type: string
    entity_type: string
    entity_id: string | null
    old_value: string | null
    new_value: string | null
    significance: string | null
    detected_at: string
    acknowledged: boolean
    acknowledged_by: string | null
    acknowledged_at: string | null
  }
  
  export type VitalType = 
    | 'systolic'
    | 'diastolic'
    | 'heart_rate'
    | 'temperature'
    | 'spo2'
    | 'respiratory_rate'
    | 'weight'
    | 'height'
    | 'glucose'
  
  export type ClinicalSignificance = 
    | 'normal'
    | 'borderline'
    | 'elevated'
    | 'high'
    | 'critical'
    | 'low'
    | 'critical_low'
  
  export type TrendDirection = 
    | 'stable'
    | 'increasing'
    | 'decreasing'
    | 'rapidly_increasing'
    | 'rapidly_decreasing'