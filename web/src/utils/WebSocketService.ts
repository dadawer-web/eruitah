import { MessageType } from './MessageTypes';

// 基础消息类型接口
interface BaseMessage {
  msgid: number;
  msgtype: MessageType;
}

// WebSocket连接状态类型
type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

class WebSocketService {
  private ws: WebSocket | null = null;
  private status: ConnectionStatus = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000;
  private url: string;
  private messageHandlers: Map<number, (data: any) => void> = new Map();
  private globalHandlers: ((data: any) => void)[] = [];
  private heartbeatInterval: number | null = null;

  constructor(url: string) {
    this.url = url;
  }

  // 连接WebSocket服务器
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.status === 'connected' || this.status === 'connecting') {
        resolve();
        return;
      }

      this.status = 'connecting';
      
      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('WebSocket连接已建立');
          this.status = 'connected';
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onclose = () => {
          console.log('WebSocket连接已关闭');
          this.status = 'disconnected';
          this.stopHeartbeat();
          this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket错误:', error);
          this.status = 'disconnected';
          reject(error);
        };
      } catch (error) {
        console.error('WebSocket连接失败:', error);
        this.status = 'disconnected';
        reject(error);
      }
    });
  }

  // 断开连接
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.status = 'disconnected';
    this.stopHeartbeat();
    this.reconnectAttempts = 0;
  }

  // 发送消息
  send(message: BaseMessage): void {
    if (this.status !== 'connected' || !this.ws) {
      console.error('WebSocket未连接，无法发送消息');
      return;
    }

    try {
      const messageString = JSON.stringify(message);
      this.ws.send(messageString);
    } catch (error) {
      console.error('发送消息失败:', error);
    }
  }

  // 处理接收到的消息
  private handleMessage(data: string): void {
    try {
      const message = JSON.parse(data);
      
      // 调用特定消息类型的处理器
      if (message.msgtype && this.messageHandlers.has(message.msgtype)) {
        const handler = this.messageHandlers.get(message.msgtype);
        if (handler) {
          handler(message);
        }
      }
      
      // 调用全局消息处理器
      this.globalHandlers.forEach(handler => handler(message));
    } catch (error) {
      console.error('解析消息失败:', error, '消息内容:', data);
    }
  }

  // 注册消息处理器
  onMessage(msgtype: number, handler: (data: any) => void): void {
    this.messageHandlers.set(msgtype, handler);
  }

  // 注册全局消息处理器
  onAnyMessage(handler: (data: any) => void): void {
    this.globalHandlers.push(handler);
  }

  // 移除消息处理器
  offMessage(msgtype: number): void {
    this.messageHandlers.delete(msgtype);
  }

  // 移除全局消息处理器
  offAnyMessage(handler: (data: any) => void): void {
    this.globalHandlers = this.globalHandlers.filter(h => h !== handler);
  }

  // 获取连接状态
  getStatus(): ConnectionStatus {
    return this.status;
  }

  // 尝试重连
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('WebSocket重连失败，已达到最大重试次数');
      return;
    }

    this.reconnectAttempts++;
    console.log(`WebSocket尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

    setTimeout(() => {
      this.connect().catch(() => {
        console.error('重连失败，稍后将再次尝试');
      });
    }, this.reconnectInterval);
  }

  // 启动心跳
  private startHeartbeat(): void {
    // 每30秒发送一次心跳
    this.heartbeatInterval = window.setInterval(() => {
      if (this.status === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000);
  }

  // 停止心跳
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }
}

// 创建WebSocket服务实例
export const wsService = new WebSocketService('ws://localhost:6000');
export default WebSocketService;