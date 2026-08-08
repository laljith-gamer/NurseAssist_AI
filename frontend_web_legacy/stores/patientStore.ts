import { create } from 'zustand'
import { apiClient } from '@/lib/api/client'
import type { Patient, VitalReading, DeltaMetrics, Medication } from '@/lib/types'

interface PatientState {
  patients: Patient[]
  selectedPatient: Patient | null
  vitals: VitalReading[]
  deltaMetrics: DeltaMetrics | null
  medications: Medication[]
  alerts: string[]
  loading: boolean
  error: string | null
  
  fetchPatients: () => Promise<void>
  fetchPatientData: (patientId: string) => Promise<void>
  selectPatient: (patient: Patient) => void
  clearSelectedPatient: () => void
  setAlerts: (alerts: string[]) => void
  dismissAlert: (index: number) => void
  addVitalReading: (reading: VitalReading) => void
  refreshDelta: (patientId: string) => Promise<void>
}

export const usePatientStore = create<PatientState>((set, get) => ({
  patients: [],
  selectedPatient: null,
  vitals: [],
  deltaMetrics: null,
  medications: [],
  alerts: [],
  loading: false,
  error: null,

  fetchPatients: async () => {
    try {
      set({ loading: true, error: null })
      const patients = await apiClient.getPatients()
      set({ patients, loading: false })
    } catch (error) {
      set({ 
        error: error instanceof Error ? error.message : 'Failed to fetch patients',
        loading: false 
      })
    }
  },

  fetchPatientData: async (patientId: string) => {
    try {
      set({ loading: true, error: null })

      const [vitalsData, deltaData, medsData] = await Promise.all([
        apiClient.getPatientVitals(patientId, 7).catch(() => []),
        apiClient.getVitalsDelta(patientId).catch(() => null),
        apiClient.getPatientMedications(patientId).catch(() => [])
      ])

      set({
        vitals: vitalsData,
        deltaMetrics: deltaData,
        medications: medsData,
        alerts: deltaData?.alerts || [],
        loading: false
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch patient data',
        loading: false
      })
    }
  },

  selectPatient: (patient: Patient) => {
    set({ 
      selectedPatient: patient,
      vitals: [],
      deltaMetrics: null,
      medications: [],
      alerts: []
    })
  },

  clearSelectedPatient: () => {
    set({
      selectedPatient: null,
      vitals: [],
      deltaMetrics: null,
      medications: [],
      alerts: []
    })
  },

  setAlerts: (alerts: string[]) => {
    set({ alerts })
  },

  dismissAlert: (index: number) => {
    const { alerts } = get()
    set({ alerts: alerts.filter((_, i) => i !== index) })
  },

  addVitalReading: (reading: VitalReading) => {
    const { vitals } = get()
    set({ vitals: [reading, ...vitals] })
  },

  refreshDelta: async (patientId: string) => {
    try {
      const deltaData = await apiClient.getVitalsDelta(patientId)
      set({
        deltaMetrics: deltaData,
        alerts: deltaData?.alerts || []
      })
    } catch (error) {
      console.error('Failed to refresh delta metrics')
    }
  }
}))

export default usePatientStore