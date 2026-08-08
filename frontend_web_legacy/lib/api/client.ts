const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  body?: any
  headers?: Record<string, string>
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options

    const config: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers
      }
    }

    if (body) {
      config.body = JSON.stringify(body)
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, config)

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      throw new Error(error.message || `HTTP ${response.status}`)
    }

    return response.json()
  }

  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint)
  }

  async post<T>(endpoint: string, body: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'POST', body })
  }

  async put<T>(endpoint: string, body: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'PUT', body })
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }

  async healthCheck(): Promise<{ status: string; timestamp: string; version: string }> {
    return this.get('/health')
  }

  async getPatients(): Promise<any[]> {
    return this.get('/api/patients')
  }

  async getPatient(patientId: string): Promise<any> {
    return this.get(`/api/patients/${patientId}`)
  }

  async getPatientVitals(patientId: string, days: number = 30): Promise<any[]> {
    return this.get(`/api/patients/${patientId}/vitals?days=${days}`)
  }

  async getVitalsDelta(patientId: string): Promise<any> {
    return this.get(`/api/patients/${patientId}/vitals/delta`)
  }

  async getPatientMedications(patientId: string): Promise<any[]> {
    return this.get(`/api/patients/${patientId}/medications`)
  }

  async processInput(text: string, patientId?: string, context?: any): Promise<any> {
    return this.post('/api/input', {
      text,
      patient_id: patientId,
      context: context || {}
    })
  }
}

export const apiClient = new ApiClient()
export default apiClient
