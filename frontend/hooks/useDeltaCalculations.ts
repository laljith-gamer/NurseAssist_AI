import { useMemo } from 'react'
import type { VitalReading, DeltaMetrics, VitalDelta } from '@/lib/types'

interface DeltaResult {
  current: number | null
  vsYesterday: number | null
  vs7DayAvg: number | null
  vsBaseline: number | null
  trend: 'stable' | 'increasing' | 'decreasing' | 'rapidly_increasing' | 'rapidly_decreasing'
  significance: string
  percentChange: number | null
}

interface UseDeltaCalculationsResult {
  getVitalDelta: (vitalType: string) => DeltaResult | null
  getBPDelta: () => { systolic: DeltaResult | null; diastolic: DeltaResult | null }
  getAllDeltas: () => Record<string, DeltaResult>
  hasSignificantChanges: boolean
  criticalAlerts: string[]
}

export function useDeltaCalculations(
  vitals: VitalReading[],
  deltaMetrics: DeltaMetrics | null
): UseDeltaCalculationsResult {
  
  const getVitalDelta = useMemo(() => {
    return (vitalType: string): DeltaResult | null => {
      if (!deltaMetrics?.deltas) return null

      const delta = deltaMetrics.deltas[vitalType as keyof typeof deltaMetrics.deltas]
      if (!delta) return null

      return {
        current: delta.current,
        vsYesterday: delta.vs_yesterday?.absolute_change ?? null,
        vs7DayAvg: delta.vs_7day_avg?.absolute_change ?? null,
        vsBaseline: delta.vs_baseline?.absolute_change ?? null,
        trend: delta.trend as DeltaResult['trend'],
        significance: delta.significance,
        percentChange: delta.vs_yesterday?.percent_change ?? null
      }
    }
  }, [deltaMetrics])

  const getBPDelta = useMemo(() => {
    return () => ({
      systolic: getVitalDelta('bp_systolic'),
      diastolic: getVitalDelta('bp_diastolic')
    })
  }, [getVitalDelta])

  const getAllDeltas = useMemo(() => {
    return (): Record<string, DeltaResult> => {
      const vitalTypes = [
        'bp_systolic',
        'bp_diastolic',
        'heart_rate',
        'temperature',
        'spo2',
        'respiratory_rate',
        'weight',
        'glucose'
      ]

      const result: Record<string, DeltaResult> = {}
      
      for (const vitalType of vitalTypes) {
        const delta = getVitalDelta(vitalType)
        if (delta) {
          result[vitalType] = delta
        }
      }

      return result
    }
  }, [getVitalDelta])

  const hasSignificantChanges = useMemo(() => {
    if (!deltaMetrics?.clinical_status) return false

    return Object.values(deltaMetrics.clinical_status).some(
      status => ['critical', 'critical_low', 'high'].includes(status)
    )
  }, [deltaMetrics])

  const criticalAlerts = useMemo(() => {
    return deltaMetrics?.alerts ?? []
  }, [deltaMetrics])

  return {
    getVitalDelta,
    getBPDelta,
    getAllDeltas,
    hasSignificantChanges,
    criticalAlerts
  }
}

export function calculateLocalDelta(
  readings: VitalReading[],
  vitalType: string
): DeltaResult | null {
  const filtered = readings
    .filter(r => r.vital_type === vitalType)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  if (filtered.length === 0) return null

  const current = filtered[0].value
  
  const now = new Date()
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

  const yesterdayReading = filtered.find(r => {
    const readingTime = new Date(r.timestamp)
    return readingTime <= yesterday
  })

  const weekReadings = filtered.filter(r => {
    const readingTime = new Date(r.timestamp)
    return readingTime >= weekAgo
  })

  const vsYesterday = yesterdayReading ? current - yesterdayReading.value : null
  
  const vs7DayAvg = weekReadings.length > 0
    ? current - (weekReadings.reduce((sum, r) => sum + r.value, 0) / weekReadings.length)
    : null

  let trend: DeltaResult['trend'] = 'stable'
  if (filtered.length >= 3) {
    const recentValues = filtered.slice(0, 5).map(r => r.value)
    const avgDiff = recentValues.slice(0, -1).reduce((sum, val, i) => {
      return sum + (val - recentValues[i + 1])
    }, 0) / (recentValues.length - 1)

    if (avgDiff > 5) trend = 'rapidly_increasing'
    else if (avgDiff > 1) trend = 'increasing'
    else if (avgDiff < -5) trend = 'rapidly_decreasing'
    else if (avgDiff < -1) trend = 'decreasing'
  }

  return {
    current,
    vsYesterday,
    vs7DayAvg,
    vsBaseline: null,
    trend,
    significance: 'normal',
    percentChange: vsYesterday && yesterdayReading 
      ? (vsYesterday / yesterdayReading.value) * 100 
      : null
  }
}

export function formatDelta(value: number | null, decimals: number = 1): string {
  if (value === null) return '--'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}`
}

export function getDeltaColor(value: number | null, inverted: boolean = false): string {
  if (value === null) return 'text-gray-500'
  
  if (inverted) {
    if (value > 0) return 'text-green-600'
    if (value < 0) return 'text-red-600'
  } else {
    if (value > 0) return 'text-red-600'
    if (value < 0) return 'text-green-600'
  }
  
  return 'text-gray-500'
}

export function getTrendIcon(trend: DeltaResult['trend']): string {
  switch (trend) {
    case 'rapidly_increasing': return 'trending-up'
    case 'increasing': return 'arrow-up'
    case 'rapidly_decreasing': return 'trending-down'
    case 'decreasing': return 'arrow-down'
    default: return 'minus'
  }
}

export default useDeltaCalculations