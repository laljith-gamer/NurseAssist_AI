type MessageHandler = (data: any) => void
type ConnectionHandler = () => void

interface WebSocketOptions {
  reconnectAttempts?: number
  reconnectInterval?: number
  heartbeatInterval?: number
}

class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private patientId: string
  private options: Required<WebSocketOptions>
  private messageHandlers: Set<MessageHandler> = new Set()
  private connectHandlers: Set<ConnectionHandler> = new Set()
  private disconnectHandlers: Set<ConnectionHandler> = new Set()
  private reconnectCount = 0
  private heartbeatTimer: NodeJS.Timeout | null = null
  private isIntentionallyClosed = false

  constructor(patientId: string, options: WebSocketOptions = {}) {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001'
    this.url = `${wsBase}/ws/${patientId}`
    this.patientId = patientId
    this.options = {
      reconnectAttempts: options.reconnectAttempts ?? 5,
      reconnectInterval: options.reconnectInterval ?? 3000,
      heartbeatInterval: options.heartbeatInterval ?? 30000
    }
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    this.isIntentionallyClosed = false

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this.reconnectCount = 0
        this.startHeartbeat()
        this.connectHandlers.forEach(handler => handler())
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          this.messageHandlers.forEach(handler => handler(data))
        } catch (error) {
          console.error('Failed to parse WebSocket message')
        }
      }

      this.ws.onclose = () => {
        this.stopHeartbeat()
        this.disconnectHandlers.forEach(handler => handler())

        if (!this.isIntentionallyClosed && this.reconnectCount < this.options.reconnectAttempts) {
          this.reconnectCount++
          setTimeout(() => this.connect(), this.options.reconnectInterval)
        }
      }

      this.ws.onerror = () => {
        console.error('WebSocket error')
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection')
    }
  }

  disconnect(): void {
    this.isIntentionallyClosed = true
    this.stopHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  send(data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
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

  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, this.options.heartbeatInterval)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export function createWebSocketClient(patientId: string, options?: WebSocketOptions): WebSocketClient {
  return new WebSocketClient(patientId, options)
}

export default WebSocketClient
