// 通信服务类，结合WebSocket和模拟数据功能
class CommunicationService {
  private ws: WebSocket | null = null;
  private serverUrl: string;
  private status: 'disconnected' | 'connected' = 'disconnected';
  private handlers: Map<number, ((data: any) => void)[]> = new Map();
  private globalHandlers: ((data: any) => void)[] = [];
  private useMockData: boolean = false;

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
  }

  // 连接服务器
  connect(): Promise<void> {
    return new Promise((resolve) => {
      try {
        this.ws = new WebSocket(this.serverUrl);
        
        this.ws.onopen = () => {
          this.status = 'connected';
          this.useMockData = false;
          console.log('WebSocket连接已建立，使用真实后端服务');
          resolve();
        };

        this.ws.onclose = () => {
          this.status = 'disconnected';
          console.log('WebSocket连接已关闭');
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket连接错误:', error);
          console.log('切换到模拟数据模式');
          this.useMockData = true;
          this.status = 'connected'; // 模拟连接成功
          resolve(); // 即使失败也resolve，让应用能继续运行
        };

        this.ws.onmessage = (event) => {
          try {
            // 尝试解析JSON消息
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (parseError) {
            console.error('解析消息失败:', parseError, event.data);
          }
        };
      } catch (error) {
        console.error('创建WebSocket连接失败:', error);
        console.log('切换到模拟数据模式');
        this.useMockData = true;
        this.status = 'connected'; // 模拟连接成功
        resolve(); // 即使失败也resolve，让应用能继续运行
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
    this.handlers.clear();
    this.globalHandlers = [];
  }

  // 发送消息
  send(data: any): void {
    console.log('发送消息:', data);
    
    // 如果连接到真实后端，尝试发送消息
    if (this.status === 'connected' && this.ws && !this.useMockData) {
      try {
        this.ws.send(JSON.stringify(data));
        console.log('消息已发送到真实后端');
        return;
      } catch (error) {
        console.error('发送消息到真实后端失败，切换到模拟数据:', error);
        this.useMockData = true;
      }
    }

    // 模拟数据处理
    if (this.useMockData) {
      console.log('使用模拟数据响应');
      
      // 模拟登录响应
      if (data.msgtype === 1) { // LOGIN_MSG
        setTimeout(() => {
          const mockResponse = {
            msgtype: 2, // LOGIN_MSG_ACK
            error: 0, // 模拟登录成功
            userid: data.id,
            name: `用户${data.id}`,
            friends: [
              { userid: 1, name: '用户1', onlineStatus: true },
              { userid: 2, name: '用户2', onlineStatus: false }
            ],
            groups: [
              { groupid: 101, name: '测试群组', desc: '这是一个测试群组' }
            ]
          };
          this.handleMessage(mockResponse);
        }, 300);
      }
      
      // 模拟注册响应
      if (data.msgtype === 4) { // REG_MSG
        setTimeout(() => {
          const mockResponse = {
            msgtype: 5, // REG_MSG_ACK
            error: 0 // 模拟注册成功
          };
          this.handleMessage(mockResponse);
        }, 300);
      }
      
      // 模拟添加好友响应
      if (data.msgtype === 8) { // ADD_FRIEND_MSG
        setTimeout(() => {
          const mockResponse = {
            msgtype: 9, // ADD_FRIEND_MSG_ACK
            error: 0 // 模拟添加成功
          };
          this.handleMessage(mockResponse);
        }, 300);
      }
      
      // 模拟创建群组响应
      if (data.msgtype === 10) { // CREATE_GROUP_MSG
        setTimeout(() => {
          const mockResponse = {
            msgtype: 12, // ADD_GROUP_MSG_ACK
            error: 0 // 模拟创建成功
          };
          this.handleMessage(mockResponse);
        }, 300);
      }
    }
  }

  // 监听特定消息类型
  onMessage(msgType: number, handler: (data: any) => void): void {
    if (!this.handlers.has(msgType)) {
      this.handlers.set(msgType, []);
    }
    this.handlers.get(msgType)!.push(handler);
  }

  // 取消监听特定消息类型
  offMessage(msgType: number): void {
    this.handlers.delete(msgType);
  }

  // 监听所有消息
  onGlobalMessage(handler: (data: any) => void): void {
    this.globalHandlers.push(handler);
  }

  // 取消监听所有消息
  offGlobalMessage(): void {
    this.globalHandlers = [];
  }

  // 处理接收到的消息
  private handleMessage(data: any): void {
    // 调用对应的消息处理器
    if (data.msgtype && this.handlers.has(data.msgtype)) {
      this.handlers.get(data.msgtype)!.forEach(handler => handler(data));
    }
    
    // 调用全局消息处理器
    this.globalHandlers.forEach(handler => handler(data));
  }

  // 获取连接状态
  getStatus(): 'disconnected' | 'connected' {
    return this.status;
  }
}

// 创建通信服务实例，优先尝试连接真实后端，失败时使用模拟数据
export const tcpService = new CommunicationService('ws://localhost:6000');
export default CommunicationService;