# 架构设计文档

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Python   │  │   C++    │  │  Java    │  │   Web    │       │
│  │ Client   │  │  Client  │  │  Client  │  │  Client  │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼───────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                              │
                              │ TCP (Protobuf)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   C++ muduo Bridge Server                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Protobuf Codec Layer                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Encoder    │  │   Decoder    │  │  Checksum    │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              RPC Channel Layer                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │  Connection  │  │  Call Method │  │   Response   │  │   │
│  │  │    Pool      │  │    Router    │  │   Handler    │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              muduo Event Loop                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Acceptor   │  │   EventLoop  │  │  ThreadPool  │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ TCP (Protobuf RPC)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Java Backend Server                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Netty Server Layer                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   BossGroup  │  │ WorkerGroup  │  │   Pipeline   │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              RPC Handler Layer                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Decoder    │  │   Encoder    │  │   Handler    │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Business Logic Layer                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ ChatService  │  │  AI Engine   │  │   Database   │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 数据流分析

### 请求流程

```
1. 客户端发送请求
   ┌──────────┐
   │  Client  │
   └────┬─────┘
        │ 1. ChatRequest (Protobuf)
        ▼
2. C++ muduo 接收并解码
   ┌──────────────┐
   │ muduo Server │
   │  ┌────────┐  │
   │  │Decode  │  │ 2. 解析 Protobuf
   │  │Request │  │
   │  └────────┘  │
   └────┬─────────┘
        │ 3. RpcMessage (Protobuf)
        ▼
3. 通过 RPC Channel 转发
   ┌──────────────┐
   │  RPC Channel │
   │  ┌────────┐  │
   │  │Forward │  │ 3. 封装 RPC 消息
   │  │Request │  │
   │  └────────┘  │
   └────┬─────────┘
        │ 4. TCP 长连接
        ▼
4. Java 后端处理
   ┌──────────────┐
   │Java Backend  │
   │  ┌────────┐  │
   │  │Process │  │ 4. 业务逻辑处理
   │  │Request │  │
   │  └────────┘  │
   └────┬─────────┘
        │ 5. ChatResponse (Protobuf)
        ▼
5. 返回响应
   ┌──────────────┐
   │  RPC Channel │
   │  ┌────────┐  │
   │  │Return  │  │ 5. 接收响应
   │  │Response│  │
   │  └────────┘  │
   └────┬─────────┘
        │ 6. ChatResponse (Protobuf)
        ▼
6. 客户端接收响应
   ┌──────────┐
   │  Client  │
   └──────────┘
```

## 关键技术点

### 1. Protobuf 编解码

#### 编码流程
```cpp
// C++ 端编码
void ProtobufCodec::send(const TcpConnectionPtr& conn,
                         const Message& message) {
    // 1. 序列化消息
    int byte_size = message.ByteSizeLong();
    
    // 2. 写入类型名称
    string typeName = message.GetTypeName();
    
    // 3. 写入 payload
    message.SerializeWithCachedSizesToArray(buffer);
    
    // 4. 计算校验和
    int32_t checkSum = adler32(buffer);
    
    // 5. 发送
    conn->send(buffer);
}
```

#### 解码流程
```java
// Java 端解码
protected void decode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) {
    // 1. 读取长度
    int totalLen = in.readInt();
    
    // 2. 读取类型名称
    String typeName = readTypeName(in);
    
    // 3. 读取 payload
    byte[] payload = readPayload(in);
    
    // 4. 解析消息
    Message message = parseMessage(typeName, payload);
    
    // 5. 输出
    out.add(message);
}
```

### 2. RPC 调用机制

#### C++ 端 RPC Channel
```cpp
void RpcChannel::CallMethod(
    const MethodDescriptor* method,
    RpcController* controller,
    const Message* request,
    Message* response,
    Closure* done) {
    
    // 1. 封装 RPC 消息
    RpcMessage rpcMessage;
    rpcMessage.set_type(RpcMessage::REQUEST);
    rpcMessage.set_id(++id_);
    rpcMessage.set_service_name(method->service()->name());
    rpcMessage.set_method_name(method->name());
    rpcMessage.set_payload(request->SerializeAsString());
    
    // 2. 注册回调
    outstandingCalls_[rpcMessage.id()] = {response, done};
    
    // 3. 发送
    codec_.send(conn_, rpcMessage);
}
```

#### Java 端 RPC 处理
```java
private void handleRpcMessage(ChannelHandlerContext ctx, RpcMessage rpcMessage) {
    if (rpcMessage.getType() == RpcMessage.Type.REQUEST) {
        // 1. 解析请求
        Message request = parseRequest(rpcMessage);
        
        // 2. 调用业务逻辑
        Message response = processRequest(rpcMessage);
        
        // 3. 返回响应
        sendResponse(ctx, rpcMessage.getId(), response);
    }
}
```

### 3. 连接管理

#### C++ 端连接池
```cpp
class RpcChannel {
    TcpClient client_;
    TcpConnectionPtr conn_;
    map<int64_t, OutstandingCall> outstandingCalls_;
    
    void onConnection(const TcpConnectionPtr& conn) {
        if (conn->connected()) {
            conn_ = conn;
            LOG_INFO << "Connected to Java backend";
        } else {
            conn_.reset();
            LOG_INFO << "Disconnected from Java backend";
        }
    }
};
```

#### Java 端连接处理
```java
public class RpcMessageHandler extends SimpleChannelInboundHandler<Message> {
    private Map<Long, ChannelHandlerContext> pendingRequests;
    
    @Override
    protected void channelRead0(ChannelHandlerContext ctx, Message msg) {
        if (msg instanceof RpcMessage) {
            handleRpcMessage(ctx, (RpcMessage) msg);
        }
    }
}
```

## 性能优化策略

### 1. 零拷贝优化

#### muduo Buffer
```cpp
// 避免数据拷贝
void Buffer::ensureWritableBytes(size_t len) {
    if (writableBytes() < len) {
        makeSpace(len);
    }
}

// 直接写入
void Buffer::append(const char* data, size_t len) {
    ensureWritableBytes(len);
    std::copy(data, data + len, beginWrite());
    hasWritten(len);
}
```

### 2. 内存池

#### Protobuf 内存管理
```cpp
// 使用 Arena 分配器
google::protobuf::Arena arena;
ChatRequest* request = google::protobuf::Arena::CreateMessage<ChatRequest>(&arena);
```

### 3. 批处理

#### 批量发送
```cpp
void ChatServer::batchSend(const vector<ChatResponse>& responses) {
    Buffer buf;
    for (const auto& response : responses) {
        codec_.sendToBuffer(response, &buf);
    }
    conn_->send(&buf);
}
```

## 错误处理机制

### 1. 连接断开重连

```cpp
class RpcChannel {
    void onConnection(const TcpConnectionPtr& conn) {
        if (!conn->connected()) {
            // 重连逻辑
            client_.connect();
        }
    }
};
```

### 2. 请求超时

```cpp
class RpcChannel {
    void checkTimeout() {
        for (auto& [id, call] : outstandingCalls_) {
            if (isTimeout(call)) {
                call.controller->SetFailed("Timeout");
                call.done->Run();
                outstandingCalls_.erase(id);
            }
        }
    }
};
```

### 3. 错误响应

```java
private void sendError(ChannelHandlerContext ctx, long id, String errorMessage) {
    RpcMessage errorResponse = RpcMessage.newBuilder()
        .setType(RpcMessage.Type.ERROR)
        .setId(id)
        .setErrorCode(500)
        .setErrorDesc(errorMessage)
        .build();
    
    ctx.writeAndFlush(errorResponse);
}
```

## 监控指标

### 1. 性能指标

```cpp
// C++ 端
class Metrics {
    atomic<int64_t> totalRequests;
    atomic<int64_t> totalLatency;
    atomic<int64_t> errorCount;
    
    void recordLatency(int64_t latency) {
        totalLatency += latency;
        totalRequests++;
    }
};
```

### 2. Java 端监控

```java
public class Metrics {
    private AtomicLong totalRequests = new AtomicLong();
    private AtomicLong totalLatency = new AtomicLong();
    private AtomicLong errorCount = new AtomicLong();
    
    public void recordLatency(long latency) {
        totalLatency.addAndGet(latency);
        totalRequests.incrementAndGet();
    }
}
```

## 扩展性设计

### 1. 水平扩展

```
                    ┌──────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
      ┌──────────┐  ┌──────────┐  ┌──────────┐
      │ Java #1  │  │ Java #2  │  │ Java #3  │
      └──────────┘  └──────────┘  └──────────┘
```

### 2. 服务发现

```java
public interface ServiceDiscovery {
    List<InetSocketAddress> discover(String serviceName);
    void register(String serviceName, InetSocketAddress address);
    void deregister(String serviceName, InetSocketAddress address);
}
```

### 3. 负载均衡

```cpp
class LoadBalancer {
    vector<InetAddress> backends;
    size_t currentIndex;
    
    InetAddress next() {
        return backends[currentIndex++ % backends.size()];
    }
};
```

## 安全性考虑

### 1. TLS 加密

```cpp
// C++ 端
void setupSSL() {
    SSL_CTX* ctx = SSL_CTX_new(TLS_server_method());
    SSL_CTX_use_certificate_file(ctx, "server.crt", SSL_FILETYPE_PEM);
    SSL_CTX_use_PrivateKey_file(ctx, "server.key", SSL_FILETYPE_PEM);
}
```

### 2. 认证机制

```protobuf
message AuthRequest {
    string token = 1;
    string user_id = 2;
}

message AuthResponse {
    bool success = 1;
    string session_id = 2;
}
```

### 3. 限流

```java
public class RateLimiter {
    private final RateLimiter limiter = RateLimiter.create(1000);
    
    public boolean tryAcquire() {
        return limiter.tryAcquire();
    }
}
```

## 总结

这个架构设计实现了：

1. **高性能**：基于 Protobuf 的二进制协议，零拷贝传输
2. **可扩展**：支持水平扩展，服务发现，负载均衡
3. **可靠性**：连接管理，错误处理，超时控制
4. **易维护**：清晰的分层架构，完善的日志和监控

通过这个系统，C++ muduo 和 Java 后端可以实现高效、可靠的异构通信。
