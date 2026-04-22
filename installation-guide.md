# AI Service 安装配置说明

## 1. 环境要求

### 1.1 基础环境

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| JDK | 17 | 推荐 Eclipse Temurin 17 |
| Maven | 3.9+ | 项目构建工具 |
| Node.js | 18+ | MCP文件系统工具运行环境（代码审查员功能需要） |
| npm/npx | 9+ | MCP Server启动工具 |
| Redis Stack | 7.0+ | 向量存储、聊天记忆、限流、Pub/Sub（需含RedisSearch模块） |
| Neo4j | 5.0+ | 知识图谱存储 |
| g++ | - | C++编译器（代码沙盒功能需要） |
| pdftoppm | - | PDF转图片工具（OCR功能需要） |
| tesseract | - | OCR引擎（扫描版PDF识别需要） |

### 1.2 外部服务API

| 服务 | 用途 | 获取地址 |
|------|------|----------|
| 阿里云DashScope | LLM对话、ASR语音识别、TTS语音合成 | https://dashscope.console.aliyun.com/ |
| SiliconFlow | 文本嵌入（BGE-M3）、重排序（BGE-Reranker） | https://siliconflow.cn/ |
| Serper | 联网搜索 | https://serper.dev/ |

---

## 2. 安装步骤

### 2.1 方式一：本地源码构建

#### Step 1：克隆项目

```bash
cd /your/workspace
git clone <repository-url> ai-service
cd ai-service
```

#### Step 2：安装系统依赖

**Ubuntu/Debian：**

```bash
# C++编译器
sudo apt-get install -y g++

# Node.js + npm（MCP文件系统工具需要）
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# PDF转图片 + OCR（可选，仅扫描版PDF需要）
sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-chi-sim
```

**CentOS/RHEL：**

```bash
sudo yum install -y gcc-c++
sudo yum install -y nodejs npm
sudo yum install -y poppler-utils tesseract tesseract-langpack-chi_sim
```

**macOS：**

```bash
brew install gcc
brew install node
brew install poppler tesseract tesseract-lang
```

#### Step 3：安装并配置Redis

```bash
# Ubuntu
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 设置密码（必须与application.yml一致）
redis-cli CONFIG SET requirepass "123456"
```

**Redis向量搜索模块**（必需）：

Redis需要安装 RedisSearch 模块以支持向量存储功能。推荐使用 Redis Stack：

```bash
# Docker方式（推荐）
docker run -d --name redis-stack \
  -p 6379:6379 \
  -p 8001:8001 \
  -e REDIS_ARGS="--requirepass 123456" \
  redis/redis-stack-server:latest
```

或下载 Redis Stack：https://redis.io/docs/get-started/install-stack/

#### Step 4：安装并配置Neo4j

```bash
# Docker方式（推荐）
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/12345678 \
  neo4j:5

# 或使用APT安装
# 参见 https://neo4j.com/docs/operations-manual/current/installation/linux/
```

#### Step 5：配置API密钥

编辑 `src/main/resources/application.yml`，填入你的API密钥：

```yaml
spring:
  ai:
    openai:
      api-key: your-dashscope-api-key        # 阿里云DashScope API Key
      base-url: https://dashscope.aliyuncs.com/compatible-mode
      chat:
        options:
          model: qwen3.5-plus
          temperature: 0.7

multimodal:
  openai:
    api-key: your-dashscope-api-key          # 同上
    base-url: https://dashscope.aliyuncs.com/compatible-mode
    model: qwen3.5-omni-flash-2026-03-15

embedding:
  siliconflow:
    api-key: your-siliconflow-api-key        # SiliconFlow API Key
    base-url: https://api.siliconflow.cn
    model: BAAI/bge-m3

reranker:
  siliconflow:
    api-key: your-siliconflow-api-key        # 同上
    base-url: https://api.siliconflow.cn
    model: BAAI/bge-reranker-v2-m3

serper:
  api-key: your-serper-api-key               # Serper API Key
  base-url: https://google.serper.dev

voice:
  dashscope:
    api-key: your-dashscope-api-key          # 同上
```

#### Step 6：构建项目

```bash
mvn clean package -DskipTests
```

构建产物位于 `target/ai-service-1.0.0.jar`

#### Step 7：启动服务

```bash
java -jar target/ai-service-1.0.0.jar
```

或指定配置文件：

```bash
java -jar target/ai-service-1.0.0.jar --spring.config.location=/path/to/application.yml
```

#### Step 8：验证启动

```bash
curl http://localhost:8081/api/ai/health
# 预期返回：AI Service is running
```

---

### 2.2 方式二：Docker部署

#### Step 1：配置application.yml

参照 2.1 Step 5 修改配置文件中的API密钥和中间件地址。

如果Redis和Neo4j也使用Docker部署，需将 `localhost` 替换为容器名或宿主机IP。

#### Step 2：构建Docker镜像

```bash
docker build -t ai-service:1.0.0 .
```

#### Step 3：启动依赖服务

```bash
# Redis Stack
docker run -d --name redis-stack \
  -p 6379:6379 \
  -e REDIS_ARGS="--requirepass 123456" \
  redis/redis-stack-server:latest

# Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/12345678 \
  neo4j:5
```

#### Step 4：启动AI Service

```bash
docker run -d --name ai-service \
  -p 8081:8081 \
  -v /tmp/audio:/tmp/audio \
  -v /tmp/408_codes:/tmp/408_codes \
  --link redis-stack:redis \
  --link neo4j:neo4j \
  ai-service:1.0.0
```

如果使用自定义配置：

```bash
docker run -d --name ai-service \
  -p 8081:8081 \
  -v /path/to/application.yml:/app/config/application.yml \
  -v /tmp/audio:/tmp/audio \
  -v /tmp/408_codes:/tmp/408_codes \
  ai-service:1.0.0 \
  --spring.config.location=file:/app/config/application.yml
```

---

### 2.3 方式三：Docker Compose（推荐）

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  redis:
    image: redis/redis-stack-server:latest
    ports:
      - "6379:6379"
    command: --requirepass 123456
    volumes:
      - redis-data:/data

  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/12345678
    volumes:
      - neo4j-data:/data

  ai-service:
    build: .
    ports:
      - "8081:8081"
    depends_on:
      - redis
      - neo4j
    environment:
      - SPRING_DATA_REDIS_HOST=redis
      - SPRING_DATA_REDIS_PASSWORD=123456
      - SPRING_NEO4J_URI=bolt://neo4j:7687
      - SPRING_NEO4J_AUTHENTICATION_USERNAME=neo4j
      - SPRING_NEO4J_AUTHENTICATION_PASSWORD=12345678
    volumes:
      - audio-data:/tmp/audio
      - codes-data:/tmp/408_codes

volumes:
  redis-data:
  neo4j-data:
  audio-data:
  codes-data:
```

启动：

```bash
docker-compose up -d
```

---

## 3. 配置详解

### 3.1 服务端口

```yaml
server:
  port: 8081
```

### 3.2 Spring AI - OpenAI兼容接口

```yaml
spring:
  ai:
    openai:
      api-key: sk-xxx                    # DashScope API Key
      base-url: https://dashscope.aliyuncs.com/compatible-mode
      chat:
        options:
          model: qwen3.5-plus            # 主对话模型
          temperature: 0.7               # 创造性参数（0-1）
      enabled: true
```

**可选模型：**
- `qwen3.5-plus`：旗舰大师、多智能体编排使用
- `qwen3.5-omni-flash-2026-03-15`：多模态模型（解题大王）

### 3.3 向量存储

```yaml
spring:
  ai:
    vectorstore:
      redis:
        initialize-schema: true          # 首次启动自动创建索引
        index-name: rag-knowledge-index  # 向量索引名称
        prefix: "rag:doc:"              # Key前缀
```

### 3.4 多模态配置

```yaml
multimodal:
  openai:
    api-key: sk-xxx
    base-url: https://dashscope.aliyuncs.com/compatible-mode
    model: qwen3.5-omni-flash-2026-03-15
    temperature: 0.7
```

### 3.5 向量嵌入

```yaml
embedding:
  siliconflow:
    api-key: sk-xxx
    base-url: https://api.siliconflow.cn
    model: BAAI/bge-m3                  # 多语言嵌入模型
```

### 3.6 重排序

```yaml
reranker:
  siliconflow:
    api-key: sk-xxx
    base-url: https://api.siliconflow.cn
    model: BAAI/bge-reranker-v2-m3      # 重排序模型
    top-n: 3                            # 返回Top-N结果
```

### 3.7 聊天记忆

```yaml
chat:
  memory:
    max-history: 10                     # 最大历史轮数
    ttl-minutes: 30                     # 记忆过期时间（分钟）
```

### 3.8 群聊配置

```yaml
group:
  chat:
    max-messages: 100                   # 群聊最大消息数
    ttl-hours: 24                       # 群聊记忆过期时间（小时）
```

### 3.9 联网搜索

```yaml
serper:
  api-key: xxx
  base-url: https://google.serper.dev
```

### 3.10 MCP文件系统工具配置

```yaml
mcp:
  server:
    filesystem:
      command: npx                          # MCP Server启动命令
      args:
        - "-y"
        - "@modelcontextprotocol/server-filesystem@0.6.2"
        - "/tmp/408_codes"                  # 文件系统工作目录
```

**前置条件：**
- 需要安装 Node.js 18+ 和 npx
- 首次启动时npx会自动下载 `@modelcontextprotocol/server-filesystem` 包
- 工作目录 `/tmp/408_codes` 需要手动创建：`mkdir -p /tmp/408_codes`

**说明：** 此工具为代码审查员（botId=10003）提供文件读取、目录列表、文件搜索能力。

### 3.11 语音配置

```yaml
voice:
  dashscope:
    api-key: sk-xxx
    asr-model: fun-asr-realtime-2026-02-28   # 语音识别模型
    tts-model: qwen3-tts-instruct-flash-realtime  # 语音合成模型
    tts-voice: Cherry                          # 语音角色
  storage:
    path: /tmp/audio                           # 音频存储路径
    url-prefix: http://localhost:8081/audio     # 音频访问URL前缀
```

**可选TTS语音角色：** Cherry, Serena, Ethan, Chelsie 等

### 3.12 Neo4j配置

```yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: 12345678
```

### 3.13 Redis配置

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      password: 123456
      database: 0
      timeout: 10000ms
      lettuce:
        pool:
          max-active: 8
          max-idle: 8
          min-idle: 0
          max-wait: -1ms
```

### 3.14 文件上传

```yaml
spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 50MB
      max-request-size: 50MB
      file-size-threshold: 2KB
```

### 3.15 结构化输出重试

```yaml
app:
  ai:
    structured-max-attempts: 2
    structured-include-last-error: true
    structured-retry-use-repair-prompt: true
    structured-retry-append-strict-json-instruction: true
    structured-error-message-max-length: 200
    structured-metrics-enabled: true
```

### 3.16 日志级别

```yaml
logging:
  level:
    com.chat.ai: DEBUG
    org.springframework.ai: DEBUG
```

生产环境建议改为 `INFO` 或 `WARN`。

### 3.17 RAG文档处理配置

```yaml
rag:
  chunk-size: 800                        # 文档分块大小（字符数）
  chunk-overlap: 200                     # 分块重叠区域
  top-k: 5                               # 向量检索返回Top-K
  bm25-top-k: 10                         # BM25检索返回Top-K
```

### 3.18 知识图谱初始数据

系统首次启动时，需要向Neo4j导入408考研知识图谱初始数据。知识图谱包含：

- Level 0：408计算机学科专业基础
- Level 1：四大科目（数据结构、计算机组成原理、操作系统、计算机网络）
- Level 2-5：章节和考点层级

**导入方式：** 通过 `/api/graph/extract` 接口逐步构建，或通过Neo4j Browser执行Cypher脚本批量导入。

### 3.19 考情大屏静态资源

系统内置考情大屏HTML页面，访问地址：

```
http://localhost:8081/dashboard.html?userId=1
```

该页面使用ECharts可视化库，展示雷达图和活跃度折线图。

---

## 4. 环境变量覆盖

所有配置项均可通过环境变量覆盖，格式为 `SPRING_` 前缀 + 下划线分隔的大写路径：

```bash
# 示例
export SPRING_AI_OPENAI_API_KEY=sk-xxx
export SPRING_DATA_REDIS_HOST=redis
export SPRING_DATA_REDIS_PASSWORD=123456
export SPRING_NEO4J_URI=bolt://neo4j:7687
export SPRING_NEO4J_AUTHENTICATION_USERNAME=neo4j
export SPRING_NEO4J_AUTHENTICATION_PASSWORD=12345678
```

---

## 5. 生产环境部署建议

### 5.1 JVM参数

```bash
java -Xms512m -Xmx2g -jar ai-service-1.0.0.jar
```

### 5.2 安全配置

1. **修改默认密码**：Redis、Neo4j的默认密码必须修改
2. **API密钥保护**：不要将API密钥提交到版本控制，使用环境变量注入
3. **CORS配置**：生产环境应限制允许的域名
4. **限流配置**：根据实际负载调整限流参数
5. **MCP工作目录**：限制 `/tmp/408_codes` 目录的权限，仅允许应用用户读写
6. **C++沙盒安全**：代码沙盒在 `/tmp` 目录执行，建议使用容器隔离或沙盒工具

### 5.3 音频存储

- 默认存储路径 `/tmp/audio`，Docker部署时需挂载卷
- 生产环境建议使用对象存储（如OSS）替代本地文件存储
- 需修改 `voice.storage.path` 和 `voice.storage.url-prefix` 配置

### 5.4 Redis高可用

- 生产环境推荐使用 Redis Sentinel 或 Redis Cluster
- 开启AOF持久化以防止数据丢失
- Redis Stack需确保RedisSearch模块已加载

### 5.5 Neo4j配置

- 生产环境建议调大 `dbms.memory.heap.max_size`
- 开启认证并设置强密码
- 定期备份图数据库

### 5.6 Node.js与MCP

- 生产环境建议预安装MCP Server包，避免运行时下载：`npm install -g @modelcontextprotocol/server-filesystem@0.6.2`
- Docker镜像中需包含Node.js环境（Dockerfile已配置）
- 首次启动可能较慢（npx下载MCP包），后续启动会使用缓存

---

## 6. 常见问题

### Q1：启动报错 "Unable to connect to Redis"

**排查步骤：**
1. 确认Redis服务已启动：`redis-cli -a 123456 ping`
2. 检查 `application.yml` 中Redis地址和密码是否正确
3. 如果Redis在Docker中，确认网络连通性

### Q2：启动报错 "Unable to connect to Neo4j"

**排查步骤：**
1. 确认Neo4j服务已启动：`curl http://localhost:7474`
2. 检查 `application.yml` 中Neo4j URI和认证信息
3. 确认7687端口（bolt协议）已开放

### Q3：RAG上传文档后向量索引创建失败

**排查步骤：**
1. 确认使用的是 Redis Stack（包含RedisSearch模块），而非普通Redis
2. 检查 `spring.ai.vectorstore.redis.initialize-schema` 是否为 `true`
3. 首次启动时自动创建索引，后续可设为 `false`

### Q4：语音功能不可用

**排查步骤：**
1. 确认DashScope API Key有效且有语音服务权限
2. 检查 `/tmp/audio` 目录是否有写入权限
3. 确认 `voice.storage.url-prefix` 配置正确，客户端能访问该URL

### Q5：C++代码沙盒无法编译

**排查步骤：**
1. 确认系统已安装 `g++`：`g++ --version`
2. 检查 `/tmp` 目录是否有写入权限
3. 编译超时默认3秒，复杂代码可能需要调整 `TIMEOUT_SECONDS`

### Q6：OCR功能不可用

**排查步骤：**
1. 确认已安装 `pdftoppm`：`pdftoppm -v`
2. 确认已安装 `tesseract`：`tesseract --version`
3. 确认中文语言包已安装：`tesseract --list-langs` 应包含 `chi_sim`

### Q7：联网搜索返回错误

**排查步骤：**
1. 确认Serper API Key有效：`curl -H "X-API-KEY: your-key" https://google.serper.dev/search -d '{"q":"test"}'`
2. 检查网络是否能访问 `google.serper.dev`

### Q8：WebSocket实时语音连接失败

**排查步骤：**
1. 确认WebSocket端点 `/ws/realtime-voice` 可访问
2. 检查Nginx/反向代理是否正确配置WebSocket升级
3. 确认DashScope WebSocket服务可用

### Q9：MCP文件系统工具启动失败

**排查步骤：**
1. 确认已安装 Node.js：`node --version`（需18+）
2. 确认npx可用：`npx --version`
3. 手动测试MCP Server：`npx -y @modelcontextprotocol/server-filesystem@0.6.2 /tmp/408_codes`
4. 确认工作目录存在：`mkdir -p /tmp/408_codes`
5. 如果网络受限，可预先安装：`npm install -g @modelcontextprotocol/server-filesystem@0.6.2`

### Q10：知识图谱接口返回空数据

**排查步骤：**
1. 确认Neo4j中已导入知识图谱初始数据
2. 检查Neo4j Browser（http://localhost:7474）中是否有 `Concept` 节点
3. 确认用户节点已创建：`MATCH (u:User {userId: 1}) RETURN u`
4. 首次使用需通过聊天或 `/api/graph/extract` 接口构建知识数据

### Q11：流式聊天返回乱码或格式异常

**排查步骤：**
1. 确认客户端使用 SSE 或流式读取方式接收
2. 流式响应首行包含 `[SESSION:xxx]`，需正确解析
3. 检查字符编码是否为 UTF-8

### Q12：群聊AI不回复

**排查步骤：**
1. 确认请求中 `aiBotIds` 参数非空
2. 检查Redis Pub/Sub频道 `9997` 是否正常
3. 确认C++网关（ChatServer）已订阅 `9997` 频道
4. 检查群聊记忆是否已满（默认100条）

### Q13：异步任务（摘要/周报）不执行

**排查步骤：**
1. 确认Redis连接正常，`ai:task:queue` 队列存在
2. 检查AiTaskConsumer线程是否正常运行（查看日志）
3. 周报定时任务需确认Cron表达式和时区配置
4. 确认Neo4j中存在 `UserNode` 节点

---

## 7. 依赖版本汇总

| 依赖 | 版本 | 说明 |
|------|------|------|
| Spring Boot | 3.2.0 | 基础框架 |
| Spring AI | 1.0.0-M3 | AI集成框架 |
| spring-ai-mcp | 0.2.0 | Model Context Protocol |
| DashScope SDK | 2.22.7 | 阿里云AI SDK |
| Redisson | 3.24.3 | 分布式锁、限流 |
| Jedis | 5.1.0 | Redis客户端 |
| PDFBox | 3.0.1 | PDF处理 |
| Lombok | - | 代码简化 |
| Java | 17 | 运行时环境 |

---

## 8. 快速验证清单

启动后依次验证以下功能：

```bash
# 1. 健康检查
curl http://localhost:8081/api/ai/health

# 2. 基础聊天
curl -X POST http://localhost:8081/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "botId":10000, "message":"你好"}'

# 3. 语音服务健康检查
curl http://localhost:8081/api/voice/health

# 4. 农场服务健康检查
curl http://localhost:8081/api/farm/health

# 5. RAG文档上传
curl -X POST http://localhost:8081/api/rag/upload \
  -F "file=@test.txt"

# 6. 知识图谱（需先有数据）
curl http://localhost:8081/api/graph/user/1/tree

# 7. 考情大屏
curl http://localhost:8081/api/analysis/dashboard/1

# 8. 考情大屏页面
curl http://localhost:8081/dashboard.html?userId=1

# 9. 多智能体工作流
curl -X POST http://localhost:8081/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "message":"请解释一下TCP三次握手"}'

# 10. MCP文件系统工具验证（代码审查员）
curl -X POST http://localhost:8081/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "botId":10003, "message":"帮我看看这段代码有没有问题"}'

# 11. 流式聊天
curl -N "http://localhost:8081/api/ai/stream-chat?message=你好&sessionId=test_session"

# 12. Redis连接验证
redis-cli -a 123456 ping
```

---

## 9. C++服务器端安装配置

### 9.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| GCC | 9+ | C++编译器 |
| CMake | 3.10+ | 构建工具 |
| muduo | - | 陈硕网络库（需从源码编译） |
| MySQL | 8.0+ | 用户数据存储 |
| Redis | 7.0+ | 消息转发、跨服务器通信 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | - | MySQL C客户端 |
| nlohmann/json | 3.x | JSON解析库（header-only） |

### 9.2 安装muduo网络库

muduo需要从源码编译安装：

```bash
# 安装依赖
sudo apt-get install -y cmake g++ libboost-dev libcurl4-openssl-dev

# 克隆muduo
git clone https://github.com/chenshuo/muduo.git
cd muduo

# 编译（生成在build目录）
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# 安装到指定目录（可选）
# 默认安装到 /usr/local
sudo make install

# 或安装到自定义目录
# cmake .. -DCMAKE_INSTALL_PREFIX=/home/xmy/muduo
# make install
```

### 9.3 安装MySQL和Redis客户端库

**Ubuntu/Debian：**

```bash
sudo apt-get install -y libmysqlclient-dev libhiredis-dev
```

**CentOS/RHEL：**

```bash
sudo yum install -y mysql-devel hiredis-devel
```

### 9.4 数据库初始化

创建MySQL数据库和表：

```sql
CREATE DATABASE chat;

USE chat;

-- 用户表
CREATE TABLE user (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(50) NOT NULL,
    state ENUM('online', 'offline') DEFAULT 'offline',
    avatar MEDIUMBLOB
);

-- 好友关系表
CREATE TABLE friend (
    userid INT NOT NULL,
    friendid INT NOT NULL,
    PRIMARY KEY(userid, friendid)
);

-- 群组表
CREATE TABLE allgroup (
    id INT PRIMARY KEY AUTO_INCREMENT,
    groupname VARCHAR(50) NOT NULL UNIQUE,
    groupdesc VARCHAR(200) DEFAULT ''
);

-- 群组成员表
CREATE TABLE groupuser (
    groupid INT NOT NULL,
    userid INT NOT NULL,
    grouprole ENUM('creator', 'normal') DEFAULT 'normal',
    PRIMARY KEY(groupid, userid)
);

-- 离线消息表
CREATE TABLE offlinemessage (
    userid INT NOT NULL,
    message VARCHAR(500) NOT NULL
);

-- 表情包表
CREATE TABLE emoji (
    id INT PRIMARY KEY AUTO_INCREMENT,
    userid INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    imagedata MEDIUMTEXT NOT NULL,
    createtime DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 农场用户表
CREATE TABLE farm_user (
    userid INT PRIMARY KEY,
    coins INT DEFAULT 0,
    exp INT DEFAULT 0
);

-- 农场地块表
CREATE TABLE farm_plot (
    ownerid INT NOT NULL,
    plotindex INT NOT NULL,
    state INT DEFAULT 0,
    question VARCHAR(500),
    subject VARCHAR(50),
    answererid INT,
    answer VARCHAR(1000),
    score INT,
    feedback VARCHAR(500),
    PRIMARY KEY(ownerid, plotindex)
);
```

### 9.5 修改CMakeLists.txt配置

编辑 `/home/xmy/code/src/server/CMakeLists.txt`，修改muduo路径：

```cmake
# 设置muduo路径
set(MUDUO_ROOT_DIR "/home/xmy/muduo")  # 修改为你的muduo安装路径
```

### 9.6 编译服务器

```bash
cd /home/xmy/code
mkdir -p build && cd build
cmake ..
make ChatServer -j$(nproc)
```

编译产物位于 `bin/ChatServer`

### 9.7 启动服务器

```bash
# 前台运行
./bin/ChatServer

# 后台运行
nohup ./bin/ChatServer > chatserver.log 2>&1 &
```

服务器默认监听端口 **8000**。

### 9.8 配置说明

服务器配置通过代码硬编码，主要配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 服务器端口 | 8000 | TCP监听端口 |
| 线程数 | 4 | muduo IO线程数 |
| Redis主机 | 127.0.0.1 | Redis服务器地址 |
| Redis端口 | 6379 | Redis端口 |
| Redis密码 | 123456 | Redis密码（需修改代码） |
| MySQL主机 | 127.0.0.1 | MySQL服务器地址 |
| MySQL端口 | 3306 | MySQL端口 |
| MySQL用户 | root | MySQL用户名 |
| MySQL密码 | 123456 | MySQL密码（需修改代码） |
| MySQL数据库 | chat | 数据库名 |

**修改配置位置：**
- Redis配置：`src/server/redis/redis.cpp`
- MySQL配置：`src/server/db/db.cpp`

---

## 10. C++客户端安装配置

### 10.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Qt | 5.12+ | Qt框架 |
| GCC | 9+ | C++编译器 |
| CMake | 3.10+ | 构建工具 |
| muduo | - | 网络库（与服务器共用） |
| mysqlclient | - | MySQL客户端库 |
| hiredis | - | Redis客户端库 |

**Qt组件要求：**
- Qt5::Widgets
- Qt5::Network
- Qt5::Concurrent
- Qt5::Svg
- Qt5::WebEngineWidgets
- Qt5::Multimedia
- Qt5::WebSockets

### 10.2 安装Qt 5

**Ubuntu/Debian：**

```bash
sudo apt-get install -y qt5-default qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools \
    libqt5svg5-dev libqt5webengine5-dev libqt5multimedia5-dev libqt5websockets5-dev \
    qtwebengine5-dev qtmultimedia5-dev
```

**CentOS/RHEL：**

```bash
sudo yum install -y qt5-qtbase-devel qt5-qtsvg-devel qt5-qtwebengine-devel \
    qt5-qtmultimedia-devel qt5-qtwebsockets-devel
```

**Windows：**

1. 下载Qt安装器：https://www.qt.io/download
2. 安装Qt 5.15+，勾选以下组件：
   - MSVC 2019 64-bit
   - Qt WebEngine
   - Qt Multimedia
   - Qt WebSockets

### 10.3 编译客户端

```bash
cd /home/xmy/code
mkdir -p build && cd build
cmake ..
make QtChat -j$(nproc)
```

编译产物位于 `bin/QtChat`

### 10.4 运行客户端

```bash
./bin/QtChat
```

### 10.5 客户端配置

客户端通过代码硬编码连接服务器，修改位置：

**服务器地址配置** - `src/chatclient.cpp`：

```cpp
// 默认连接本地服务器
bool ChatClient::connectToServer(const QString &host, quint16 port) {
    // ...
}

// 或在main.cpp中指定
client->connectToServer("your-server-ip", 8000);
```

### 10.6 Live2D资源

客户端需要Live2D资源文件：

```
live2d/
├── core/
│   └── live2dcubismcore.js
└── hiyori/
    ├── hiyori_pro_t11.model3.json
    ├── hiyori_pro_t11.moc3
    ├── hiyori_pro_t11.physics3.json
    ├── hiyori_pro_t11.pose3.json
    ├── hiyori_pro_t11.2048/
    │   ├── texture_00.png
    │   └── texture_01.png
    └── motion/
        └── *.motion3.json
```

资源会在编译时自动复制到build目录。

---

## 11. 完整部署架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              部署架构图                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                  │
│   │ QtChat      │     │ QtChat      │     │ Web Client  │                  │
│   │ (Linux)     │     │ (Windows)   │     │ (Browser)   │                  │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                  │
│          │                   │                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              │ TCP:8000                                     │
│                              ▼                                              │
│                    ┌─────────────────┐                                      │
│                    │  ChatServer     │                                      │
│                    │  (C++ muduo)    │                                      │
│                    └────────┬────────┘                                      │
│                             │                                               │
│          ┌──────────────────┼──────────────────┐                            │
│          │                  │                  │                            │
│          ▼                  ▼                  ▼                            │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│   │   MySQL     │    │   Redis     │    │  AI Service │                     │
│   │   :3306     │    │   :6379     │    │  (Java)     │                     │
│   └─────────────┘    └──────┬──────┘    │   :8081     │                     │
│                             │            └──────┬──────┘                     │
│                             │                   │                            │
│                             │    ┌──────────────┘                            │
│                             │    │                                           │
│                             ▼    ▼                                           │
│                      ┌─────────────┐    ┌─────────────┐                      │
│                      │   Neo4j     │    │  RedisStack │                      │
│                      │   :7687     │    │  (Vector)   │                      │
│                      └─────────────┘    └─────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. 常见问题（C++端）

### Q14：ChatServer编译报错 "muduo not found"

**排查步骤：**
1. 确认muduo已编译：检查 `/home/xmy/muduo/build/lib/` 是否存在 `.a` 文件
2. 修改 `src/server/CMakeLists.txt` 中的 `MUDUO_ROOT_DIR` 路径
3. 确认 `link_directories` 指向正确的lib目录

### Q15：QtChat编译报错 "Qt5 not found"

**排查步骤：**
1. 确认Qt5已安装：`qmake --version`
2. 安装缺失组件：`sudo apt-get install qt5-default qtbase5-dev`
3. 设置Qt路径：`export Qt5_DIR=/usr/lib/x86_64-linux-gnu/cmake/Qt5`

### Q16：客户端连接服务器失败

**排查步骤：**
1. 确认服务器已启动：`netstat -tlnp | grep 8000`
2. 检查防火墙：`sudo ufw allow 8000`
3. 确认客户端配置的服务器地址正确

### Q17：Live2D不显示

**排查步骤：**
1. 确认Live2D资源已复制到build目录
2. 检查 `live2d/core/live2dcubismcore.js` 是否存在
3. 查看Qt控制台是否有WebEngine错误

### Q18：MySQL连接失败

**排查步骤：**
1. 确认MySQL服务已启动：`sudo systemctl status mysql`
2. 检查用户名密码是否正确（修改 `src/server/db/db.cpp`）
3. 确认数据库 `chat` 已创建

### Q19：Redis连接失败

**排查步骤：**
1. 确认Redis服务已启动：`redis-cli ping`
2. 检查密码是否正确（修改 `src/server/redis/redis.cpp`）
3. 确认hiredis库已安装

---

## 13. 依赖版本汇总（完整）

### Java AI服务

| 依赖 | 版本 | 说明 |
|------|------|------|
| Spring Boot | 3.2.0 | 基础框架 |
| Spring AI | 1.0.0-M3 | AI集成框架 |
| spring-ai-mcp | 0.2.0 | Model Context Protocol |
| DashScope SDK | 2.22.7 | 阿里云AI SDK |
| Redisson | 3.24.3 | 分布式锁、限流 |
| Jedis | 5.1.0 | Redis客户端 |
| PDFBox | 3.0.1 | PDF处理 |
| Java | 17 | 运行时环境 |

### C++服务器端

| 依赖 | 版本 | 说明 |
|------|------|------|
| muduo | master | 陈硕网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |
| nlohmann/json | 3.x | JSON解析 |

### C++客户端

| 依赖 | 版本 | 说明 |
|------|------|------|
| Qt | 5.12+ | GUI框架 |
| muduo | master | 网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |

---

## 14. 快速验证清单（完整）

### Java AI服务

```bash
# 健康检查
curl http://localhost:8081/api/ai/health

# 基础聊天
curl -X POST http://localhost:8081/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "botId":10000, "message":"你好"}'
```

### C++服务器

```bash
# 检查服务状态
netstat -tlnp | grep 8000

# 查看日志
tail -f chatserver.log
```

### C++客户端

```bash
# 启动客户端
./bin/QtChat

# 或命令行版本
./bin/ChatClient
```

### 数据库验证

```bash
# MySQL
mysql -u root -p -e "USE chat; SELECT COUNT(*) FROM user;"

# Redis
redis-cli -a 123456 ping

# Neo4j
curl http://localhost:7474
```

---

## 15. Eruitah智能编程沙盒安装配置

### 15.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 运行时环境 |
| pip | 21+ | 包管理器 |
| ripgrep (rg) | - | 可选，代码搜索加速（推荐安装） |

### 15.2 安装Python依赖

```bash
cd /home/xmy/code/eruitah-sandbox

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**requirements.txt内容：**

```
fastapi>=0.104.0
uvicorn>=0.24.0
sse-starlette>=1.8.0
pydantic>=2.5.0
anthropic>=0.39.0
openai>=1.6.0
tiktoken>=0.7.0
python-dotenv>=1.0.0
websockets>=12.0
```

### 15.3 环境变量配置

在项目根目录 `/home/xmy/code/.env` 文件中配置：

```bash
# Eruitah 沙盒配置
ERUITAH_SANDBOX_DIR=/tmp/eruitah-sandbox
ERUITAH_API_PROVIDER=openai
ERUITAH_MODEL_OPENAI=gpt-4o
ERUITAH_MODEL_ANTHROPIC=claude-sonnet-4-20250514

# OpenAI 兼容接口（支持通义千问等）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode

# Anthropic Claude（可选）
ANTHROPIC_API_KEY=sk-xxx
```

### 15.4 启动服务

**开发模式：**

```bash
cd /home/xmy/code/eruitah-sandbox
source venv/bin/activate
python main.py
```

**生产模式：**

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4
```

服务默认监听端口 **8001**。

### 15.5 安装ripgrep（可选但推荐）

ripgrep比grep快10-100倍，且默认尊重.gitignore：

**Ubuntu/Debian：**

```bash
sudo apt-get install -y ripgrep
```

**CentOS/RHEL：**

```bash
sudo yum install -y ripgrep
```

**macOS：**

```bash
brew install ripgrep
```

### 15.6 Docker部署

**构建镜像：**

```bash
cd /home/xmy/code/eruitah-sandbox
docker build -t eruitah-sandbox:1.0.0 .
```

**运行容器：**

```bash
docker run -d --name eruitah-sandbox \
  -p 8001:8001 \
  -v /tmp/eruitah-sandbox:/tmp/eruitah-sandbox \
  -e OPENAI_API_KEY=sk-xxx \
  -e OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode \
  eruitah-sandbox:1.0.0
```

### 15.7 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ERUITAH_SANDBOX_DIR` | `/tmp/eruitah-sandbox` | 沙盒工作目录 |
| `ERUITAH_API_PROVIDER` | `openai` | API提供商（openai/anthropic） |
| `ERUITAH_MODEL_OPENAI` | `gpt-4o` | OpenAI模型名称 |
| `ERUITAH_MODEL_ANTHROPIC` | `claude-sonnet-4-20250514` | Anthropic模型名称 |
| `OPENAI_API_KEY` | - | OpenAI API密钥 |
| `OPENAI_BASE_URL` | - | OpenAI兼容API地址 |
| `ANTHROPIC_API_KEY` | - | Anthropic API密钥 |

### 15.8 验证安装

```bash
# 健康检查
curl http://localhost:8001/api/v1/health

# 预期返回
# {"status":"ok","sandbox_dir":"/tmp/eruitah-sandbox","api_provider":"openai"}

# WebSocket测试（使用wscat）
wscat -c ws://localhost:8001/ws/coding
# 发送: {"task":"列出当前目录文件"}
```

---

## 16. 完整部署架构（更新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              部署架构图                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                  │
│   │ QtChat      │     │ QtChat      │     │ Web Client  │                  │
│   │ (Linux)     │     │ (Windows)   │     │ (Browser)   │                  │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                  │
│          │                   │                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              │ TCP:8000                                     │
│                              ▼                                              │
│                    ┌─────────────────┐                                      │
│                    │  ChatServer     │                                      │
│                    │  (C++ muduo)    │                                      │
│                    └────────┬────────┘                                      │
│                             │                                               │
│          ┌──────────────────┼──────────────────┬──────────────┐            │
│          │                  │                  │              │            │
│          ▼                  ▼                  ▼              ▼            │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ ┌─────────────┐   │
│   │   MySQL     │    │   Redis     │    │  AI Service │ │  Eruitah    │   │
│   │   :3306     │    │   :6379     │    │  (Java)     │ │  Sandbox    │   │
│   └─────────────┘    └──────┬──────┘    │   :8081     │ │  (Python)   │   │
│                             │            └──────┬──────┘ │   :8001     │   │
│                             │                   │        └──────┬──────┘   │
│                             │    ┌──────────────┘               │          │
│                             │    │                              │          │
│                             ▼    ▼                              ▼          │
│                      ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│                      │   Neo4j     │    │  RedisStack │    │  LLM API    │ │
│                      │   :7687     │    │  (Vector)   │    │  (Claude)   │ │
│                      └─────────────┘    └─────────────┘    │  (GPT-4o)   │ │
│                                                             └─────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 17. 常见问题（Eruitah沙盒）

### Q20：Python依赖安装失败

**排查步骤：**
1. 确认Python版本：`python3 --version`（需3.10+）
2. 升级pip：`pip install --upgrade pip`
3. 使用虚拟环境隔离依赖

### Q21：OpenAI API调用失败

**排查步骤：**
1. 确认API Key有效：`curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models`
2. 检查base_url是否正确（通义千问需使用兼容模式地址）
3. 确认base_url以`/v1`结尾

### Q22：WebSocket连接失败

**排查步骤：**
1. 确认服务已启动：`curl http://localhost:8001/api/v1/health`
2. 检查防火墙：`sudo ufw allow 8001`
3. 使用wscat测试：`wscat -c ws://localhost:8001/ws/coding`

### Q23：bash命令被安全拦截

**排查步骤：**
1. 检查命令是否匹配危险模式（如`rm -rf /`）
2. 确认命令中的路径在工作目录范围内
3. 查看`bash_executor.py`中的`BLOCKED_PATTERNS`和`WARNED_PATTERNS`

### Q24：文件编辑失败"未找到匹配"

**排查步骤：**
1. 确认`search_text`与文件内容完全一致（包括缩进）
2. 检查引号类型（弯引号vs直引号）
3. 使用`file_read`工具先查看文件内容

### Q25：Agent陷入死循环

**排查步骤：**
1. 检查`max_turns`参数（默认15轮）
2. 查看日志中的工具调用序列
3. 确认自愈机制是否正常工作

---

## 18. 依赖版本汇总（完整更新）

### Java AI服务

| 依赖 | 版本 | 说明 |
|------|------|------|
| Spring Boot | 3.2.0 | 基础框架 |
| Spring AI | 1.0.0-M3 | AI集成框架 |
| spring-ai-mcp | 0.2.0 | Model Context Protocol |
| DashScope SDK | 2.22.7 | 阿里云AI SDK |
| Redisson | 3.24.3 | 分布式锁、限流 |
| Jedis | 5.1.0 | Redis客户端 |
| PDFBox | 3.0.1 | PDF处理 |
| Java | 17 | 运行时环境 |

### C++服务器端

| 依赖 | 版本 | 说明 |
|------|------|------|
| muduo | master | 陈硕网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |
| nlohmann/json | 3.x | JSON解析 |

### C++客户端

| 依赖 | 版本 | 说明 |
|------|------|------|
| Qt | 5.12+ | GUI框架 |
| muduo | master | 网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |

### Eruitah智能编程沙盒

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 运行时环境 |
| FastAPI | 0.104+ | Web框架 |
| uvicorn | 0.24+ | ASGI服务器 |
| openai | 1.6+ | OpenAI SDK |
| anthropic | 0.39+ | Anthropic SDK |
| pydantic | 2.5+ | 数据验证 |
| websockets | 12.0+ | WebSocket支持 |
| ripgrep | - | 可选，代码搜索加速 |

---

## 19. 快速验证清单（完整更新）

### Java AI服务

```bash
curl http://localhost:8081/api/ai/health
```

### C++服务器

```bash
netstat -tlnp | grep 8000
```

### C++客户端

```bash
./bin/QtChat
```

### Eruitah智能编程沙盒

```bash
# 健康检查
curl http://localhost:8001/api/v1/health

# WebSocket测试
wscat -c ws://localhost:8001/ws/coding
# 发送: {"task":"列出当前目录文件"}

# REST API测试
curl -X POST http://localhost:8001/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"prompt":"写一个Hello World程序","max_turns":5}'
```

### 数据库验证

```bash
# MySQL
mysql -u root -p -e "USE chat; SELECT COUNT(*) FROM user;"

# Redis
redis-cli -a 123456 ping

# Neo4j
curl http://localhost:7474
```
