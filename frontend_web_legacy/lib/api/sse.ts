type MessageHandler = (data: unknown) => void
type ConnectionHandler = () => void
type ErrorHandler = (event: Event) => void

interface SSEOptions {
  reconnectAttempts?: number
  reconnectInterval?: number
}

class SSEClient {
  private eventSource: EventSource | null = null
  private url: string
  private options: Required<SSEOptions>
  private messageHandlers: Set<MessageHandler> = new Set()
  private connectHandlers: Set<ConnectionHandler> = new Set()
  private disconnectHandlers: Set<ConnectionHandler> = new Set()
  private errorHandlers: Set<ErrorHandler> = new Set()
  private reconnectCount = 0
  private isIntentionallyClosed = false

  constructor(patientId: string, options: SSEOptions = {}) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'
    this.url = `${apiBase}/api/stream/${patientId}`
    this.options = {
      reconnectAttempts: options.reconnectAttempts ?? 5,
      reconnectInterval: options.reconnectInterval ?? 3000
    }
  }

  connect(): void {
    if (this.eventSource && this.eventSource.readyState !== EventSource.CLOSED) {
      return
    }

    this.isIntentionallyClosed = false
    this.eventSource = new EventSource(this.url)

    this.eventSource.onopen = () => {
      this.reconnectCount = 0
      this.connectHandlers.forEach((handler) => handler())
    }

    this.eventSource.onmessage = (event) => {
      let payload: unknown = event.data
      try {
        payload = JSON.parse(event.data)
      } catch {
        payload = event.data
      }
      this.messageHandlers.forEach((handler) => handler(payload))
    }

    this.eventSource.onerror = (event) => {
      this.errorHandlers.forEach((handler) => handler(event))
      this.disconnectHandlers.forEach((handler) => handler())

      if (!this.isIntentionallyClosed && this.reconnectCount < this.options.reconnectAttempts) {
        this.reconnectCount += 1
        this.eventSource?.close()
        this.eventSource = null
        setTimeout(() => this.connect(), this.options.reconnectInterval)
      }
    }
  }

  disconnect(): void {
    this.isIntentionallyClosed = true
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
    this.disconnectHandlers.forEach((handler) => handler())
  }

  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler)
    return () => this.messageHandlers.delete(handler)
  }

  onConnect(handler: ConnectionHandler): () => void {
    this.connectHandlers.add(handler)
    return () => this.connectHandlers.delete(handler)
  }

  onDisconnect(handler: ConnectionHandler): () => void {
    this.disconnectHandlers.add(handler)
    return () => this.disconnectHandlers.delete(handler)
  }

  onError(handler: ErrorHandler): () => void {
    this.errorHandlers.add(handler)
    return () => this.errorHandlers.delete(handler)
  }

  get isConnected(): boolean {
    return this.eventSource?.readyState === EventSource.OPEN
  }
}

export function createSSEClient(patientId: string, options?: SSEOptions): SSEClient {
  return new SSEClient(patientId, options)
}

export default SSEClient
