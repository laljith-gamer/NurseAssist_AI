'use client'

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { 
  Activity, MessageSquare, TrendingUp, Pill, Users, Search,
  AlertTriangle, ChevronLeft, ChevronRight, Send, Mic, MicOff,
  ArrowUp, ArrowDown, Minus, X, Check, RefreshCw,
  Heart, Thermometer, Wind, Droplets, Scale, Plus, History, Clock
} from 'lucide-react'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts'
import { format, parseISO } from 'date-fns'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

interface Patient {
  id: string
  name: string
  mrn: string
  age: number
  gender: string
  room: string
  bed: string
  primary_diagnosis: string
  allergies: string
  code_status: string
  is_active: boolean
}

interface VitalReading {
  id: number
  vital_type: string
  value: number
  unit: string
  timestamp: string
}

interface DeltaMetrics {
  patient_id: string
  has_data: boolean
  current: Record<string, number>
  deltas: Record<string, {
    current: number
    significance: string
    vs_yesterday?: { absolute_change: number; percent_change: number }
    vs_7day_avg?: { absolute_change: number; percent_change: number }
    trend: string
  }>
  alerts: string[]
  clinical_status: Record<string, string>
}

interface Medication {
  id: string
  name: string
  dose: string
  route: string
  frequency: string
  scheduled_times: string[]
  status: string
  last_given?: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  data?: Record<string, unknown>
}

type AssistantMessageBlock =
  | { type: 'heading'; text: string }
  | { type: 'alert'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'bullet'; items: string[] }
  | { type: 'numbered'; items: string[] }

interface ChatSession {
  id: string
  title: string
  createdAt: Date
  updatedAt: Date
  messages: ChatMessage[]
  messageCount?: number
  lastMessagePreview?: string
  messagesLoaded?: boolean
}

interface PatientChatState {
  sessions: ChatSession[]
  activeSessionId: string | null
  draftInput: string
  isLoading: boolean
}

type ChatStateByPatient = Record<string, PatientChatState>

interface PersistedChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  data?: Record<string, unknown>
}

interface PersistedChatSession {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: PersistedChatMessage[]
}

interface PersistedPatientChatState {
  sessions: PersistedChatSession[]
  activeSessionId: string | null
  draftInput: string
}

interface ServerChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at?: string
  metadata?: Record<string, unknown>
}

interface ServerChatSession {
  id: string
  title?: string
  created_at?: string
  updated_at?: string
  message_count?: number
  last_message_preview?: string | null
  messages?: ServerChatMessage[]
}

const CHAT_HISTORY_STORAGE_KEY = 'nurseassist.chat_history.v1'

function createDefaultPatientChatState(): PatientChatState {
  return {
    sessions: [],
    activeSessionId: null,
    draftInput: '',
    isLoading: false,
  }
}

function createSessionTitleFromMessages(messages: ChatMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === 'user')
  if (!firstUserMessage) return 'New conversation'

  const compact = firstUserMessage.content.replace(/\s+/g, ' ').trim()
  if (!compact) return 'New conversation'
  if (compact.length <= 46) return compact
  return `${compact.slice(0, 43)}...`
}

function createNewSession(seedTitle?: string): ChatSession {
  const now = new Date()
  return {
    id: `session-${now.getTime()}-${Math.random().toString(36).slice(2, 7)}`,
    title: seedTitle?.trim() || 'New conversation',
    createdAt: now,
    updatedAt: now,
    messages: [],
    messageCount: 0,
    lastMessagePreview: '',
    messagesLoaded: true,
  }
}

function parseDateOrNow(value?: string): Date {
  if (!value) return new Date()
  const parsed = new Date(value)
  if (!Number.isFinite(parsed.getTime())) return new Date()
  return parsed
}

function mapServerChatMessage(message: ServerChatMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    timestamp: parseDateOrNow(message.created_at),
    data: message.metadata,
  }
}

function mapServerChatSession(session: ServerChatSession): ChatSession {
  const mappedMessages = Array.isArray(session.messages)
    ? session.messages.map(mapServerChatMessage)
    : []

  const derivedPreview = mappedMessages[mappedMessages.length - 1]?.content || ''

  return {
    id: session.id,
    title: session.title || 'New conversation',
    createdAt: parseDateOrNow(session.created_at),
    updatedAt: parseDateOrNow(session.updated_at),
    messages: mappedMessages,
    messageCount: typeof session.message_count === 'number' ? session.message_count : mappedMessages.length,
    lastMessagePreview: session.last_message_preview || derivedPreview,
    messagesLoaded: Array.isArray(session.messages),
  }
}

function serializeChatStateByPatient(state: ChatStateByPatient): Record<string, PersistedPatientChatState> {
  const serialized: Record<string, PersistedPatientChatState> = {}

  for (const [patientId, patientState] of Object.entries(state)) {
    serialized[patientId] = {
      activeSessionId: patientState.activeSessionId,
      draftInput: patientState.draftInput,
      sessions: patientState.sessions.map((session) => ({
        id: session.id,
        title: session.title,
        createdAt: session.createdAt.toISOString(),
        updatedAt: session.updatedAt.toISOString(),
        messages: session.messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          timestamp: message.timestamp.toISOString(),
          data: message.data,
        })),
      })),
    }
  }

  return serialized
}

function deserializeChatStateByPatient(raw: unknown): ChatStateByPatient {
  if (!raw || typeof raw !== 'object') return {}

  const parsed = raw as Record<string, PersistedPatientChatState>
  const hydrated: ChatStateByPatient = {}

  for (const [patientId, patientState] of Object.entries(parsed)) {
    if (!patientState || typeof patientState !== 'object' || !Array.isArray(patientState.sessions)) {
      continue
    }

    hydrated[patientId] = {
      activeSessionId: patientState.activeSessionId ?? null,
      draftInput: patientState.draftInput ?? '',
      isLoading: false,
      sessions: patientState.sessions
        .map((session) => {
          const messages = (session.messages || [])
            .map((message) => ({
              id: message.id,
              role: message.role,
              content: message.content,
              timestamp: new Date(message.timestamp),
              data: message.data,
            }))
            .filter((message) => message.id && Number.isFinite(message.timestamp.getTime()))

          return {
            id: session.id,
            title: session.title || 'New conversation',
            createdAt: new Date(session.createdAt),
            updatedAt: new Date(session.updatedAt),
            messages,
            messageCount: messages.length,
            lastMessagePreview: messages[messages.length - 1]?.content || '',
            messagesLoaded: true,
          }
        })
        .filter(
          (session) =>
            session.id &&
            Number.isFinite(session.createdAt.getTime()) &&
            Number.isFinite(session.updatedAt.getTime())
        ),
    }
  }

  return hydrated
}

export default function Dashboard() {
  const [patients, setPatients] = useState<Patient[]>([])
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null)
  const [vitals, setVitals] = useState<VitalReading[]>([])
  const [deltaMetrics, setDeltaMetrics] = useState<DeltaMetrics | null>(null)
  const [medications, setMedications] = useState<Medication[]>([])
  const [alerts, setAlerts] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'vitals' | 'chat' | 'trends' | 'meds'>('vitals')
  const [chatByPatient, setChatByPatient] = useState<ChatStateByPatient>({})

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const stored = window.localStorage.getItem(CHAT_HISTORY_STORAGE_KEY)
      if (!stored) return
      const parsed = JSON.parse(stored)
      setChatByPatient(deserializeChatStateByPatient(parsed))
    } catch {
      setChatByPatient({})
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const serialized = serializeChatStateByPatient(chatByPatient)
      window.localStorage.setItem(CHAT_HISTORY_STORAGE_KEY, JSON.stringify(serialized))
    } catch {
      // Ignore storage write failures (private mode / quota / blocked storage)
    }
  }, [chatByPatient])

  const fetchPatients = useCallback(async () => {
    try {
      setError(null)
      const response = await fetch(`${API_BASE}/api/patients`)
      
      if (response.ok) {
        const data = await response.json()
        setPatients(data)
      } else {
        setError('Failed to fetch patients')
      }
    } catch (err) {
      setError('Cannot connect to server. Make sure backend is running on port 8001.')
    }
  }, [])

  const fetchPatientData = useCallback(async (patientId: string) => {
    setLoading(true)
    try {
      const [vitalsRes, deltaRes, medsRes] = await Promise.all([
        fetch(`${API_BASE}/api/patients/${patientId}/vitals?days=7`),
        fetch(`${API_BASE}/api/patients/${patientId}/vitals/delta`),
        fetch(`${API_BASE}/api/patients/${patientId}/medications`)
      ])

      if (vitalsRes.ok) {
        const vitalsData = await vitalsRes.json()
        setVitals(vitalsData)
      }

      if (deltaRes.ok) {
        const deltaData = await deltaRes.json()
        setDeltaMetrics(deltaData)
        setAlerts(deltaData.alerts || [])
      }

      if (medsRes.ok) {
        const medsData = await medsRes.json()
        setMedications(medsData)
      }
    } catch (err) {
      setError('Failed to fetch patient data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPatients()
  }, [fetchPatients])

  useEffect(() => {
    if (selectedPatient) {
      fetchPatientData(selectedPatient.id)
    }
  }, [selectedPatient, fetchPatientData])

  const handleDismissAlert = (index: number) => {
    setAlerts((prev) => prev.filter((_, i) => i !== index))
  }

  const handleVitalRecorded = () => {
    if (selectedPatient) {
      fetchPatientData(selectedPatient.id)
    }
  }

  const selectedPatientChat = useMemo(() => {
    if (!selectedPatient) return createDefaultPatientChatState()
    return chatByPatient[selectedPatient.id] ?? createDefaultPatientChatState()
  }, [chatByPatient, selectedPatient])

  const setPatientChatState = useCallback(
    (patientId: string, updater: (state: PatientChatState) => PatientChatState) => {
      setChatByPatient((prev) => {
        const current = prev[patientId] ?? createDefaultPatientChatState()
        const updated = updater(current)
        return { ...prev, [patientId]: updated }
      })
    },
    []
  )

  const loadPatientChatSessions = useCallback(
    async (patientId: string) => {
      try {
        const response = await fetch(`${API_BASE}/api/patients/${patientId}/chat/sessions`)
        if (!response.ok) return

        const payload = await response.json()
        const serverSessions: ChatSession[] = Array.isArray(payload)
          ? payload.map((item) => ({
              ...mapServerChatSession(item as ServerChatSession),
              messages: [],
              messagesLoaded: false,
            }))
          : []

        setPatientChatState(patientId, (state) => {
          const previousById = new Map(state.sessions.map((session) => [session.id, session]))
          const mergedSessions = serverSessions.map((serverSession) => {
            const previous = previousById.get(serverSession.id)
            if (!previous) return serverSession
            return {
              ...previous,
              ...serverSession,
              messages: previous.messages,
              messagesLoaded: previous.messagesLoaded ?? false,
              messageCount: serverSession.messageCount ?? previous.messageCount ?? previous.messages.length,
              lastMessagePreview:
                serverSession.lastMessagePreview ??
                previous.lastMessagePreview ??
                previous.messages[previous.messages.length - 1]?.content ??
                '',
            }
          })

          const nextActiveSessionId =
            state.activeSessionId && mergedSessions.some((session) => session.id === state.activeSessionId)
              ? state.activeSessionId
              : mergedSessions[0]?.id ?? null

          return {
            ...state,
            sessions: mergedSessions,
            activeSessionId: nextActiveSessionId,
          }
        })
      } catch {
        // Ignore sync failures; local state remains usable.
      }
    },
    [setPatientChatState]
  )

  const loadChatSessionMessages = useCallback(
    async (patientId: string, sessionId: string) => {
      try {
        const response = await fetch(`${API_BASE}/api/patients/${patientId}/chat/sessions/${sessionId}`)
        if (!response.ok) return

        const payload = (await response.json()) as ServerChatSession
        const mappedSession = mapServerChatSession(payload)
        const messages = Array.isArray(payload.messages) ? payload.messages.map(mapServerChatMessage) : []

        setPatientChatState(patientId, (state) => {
          const targetIndex = state.sessions.findIndex((session) => session.id === sessionId)
          const updatedSession: ChatSession = {
            ...(targetIndex >= 0 ? state.sessions[targetIndex] : mappedSession),
            ...mappedSession,
            messages,
            messagesLoaded: true,
            messageCount: typeof payload.message_count === 'number' ? payload.message_count : messages.length,
            lastMessagePreview:
              payload.last_message_preview ||
              messages[messages.length - 1]?.content ||
              mappedSession.lastMessagePreview ||
              '',
          }

          const sessionsWithoutTarget =
            targetIndex >= 0
              ? state.sessions.filter((session) => session.id !== sessionId)
              : state.sessions

          return {
            ...state,
            sessions: [updatedSession, ...sessionsWithoutTarget],
            activeSessionId: state.activeSessionId || sessionId,
          }
        })
      } catch {
        // Ignore sync failures; session remains usable with local state.
      }
    },
    [setPatientChatState]
  )

  const createChatSessionOnServer = useCallback(
    async (patientId: string, title?: string): Promise<ChatSession> => {
      const response = await fetch(`${API_BASE}/api/patients/${patientId}/chat/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })

      if (!response.ok) {
        throw new Error(`Failed to create chat session: ${response.status}`)
      }

      const payload = (await response.json()) as ServerChatSession
      return {
        ...mapServerChatSession(payload),
        messages: [],
        messagesLoaded: false,
      }
    },
    []
  )

  useEffect(() => {
    if (!selectedPatient) return
    void loadPatientChatSessions(selectedPatient.id)
  }, [selectedPatient, loadPatientChatSessions])

  const handleChatDraftChange = useCallback(
    (patientId: string, draftInput: string) => {
      setPatientChatState(patientId, (state) => ({
        ...state,
        draftInput,
      }))
    },
    [setPatientChatState]
  )

  const handleCreateNewSession = useCallback(
    (patientId: string) => {
      void (async () => {
        let session: ChatSession
        try {
          session = await createChatSessionOnServer(patientId)
        } catch {
          session = createNewSession()
        }

        setPatientChatState(patientId, (state) => {
          const deduped = state.sessions.filter((existing) => existing.id !== session.id)
          return {
            ...state,
            activeSessionId: session.id,
            sessions: [session, ...deduped],
            draftInput: '',
          }
        })
      })()
    },
    [createChatSessionOnServer, setPatientChatState]
  )

  const handleSelectChatSession = useCallback(
    (patientId: string, sessionId: string) => {
      let shouldLoadMessages = false
      setPatientChatState(patientId, (state) => ({
        ...state,
        activeSessionId: sessionId,
        sessions: state.sessions.map((session) => {
          if (session.id === sessionId && !session.messagesLoaded) {
            shouldLoadMessages = true
          }
          return session
        }),
      }))
      if (shouldLoadMessages) {
        void loadChatSessionMessages(patientId, sessionId)
      }
    },
    [loadChatSessionMessages, setPatientChatState]
  )

  const appendMessageToSession = useCallback(
    (patientId: string, sessionId: string, message: ChatMessage) => {
      setPatientChatState(patientId, (state) => {
        const targetIndex = state.sessions.findIndex((session) => session.id === sessionId)
        if (targetIndex < 0) {
          return {
            ...state,
            isLoading: false,
          }
        }

        const session = state.sessions[targetIndex]
        const updatedMessages = [...session.messages, message]
        const updatedSession: ChatSession = {
          ...session,
          messages: updatedMessages,
          updatedAt: message.timestamp,
          title: createSessionTitleFromMessages(updatedMessages),
          messageCount: updatedMessages.length,
          lastMessagePreview: message.content,
          messagesLoaded: true,
        }

        const reorderedSessions = [
          updatedSession,
          ...state.sessions.filter((item) => item.id !== sessionId),
        ]

        return {
          ...state,
          sessions: reorderedSessions,
          isLoading: false,
        }
      })
    },
    [setPatientChatState]
  )

  const handleSendChatMessage = useCallback(
    async (patientId: string, input: string) => {
      const text = input.trim()
      if (!text) return

      const now = new Date()
      const userMessage: ChatMessage = {
        id: `user-${now.getTime()}`,
        role: 'user',
        content: text,
        timestamp: now,
      }

      const patientChat = chatByPatient[patientId]
      let sessionId =
        patientChat?.activeSessionId &&
        patientChat.sessions.some((session) => session.id === patientChat.activeSessionId)
          ? patientChat.activeSessionId || ''
          : ''

      if (!sessionId) {
        let newSession: ChatSession
        try {
          newSession = await createChatSessionOnServer(
            patientId,
            createSessionTitleFromMessages([userMessage])
          )
        } catch {
          newSession = createNewSession(createSessionTitleFromMessages([userMessage]))
        }
        sessionId = newSession.id

        setPatientChatState(patientId, (state) => {
          const deduped = state.sessions.filter((existing) => existing.id !== newSession.id)
          return {
            ...state,
            sessions: [newSession, ...deduped],
            activeSessionId: newSession.id,
          }
        })
      }

      setPatientChatState(patientId, (state) => {
        const sessions = [...state.sessions]
        let targetIndex = sessions.findIndex((session) => session.id === sessionId)

        if (targetIndex < 0) {
          const fallbackSession = createNewSession(createSessionTitleFromMessages([userMessage]))
          fallbackSession.id = sessionId
          fallbackSession.createdAt = now
          fallbackSession.updatedAt = now
          sessions.unshift(fallbackSession)
          targetIndex = 0
        }

        const targetSession = sessions[targetIndex]
        const updatedMessages = [...targetSession.messages, userMessage]
        const updatedSession: ChatSession = {
          ...targetSession,
          messages: updatedMessages,
          updatedAt: now,
          title: createSessionTitleFromMessages(updatedMessages),
          messageCount: updatedMessages.length,
          lastMessagePreview: userMessage.content,
          messagesLoaded: true,
        }

        const reorderedSessions = [updatedSession, ...sessions.filter((session) => session.id !== sessionId)]

        return {
          ...state,
          sessions: reorderedSessions,
          activeSessionId: sessionId,
          draftInput: '',
          isLoading: true,
        }
      })

      try {
        const response = await fetch(`${API_BASE}/api/input`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text,
            patient_id: patientId,
            context: {},
            session_id: sessionId,
            timestamp: now.toISOString(),
          }),
        })

        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`)
        }
        const data = await response.json()
        const persistedSessionId = data?.data?.session_id

        if (persistedSessionId && persistedSessionId !== sessionId) {
          const previousSessionId = sessionId
          sessionId = persistedSessionId
          setPatientChatState(patientId, (state) => {
            const previousSession = state.sessions.find((session) => session.id === previousSessionId)
            const existingTarget = state.sessions.find((session) => session.id === persistedSessionId)
            const remaining = state.sessions.filter(
              (session) => session.id !== previousSessionId && session.id !== persistedSessionId
            )

            if (!previousSession && existingTarget) {
              return {
                ...state,
                activeSessionId: persistedSessionId,
              }
            }

            const migratedSession: ChatSession = {
              ...(existingTarget || previousSession || createNewSession()),
              ...(previousSession || {}),
              id: persistedSessionId,
              messagesLoaded: true,
            }

            return {
              ...state,
              sessions: [migratedSession, ...remaining],
              activeSessionId: persistedSessionId,
            }
          })
        }

        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data?.message || 'No response generated.',
          timestamp: new Date(),
          data: data?.data,
        }
        appendMessageToSession(patientId, sessionId, assistantMessage)
        void loadPatientChatSessions(patientId)
      } catch {
        const errorMessage: ChatMessage = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
        }
        appendMessageToSession(patientId, sessionId, errorMessage)
      } finally {
        setPatientChatState(patientId, (state) => ({
          ...state,
          isLoading: false,
        }))
      }
    },
    [
      appendMessageToSession,
      chatByPatient,
      createChatSessionOnServer,
      loadPatientChatSessions,
      setPatientChatState,
    ]
  )

  return (
    <div className="flex h-screen overflow-hidden flex-col lg:flex-row">
      <PatientSidebar
        patients={patients}
        selectedPatient={selectedPatient}
        onSelectPatient={setSelectedPatient}
        error={error}
      />

      <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <header className="px-4 lg:px-6 py-4 border-b border-slate-200/80 bg-white/75 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl lg:text-2xl font-semibold text-slate-900">
                {selectedPatient
                  ? `${selectedPatient.name} - Room ${selectedPatient.room || 'N/A'}`
                  : 'NurseAssist Command Center'
                }
              </h1>
              {selectedPatient && (
                <p className="text-sm text-slate-500 mt-0.5">
                  {selectedPatient.age} y/o {selectedPatient.gender} |
                  MRN: {selectedPatient.mrn} |
                  {selectedPatient.primary_diagnosis}
                </p>
              )}
              {!selectedPatient && (
                <p className="text-sm text-slate-500 mt-1">
                  Natural language assistant enabled. Ask clinical questions in plain English.
                </p>
              )}
            </div>

            {selectedPatient && (
              <div className="flex items-center space-x-3">
                <button
                  onClick={() => fetchPatientData(selectedPatient.id)}
                  className="btn-ghost"
                  disabled={loading}
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <span className={`badge ${
                  alerts.length > 0 ? 'badge-danger' : 'badge-success'
                }`}>
                  {alerts.length > 0
                    ? `${alerts.length} Alert${alerts.length > 1 ? 's' : ''}`
                    : 'Stable'
                  }
                </span>
              </div>
            )}
          </div>
        </header>

        {alerts.length > 0 && selectedPatient && (
          <ClinicalChangeBanner alerts={alerts} onDismiss={handleDismissAlert} />
        )}

        {selectedPatient && (
          <div className="border-b border-slate-200/80 bg-white/70 backdrop-blur-md">
            <nav className="flex space-x-1 px-3 lg:px-6 overflow-x-auto scrollbar-thin">
              {[
                { id: 'vitals', label: 'Vitals', icon: Activity },
                { id: 'chat', label: 'Assistant', icon: MessageSquare },
                { id: 'trends', label: 'Trends', icon: TrendingUp },
                { id: 'meds', label: 'Medications', icon: Pill },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as typeof activeTab)}
                  className={`flex shrink-0 items-center space-x-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-teal-600 text-teal-700'
                      : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                  }`}
                >
                  <tab.icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              ))}
            </nav>
          </div>
        )}

        <div className="flex-1 overflow-auto px-4 lg:px-6 py-4 lg:py-6">
          {!selectedPatient ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h2 className="text-xl font-medium text-gray-600 mb-2">
                  No Patient Selected
                </h2>
                <p className="text-gray-500">
                  Select a patient from the sidebar to view their information
                </p>
                {error && (
                  <p className="text-red-500 mt-4">{error}</p>
                )}
              </div>
            </div>
          ) : (
            <>
              {activeTab === 'vitals' && (
                <div className="space-y-6">
                  <QuickVitalEntry
                    patientId={selectedPatient.id}
                    onVitalRecorded={handleVitalRecorded}
                  />

                  <VitalsOverviewGrid deltaMetrics={deltaMetrics} />

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <VitalSignsDeltaChart
                      vitalType="blood_pressure"
                      title="Blood Pressure"
                      data={vitals}
                      deltaMetrics={deltaMetrics}
                    />
                    <VitalSignsDeltaChart
                      vitalType="heart_rate"
                      title="Heart Rate"
                      data={vitals}
                      deltaMetrics={deltaMetrics}
                    />
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <VitalSignsDeltaChart
                      vitalType="temperature"
                      title="Temperature"
                      data={vitals}
                      deltaMetrics={deltaMetrics}
                      compact
                    />
                    <VitalSignsDeltaChart
                      vitalType="spo2"
                      title="SpO2"
                      data={vitals}
                      deltaMetrics={deltaMetrics}
                      compact
                    />
                    <VitalSignsDeltaChart
                      vitalType="respiratory_rate"
                      title="Respiratory Rate"
                      data={vitals}
                      deltaMetrics={deltaMetrics}
                      compact
                    />
                  </div>
                </div>
              )}

              {activeTab === 'chat' && (
                <ChatInterface
                  patientId={selectedPatient.id}
                  patientName={selectedPatient.name}
                  chatState={selectedPatientChat}
                  onDraftChange={handleChatDraftChange}
                  onSendMessage={handleSendChatMessage}
                  onCreateSession={handleCreateNewSession}
                  onSelectSession={handleSelectChatSession}
                />
              )}

              {activeTab === 'trends' && (
                <div className="space-y-6">
                  <VitalSignsDeltaChart
                    vitalType="blood_pressure"
                    title="Blood Pressure Trend (7 Days)"
                    data={vitals}
                    deltaMetrics={deltaMetrics}
                    showHistory
                  />
                  <VitalSignsDeltaChart
                    vitalType="heart_rate"
                    title="Heart Rate Trend (7 Days)"
                    data={vitals}
                    deltaMetrics={deltaMetrics}
                    showHistory
                  />
                </div>
              )}

              {activeTab === 'meds' && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="lg:col-span-2 card">
                    <div className="card-header">
                      <h3 className="font-semibold text-gray-900">Active Medications</h3>
                    </div>
                    <div className="card-body">
                      <MedicationList medications={medications} />
                    </div>
                  </div>
                  <div className="card">
                    <div className="card-header">
                      <h3 className="font-semibold text-gray-900">Adherence Rate</h3>
                    </div>
                    <div className="card-body flex items-center justify-center py-8">
                      <MedicationAdherenceRing adherenceRate={87} />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function PatientSidebar({ 
  patients, 
  selectedPatient, 
  onSelectPatient,
  error
}: { 
  patients: Patient[]
  selectedPatient: Patient | null
  onSelectPatient: (patient: Patient) => void
  error: string | null
}) {
  const [searchTerm, setSearchTerm] = useState('')

  const filteredPatients = patients.filter(patient => 
    patient.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    patient.room?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    patient.mrn?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <aside className="w-full h-[42vh] lg:h-auto lg:w-80 lg:min-w-80 bg-white/75 backdrop-blur-md border-b lg:border-b-0 lg:border-r border-slate-200/80 flex flex-col">
      <div className="p-4 border-b border-slate-200/80">
        <div className="flex items-center space-x-2 mb-4">
          <Activity className="w-6 h-6 text-teal-700" />
          <h1 className="text-lg font-semibold text-slate-900">Clinical Assistant</h1>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search patients..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input pl-9"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="p-2">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Patients ({filteredPatients.length})
            </span>
            <Users className="w-4 h-4 text-slate-400" />
          </div>

          {error && (
            <div className="mx-3 p-3 bg-red-50 text-red-700 text-sm rounded-lg mb-2">
              {error}
            </div>
          )}

          <div className="space-y-1">
            {filteredPatients.map((patient) => (
              <button
                key={patient.id}
                onClick={() => onSelectPatient(patient)}
                className={`w-full text-left px-3 py-3 rounded-lg transition-colors ${
                  selectedPatient?.id === patient.id
                    ? 'bg-teal-50/70 border border-teal-200'
                    : 'hover:bg-slate-50/90'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <p className={`font-medium truncate ${
                      selectedPatient?.id === patient.id 
                        ? 'text-teal-700' 
                        : 'text-slate-900'
                    }`}>
                      {patient.name}
                    </p>
                    <p className="text-sm text-slate-500 truncate">
                      Room {patient.room || 'N/A'} | {patient.age}y {patient.gender?.[0]}
                    </p>
                  </div>
                  <ChevronRight className={`w-4 h-4 flex-shrink-0 ${
                    selectedPatient?.id === patient.id 
                      ? 'text-teal-600' 
                      : 'text-slate-300'
                  }`} />
                </div>
                {patient.primary_diagnosis && (
                  <p className="text-xs text-slate-400 mt-1 truncate">
                    {patient.primary_diagnosis}
                  </p>
                )}
              </button>
            ))}
          </div>

          {filteredPatients.length === 0 && !error && (
            <div className="text-center py-8 text-slate-500">
              <Users className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p className="text-sm">No patients found</p>
            </div>
          )}
        </div>
      </div>

      <div className="p-4 border-t border-slate-200/80 bg-slate-50/80">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-teal-100 rounded-full flex items-center justify-center">
            <span className="text-sm font-medium text-teal-700">RN</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">Nurse Station</p>
            <p className="text-xs text-slate-500">Unit 3A</p>
          </div>
        </div>
      </div>
    </aside>
  )
}

function ClinicalChangeBanner({ 
  alerts, 
  onDismiss 
}: { 
  alerts: string[]
  onDismiss: (index: number) => void 
}) {
  if (alerts.length === 0) return null

  return (
    <div className="bg-rose-50/90 border-b border-rose-200/80 backdrop-blur-sm">
      {alerts.map((alert, index) => (
        <div 
          key={index}
          className="px-6 py-3 flex items-center justify-between"
        >
          <div className="flex items-center space-x-3">
            <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
            <p className="text-sm font-medium text-rose-800">{alert}</p>
          </div>
          <button
            onClick={() => onDismiss(index)}
            className="p-1 hover:bg-rose-100 rounded"
          >
            <X className="w-4 h-4 text-rose-600" />
          </button>
        </div>
      ))}
    </div>
  )
}

function QuickVitalEntry({ 
  patientId, 
  onVitalRecorded 
}: { 
  patientId: string
  onVitalRecorded: () => void 
}) {
  const [input, setInput] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [statusMessage, setStatusMessage] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    try {
      const response = await fetch(`${API_BASE}/api/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: input,
          patient_id: patientId,
          context: {}
        })
      })

      const data = await response.json()
      
      if (data.success) {
        setStatus('success')
        setStatusMessage(data.message)
        setInput('')
        onVitalRecorded()
        setTimeout(() => {
          setStatus('idle')
          setStatusMessage('')
        }, 3000)
      } else {
        setStatus('error')
        setStatusMessage(data.message || 'Failed to record')
      }
    } catch (error) {
      setStatus('error')
      setStatusMessage('Connection error')
    }
  }

  const quickButtons = [
    { label: 'BP', example: '120/80' },
    { label: 'HR', example: 'hr 72' },
    { label: 'Temp', example: 'temp 98.6' },
    { label: 'SpO2', example: 'spo2 98' },
  ]

  return (
    <div className="card">
      <div className="card-body">
        <form onSubmit={handleSubmit} className="flex flex-col lg:flex-row items-stretch lg:items-center gap-3">
          <div className="flex-1 relative min-w-0">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={'Type naturally: "Room 101 temp 98.6 and BP 120/80"'}
              className="input pr-4 lg:pr-44"
            />
            <div className="hidden lg:flex absolute right-2 top-1/2 transform -translate-y-1/2 items-center space-x-1">
              {quickButtons.map((btn) => (
                <button
                  key={btn.label}
                  type="button"
                  onClick={() => setInput(btn.example)}
                  className="px-2 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded text-slate-600"
                >
                  {btn.label}
                </button>
              ))}
            </div>
          </div>

          <div className="lg:hidden flex items-center gap-2 overflow-x-auto scrollbar-thin">
            {quickButtons.map((btn) => (
              <button
                key={btn.label}
                type="button"
                onClick={() => setInput(btn.example)}
                className="px-2.5 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded-md text-slate-700 shrink-0"
              >
                {btn.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setIsRecording(!isRecording)}
            className={`p-2.5 rounded-lg transition-colors self-end lg:self-auto ${
              isRecording 
                ? 'bg-rose-100 text-rose-600 hover:bg-rose-200' 
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
          </button>

          <button type="submit" className="btn-primary self-end lg:self-auto">
            <Send className="w-4 h-4 mr-2" />
            Record
          </button>
        </form>

        {status !== 'idle' && (
          <div className={`mt-3 p-3 rounded-lg flex items-center space-x-2 ${
            status === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}>
            {status === 'success' ? (
              <Check className="w-4 h-4" />
            ) : (
              <AlertTriangle className="w-4 h-4" />
            )}
            <span className="text-sm">{statusMessage}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function VitalCard({
  title,
  value,
  unit,
  icon: Icon,
  status,
  delta,
}: {
  title: string
  value: string | number
  unit: string
  icon: React.ElementType
  status: 'normal' | 'elevated' | 'high' | 'critical' | 'low'
  delta?: { value: number; direction: 'up' | 'down' | 'stable' }
}) {
  const statusColors = {
    normal: 'bg-green-50 border-green-200 text-green-700',
    elevated: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    high: 'bg-red-50 border-red-200 text-red-700',
    critical: 'bg-red-100 border-red-300 text-red-800',
    low: 'bg-blue-50 border-blue-200 text-blue-700'
  }

  const iconColors = {
    normal: 'text-green-600',
    elevated: 'text-yellow-600',
    high: 'text-red-600',
    critical: 'text-red-700',
    low: 'text-blue-600'
  }

  return (
    <div className={`card border-l-4 ${statusColors[status]}`}>
      <div className="card-body">
        <div className="flex items-start justify-between">
          <div>
            <p className="vital-label">{title}</p>
            <div className="flex items-baseline mt-1">
              <span className="vital-value">{value}</span>
              <span className="vital-unit">{unit}</span>
            </div>
            {delta && (
              <div className={`flex items-center mt-1 text-sm ${
                delta.direction === 'up' ? 'delta-positive' : 
                delta.direction === 'down' ? 'delta-negative' : 'delta-neutral'
              }`}>
                {delta.direction === 'up' && <ArrowUp className="w-3 h-3 mr-1" />}
                {delta.direction === 'down' && <ArrowDown className="w-3 h-3 mr-1" />}
                {delta.direction === 'stable' && <Minus className="w-3 h-3 mr-1" />}
                <span>{delta.value > 0 ? '+' : ''}{delta.value}</span>
                <span className="text-gray-400 ml-1">vs yesterday</span>
              </div>
            )}
          </div>
          <Icon className={`w-6 h-6 ${iconColors[status]}`} />
        </div>
      </div>
    </div>
  )
}

function VitalSignsDeltaChart({
  vitalType,
  title,
  data,
  deltaMetrics,
  compact = false,
  showHistory = false
}: {
  vitalType: string
  title: string
  data: VitalReading[]
  deltaMetrics: DeltaMetrics | null
  compact?: boolean
  showHistory?: boolean
}) {
  const filteredData = useMemo(() => {
    return data
      .filter(v => {
        if (vitalType === 'blood_pressure') {
          return v.vital_type === 'systolic' || v.vital_type === 'diastolic'
        }
        return v.vital_type === vitalType
      })
      .slice(0, showHistory ? 50 : 20)
  }, [data, vitalType, showHistory])

  const chartData = useMemo(() => {
    const grouped: Record<string, Record<string, unknown>> = {}
    
    filteredData.forEach(reading => {
      const timeKey = reading.timestamp
      if (!grouped[timeKey]) {
        grouped[timeKey] = { 
          timestamp: timeKey,
          time: format(parseISO(reading.timestamp), 'MMM d HH:mm')
        }
      }
      grouped[timeKey][reading.vital_type] = reading.value
    })

    return Object.values(grouped).reverse()
  }, [filteredData])

  const currentDelta = deltaMetrics?.deltas?.[
    vitalType === 'blood_pressure' ? 'bp_systolic' : vitalType
  ]

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'normal': return '#22c55e'
      case 'elevated': return '#f59e0b'
      case 'high': return '#ef4444'
      case 'critical': return '#dc2626'
      case 'low': return '#3b82f6'
      default: return '#6b7280'
    }
  }

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">{title}</h3>
        {currentDelta && (
          <div className="flex items-center space-x-2">
            <span 
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: getStatusColor(currentDelta.significance) }}
            />
            <span className="text-sm text-gray-600 capitalize">
              {currentDelta.significance}
            </span>
          </div>
        )}
      </div>
      <div className="card-body">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={compact ? 150 : 250}>
            {vitalType === 'blood_pressure' ? (
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="systolicGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="diastolicGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[60, 180]} tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <Tooltip />
                <ReferenceLine y={120} stroke="#22c55e" strokeDasharray="5 5" />
                <ReferenceLine y={140} stroke="#f59e0b" strokeDasharray="5 5" />
                <Area type="monotone" dataKey="systolic" stroke="#ef4444" fill="url(#systolicGradient)" strokeWidth={2} name="Systolic" />
                <Area type="monotone" dataKey="diastolic" stroke="#3b82f6" fill="url(#diastolicGradient)" strokeWidth={2} name="Diastolic" />
                <Legend />
              </AreaChart>
            ) : (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <Tooltip />
                <Line type="monotone" dataKey={vitalType} stroke="#0ea5e9" strokeWidth={2} dot={{ fill: '#0ea5e9', r: 3 }} />
              </LineChart>
            )}
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-32 text-gray-400">
            <p>No data available</p>
          </div>
        )}
      </div>
    </div>
  )
}

function parseAssistantMessage(content: string): AssistantMessageBlock[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: AssistantMessageBlock[] = []

  let index = 0
  while (index < lines.length) {
    const rawLine = lines[index].trimEnd()
    const trimmed = rawLine.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (/^(\*|-)\s+/.test(trimmed)) {
      const items: string[] = []
      while (index < lines.length) {
        const candidate = lines[index].trim()
        if (!/^(\*|-)\s+/.test(candidate)) break
        items.push(candidate.replace(/^(\*|-)\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'bullet', items })
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = []
      while (index < lines.length) {
        const candidate = lines[index].trim()
        if (!/^\d+\.\s+/.test(candidate)) break
        items.push(candidate.replace(/^\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'numbered', items })
      continue
    }

    const markdownHeadingMatch = trimmed.match(/^#{1,3}\s+(.+)$/)
    if (markdownHeadingMatch) {
      blocks.push({ type: 'heading', text: markdownHeadingMatch[1].trim() })
      index += 1
      continue
    }

    const boldHeadingMatch = trimmed.match(/^\*\*(.+)\*\*:?$/)
    if (boldHeadingMatch) {
      const headingText = boldHeadingMatch[1].trim()
      if (/clinical alert/i.test(headingText)) {
        blocks.push({ type: 'alert', text: headingText })
      } else {
        blocks.push({ type: 'heading', text: headingText })
      }
      index += 1
      continue
    }

    const paragraphLines: string[] = [trimmed]
    index += 1
    while (index < lines.length) {
      const nextTrimmed = lines[index].trim()
      if (!nextTrimmed) break
      if (
        /^(\*|-)\s+/.test(nextTrimmed) ||
        /^\d+\.\s+/.test(nextTrimmed) ||
        /^#{1,3}\s+/.test(nextTrimmed) ||
        /^\*\*(.+)\*\*:?$/.test(nextTrimmed)
      ) {
        break
      }
      paragraphLines.push(nextTrimmed)
      index += 1
    }

    const paragraphText = paragraphLines.join(' ')
    if (/clinical alert/i.test(paragraphText)) {
      blocks.push({ type: 'alert', text: paragraphText })
    } else {
      blocks.push({ type: 'paragraph', text: paragraphText })
    }
  }

  return blocks
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const pattern = /(\*\*[^*]+?\*\*|`[^`]+?`|\*[^*\n]+?\*)/g

  let lastIndex = 0
  let match = pattern.exec(text)

  while (match) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }

    const token = match[0]
    const key = `${match.index}-${token}`
    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(<strong key={key} className="font-semibold text-slate-900">{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(
        <code key={key} className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-800">
          {token.slice(1, -1)}
        </code>
      )
    } else if (token.startsWith('*') && token.endsWith('*')) {
      nodes.push(<em key={key} className="italic">{token.slice(1, -1)}</em>)
    } else {
      nodes.push(token)
    }

    lastIndex = match.index + token.length
    match = pattern.exec(text)
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes
}

function AssistantMessageBody({ content }: { content: string }) {
  const blocks = useMemo(() => parseAssistantMessage(content), [content])

  return (
    <div className="text-sm leading-relaxed space-y-2">
      {blocks.map((block, blockIndex) => {
        const blockKey = `${block.type}-${blockIndex}`

        if (block.type === 'heading') {
          return (
            <p key={blockKey} className="font-semibold text-slate-900">
              {renderInlineMarkdown(block.text)}
            </p>
          )
        }

        if (block.type === 'alert') {
          return (
            <div key={blockKey} className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900">
              {renderInlineMarkdown(block.text)}
            </div>
          )
        }

        if (block.type === 'bullet') {
          return (
            <ul key={blockKey} className="list-disc pl-5 space-y-1 text-slate-800">
              {block.items.map((item, itemIndex) => (
                <li key={`${blockKey}-item-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
              ))}
            </ul>
          )
        }

        if (block.type === 'numbered') {
          return (
            <ol key={blockKey} className="list-decimal pl-5 space-y-1 text-slate-800">
              {block.items.map((item, itemIndex) => (
                <li key={`${blockKey}-item-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
              ))}
            </ol>
          )
        }

        return (
          <p key={blockKey} className="text-slate-800">
            {renderInlineMarkdown(block.text)}
          </p>
        )
      })}
    </div>
  )
}

function ChatInterface({
  patientId,
  patientName,
  chatState,
  onDraftChange,
  onSendMessage,
  onCreateSession,
  onSelectSession,
}: {
  patientId: string
  patientName: string
  chatState: PatientChatState
  onDraftChange: (patientId: string, value: string) => void
  onSendMessage: (patientId: string, value: string) => Promise<void>
  onCreateSession: (patientId: string) => void
  onSelectSession: (patientId: string, sessionId: string) => void
}) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [isHistoryCollapsed, setIsHistoryCollapsed] = useState(false)

  const activeSession = useMemo(() => {
    if (!chatState.activeSessionId) return null
    return chatState.sessions.find((session) => session.id === chatState.activeSessionId) || null
  }, [chatState.activeSessionId, chatState.sessions])

  useEffect(() => {
    if (chatState.activeSessionId) {
      const active = chatState.sessions.find((session) => session.id === chatState.activeSessionId)
      if (active && !active.messagesLoaded) {
        onSelectSession(patientId, active.id)
      }
      return
    }

    if (chatState.sessions.length > 0) {
      onSelectSession(patientId, chatState.sessions[0].id)
    }
  }, [chatState.sessions, chatState.activeSessionId, onSelectSession, patientId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeSession?.messages, chatState.isLoading])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (chatState.isLoading) return
    await onSendMessage(patientId, chatState.draftInput)
  }

  return (
    <div className="card h-[72vh] min-h-[520px] overflow-hidden">
      <div className="flex h-full flex-col lg:flex-row">
        <aside
          className={`border-b lg:border-b-0 lg:border-r border-slate-200/80 bg-slate-50/70 flex flex-col transition-all duration-200 ${
            isHistoryCollapsed ? 'lg:w-16' : 'lg:w-72'
          }`}
        >
          <div className="p-3 border-b border-slate-200/80 flex items-center justify-between">
            <div className="flex items-center space-x-2 overflow-hidden">
              <History className="w-4 h-4 text-slate-500" />
              {!isHistoryCollapsed && <span className="text-sm font-semibold text-slate-800">History</span>}
            </div>
            <div className="flex items-center space-x-1">
              {!isHistoryCollapsed && (
                <button
                  type="button"
                  className="btn-ghost !px-2 !py-1"
                  onClick={() => onCreateSession(patientId)}
                  title="Start new chat"
                >
                  <Plus className="w-4 h-4" />
                </button>
              )}
              <button
                type="button"
                className="hidden lg:inline-flex btn-ghost !px-2 !py-1"
                onClick={() => setIsHistoryCollapsed((value) => !value)}
                title={isHistoryCollapsed ? 'Expand history' : 'Collapse history'}
              >
                {isHistoryCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {isHistoryCollapsed ? (
            <div className="hidden lg:flex flex-1 flex-col items-center justify-start p-2 gap-2">
              <button
                type="button"
                className="btn-ghost !p-2"
                onClick={() => onCreateSession(patientId)}
                title="Start new chat"
              >
                <Plus className="w-4 h-4" />
              </button>
              <span className="text-[11px] text-slate-500 [writing-mode:vertical-rl] rotate-180 tracking-wide">
                HISTORY
              </span>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto p-2 space-y-2 scrollbar-thin">
              {chatState.sessions.length === 0 && (
                <div className="text-center py-6 px-3">
                  <p className="text-xs text-slate-500">No saved chats for this patient.</p>
                  <button
                    type="button"
                    onClick={() => onCreateSession(patientId)}
                    className="mt-3 btn-secondary !px-3 !py-1.5 text-xs"
                  >
                    Start first chat
                  </button>
                </div>
              )}

              {chatState.sessions.map((session) => {
                const preview =
                  session.lastMessagePreview ||
                  session.messages[session.messages.length - 1]?.content ||
                  'No messages yet'
                const messageCount =
                  typeof session.messageCount === 'number'
                    ? session.messageCount
                    : session.messages.length
                const isActive = session.id === chatState.activeSessionId
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => onSelectSession(patientId, session.id)}
                    className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                      isActive
                        ? 'border-teal-300 bg-teal-50/80'
                        : 'border-slate-200 bg-white hover:bg-slate-50'
                    }`}
                  >
                    <p className={`text-sm font-medium truncate ${isActive ? 'text-teal-800' : 'text-slate-800'}`}>
                      {session.title}
                    </p>
                    <p className="text-xs text-slate-500 truncate mt-1">{preview}</p>
                    <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-400">
                      <span>{messageCount} msg</span>
                      <span className="inline-flex items-center">
                        <Clock className="w-3 h-3 mr-1" />
                        {format(session.updatedAt, 'MMM d HH:mm')}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </aside>

        <div className="flex-1 min-h-0 flex flex-col">
          <div className="card-header border-b border-slate-200/80">
            <h3 className="font-semibold text-slate-900 flex items-center">
              <MessageSquare className="w-5 h-5 mr-2 text-teal-700" />
              Clinical Assistant Chat - {patientName}
            </h3>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
            {!activeSession && (
              <div className="text-center py-8">
                <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500">Create or select a chat from history to continue.</p>
              </div>
            )}

            {activeSession && activeSession.messages.length === 0 && (
              <div className="text-center py-8">
                <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500">Ask naturally: meds due, trend summary, risk check.</p>
              </div>
            )}

            {activeSession?.messages.map((message) => (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] rounded-lg px-4 py-2.5 ${
                  message.role === 'user' ? 'bg-teal-700 text-white' : 'bg-slate-100 text-slate-900'
                }`}>
                  {message.role === 'assistant' ? (
                    <AssistantMessageBody content={message.content} />
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  )}
                  <p className={`text-xs mt-1 ${message.role === 'user' ? 'text-teal-100' : 'text-slate-400'}`}>
                    {format(message.timestamp, 'HH:mm')}
                  </p>
                </div>
              </div>
            ))}

            {chatState.isLoading && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-lg px-4 py-3">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-slate-200/80">
            <form onSubmit={handleSubmit} className="flex items-center space-x-2">
              <input
                type="text"
                value={chatState.draftInput}
                onChange={(e) => onDraftChange(patientId, e.target.value)}
                placeholder="Ask naturally: meds due, trend summary, risk check..."
                className="input flex-1"
                disabled={chatState.isLoading}
              />
              <button
                type="submit"
                disabled={!chatState.draftInput.trim() || chatState.isLoading}
                className="btn-primary disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

function MedicationAdherenceRing({ adherenceRate = 85 }: { adherenceRate?: number }) {
  const circumference = 2 * Math.PI * 45
  const strokeDashoffset = circumference - (adherenceRate / 100) * circumference

  const getColor = (rate: number) => {
    if (rate >= 90) return '#22c55e'
    if (rate >= 75) return '#f59e0b'
    return '#ef4444'
  }

  return (
    <div className="relative w-32 h-32">
      <svg className="w-full h-full transform -rotate-90">
        <circle cx="64" cy="64" r="45" stroke="#e5e7eb" strokeWidth="10" fill="none" />
        <circle
          cx="64" cy="64" r="45"
          stroke={getColor(adherenceRate)}
          strokeWidth="10"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-gray-900">{adherenceRate}%</span>
        <span className="text-xs text-gray-500">Adherence</span>
      </div>
    </div>
  )
}

function MedicationList({ medications }: { medications: Medication[] }) {
  if (!medications || medications.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <Pill className="w-8 h-8 mx-auto mb-2 text-gray-300" />
        <p>No active medications</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-gray-100">
      {medications.map((med) => (
        <div key={med.id} className="py-3 flex items-center justify-between">
          <div>
            <p className="font-medium text-gray-900">{med.name}</p>
            <p className="text-sm text-gray-500">{med.dose} {med.route} {med.frequency}</p>
          </div>
          <span className={`badge ${med.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
            {med.status}
          </span>
        </div>
      ))}
    </div>
  )
}

function VitalsOverviewGrid({ deltaMetrics }: { deltaMetrics: DeltaMetrics | null }) {
  if (!deltaMetrics?.has_data) {
    return (
      <div className="text-center py-8 text-gray-500">
        <Activity className="w-8 h-8 mx-auto mb-2 text-gray-300" />
        <p>No vitals data available</p>
      </div>
    )
  }

  const getStatus = (significance: string): 'normal' | 'elevated' | 'high' | 'critical' | 'low' => {
    switch (significance) {
      case 'normal': return 'normal'
      case 'elevated': case 'borderline': return 'elevated'
      case 'high': return 'high'
      case 'critical': case 'critical_low': return 'critical'
      case 'low': return 'low'
      default: return 'normal'
    }
  }

  const getDelta = (key: string) => {
    const delta = deltaMetrics.deltas?.[key]
    if (!delta?.vs_yesterday) return undefined
    const change = delta.vs_yesterday.absolute_change
    return {
      value: Math.round(change * 10) / 10,
      direction: change > 0 ? 'up' as const : change < 0 ? 'down' as const : 'stable' as const
    }
  }

  const vitals = [
    { key: 'bp_systolic', title: 'Blood Pressure', value: deltaMetrics.current?.systolic && deltaMetrics.current?.diastolic ? `${deltaMetrics.current.systolic}/${deltaMetrics.current.diastolic}` : '--', unit: 'mmHg', icon: Heart },
    { key: 'heart_rate', title: 'Heart Rate', value: deltaMetrics.current?.heart_rate ?? '--', unit: 'bpm', icon: Activity },
    { key: 'temperature', title: 'Temperature', value: deltaMetrics.current?.temperature?.toFixed(1) ?? '--', unit: 'C', icon: Thermometer },
    { key: 'spo2', title: 'SpO2', value: deltaMetrics.current?.spo2 ?? '--', unit: '%', icon: Droplets },
    { key: 'respiratory_rate', title: 'Resp Rate', value: deltaMetrics.current?.respiratory_rate ?? '--', unit: '/min', icon: Wind },
    { key: 'weight', title: 'Weight', value: deltaMetrics.current?.weight?.toFixed(1) ?? '--', unit: 'kg', icon: Scale }
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {vitals.map((vital) => (
        <VitalCard
          key={vital.key}
          title={vital.title}
          value={vital.value}
          unit={vital.unit}
          icon={vital.icon}
          status={getStatus(deltaMetrics.clinical_status?.[vital.key] || 'normal')}
          delta={getDelta(vital.key)}
        />
      ))}
    </div>
  )
}
