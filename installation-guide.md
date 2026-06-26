# 智能聊天应用系统 安装配置指南

## 项目概述

本项目是一个多语言微服务智能聊天应用系统，包含以下核心组件：

| 组件 | 技术栈 | 端口 | 说明 |
|------|--------|------|------|
| ChatServer | C++ / muduo | 6000 (TCP), 8888 (RPC) | 即时通讯网关，处理客户端连接、消息路由 |
| AI Service | Java / Spring Boot | 8081 (HTTP), 9999 (RPC) | AI 后端服务，LLM 对话、RAG、知识图谱、语音 |
| Butcanthic | Python / FastAPI + LangGraph | 8002 (HTTP) | 文档智能处理服务，Word/Excel/PPT 自动填充、PPT生成、知识库RAG |
| Eruitah Sandbox | Python / FastAPI | 8001 (HTTP/WS), 5900 (VNC) | 智能编程沙盒，代码执行、浏览器自动化 |
| Coding Agent UI | Vue 3 / Vite | - (构建产物) | Web IDE 前端，代码编辑器 + 终端 |
| Butcanthic Frontend | React / Vite | 5174 (开发) | 文档智能前端，PPT查看器、知识图谱可视化 |
| Protobuf RPC Bridge | Protobuf / CMake | - | 跨语言 RPC 通信桥接（C++ ↔ Java ↔ Python） |
| Nginx | nginx:1.25-alpine | 80 (HTTP), 8000 (TCP) | 反向代理，统一入口 |
| MySQL | mysql:8.0 | 3306 | 用户数据存储 |
| Redis | redis/redis-stack | 6379 | 向量存储、消息转发、限流 |
| Neo4j | neo4j:latest | 7474/7687 | 知识图谱存储（AI Service 认知图谱 + Butcanthic GraphRAG） |
| RabbitMQ | rabbitmq:3-management | 5672 (AMQP), 15672 (管理) | AIOS 全局事件总线（桌宠通知、Agent 状态、跨服务事件） |
| ChromaDB | 嵌入式（butcanthic内置） | - | Butcanthic 向量数据库（用户级 Collection 隔离） |
| MQTT Broker | rabbitmqctl（RabbitMQ MQTT 插件） | 1883 | C++ 桌面端订阅 AIOS 事件（RabbitMQ MQTT 插件启用） |

---

## 1. 环境要求

### 1.1 基础环境

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| JDK | 17 | 推荐 Eclipse Temurin 17 |
| Maven | 3.9+ | 项目构建工具 |
| Python | 3.11+ | Butcanthic 文档智能服务运行环境（3.11+），Sandbox 运行环境（3.10+） |
| pip | 21+ | Python 包管理器 |
| Node.js | 18+ | MCP 文件系统工具、Coding Agent UI 构建环境 |
| npm/npx | 9+ | MCP Server 启动工具、前端构建 |
| GCC | 9+ | C++ 编译器（ChatServer + RPC Bridge） |
| CMake | 3.10+ | C++ 构建工具 |
| protoc | 3.x | Protobuf 编译器（RPC Bridge 需要） |
| Qt | 5.12+ | 桌面客户端 GUI 框架 |
| MySQL | 8.0+ | 用户数据存储 |
| Redis Stack | 7.0+ | 向量存储、聊天记忆、限流、Pub/Sub（需含 RedisSearch 模块） |
| Neo4j | 5.0+ | 知识图谱存储 |
| muduo | - | 陈硕网络库（需从源码编译） |
| hiredis | 1.0+ | Redis C 客户端 |
| mysqlclient | - | MySQL C 客户端 |
| nlohmann/json | 3.x | JSON 解析库（header-only） |
| g++ | - | C++ 编译器（代码沙盒功能需要） |
| pdftoppm | - | PDF 转图片工具（OCR 功能需要） |
| tesseract | - | OCR 引擎（扫描版 PDF 识别需要） |
| ripgrep (rg) | - | 可选，代码搜索加速（推荐安装，Sandbox 语义检索使用） |
| RabbitMQ | 3.10+ | AIOS 全局事件总线（AI Service / Butcanthic / Sandbox 共用） |
| mosquitto | 2.0+ | C++ 客户端 MQTT 库（桌宠订阅 AIOS 事件） |
| qt-material-widgets | - | Qt5 Material Design 控件库（源码内置 `qt-material-widgets/`） |
| tree-sitter | 0.20+ | Sandbox 多语言 AST 解析（Python/Java/C++ 语法包） |
| DuckDB | - | Butcanthic Excel 数据对话引擎（pip 安装） |
| mammoth (Node.js) | - | Butcanthic DOCX→HTML 转换器（Node.js 包） |
| pika | 1.3+ | Python RabbitMQ 客户端（Butcanthic / Sandbox 事件总线） |

### 1.2 外部服务API

| 服务 | 用途 | 获取地址 |
|------|------|----------|
| 阿里云DashScope | LLM对话、ASR语音识别、TTS语音合成 | https://dashscope.console.aliyun.com/ |
| SiliconFlow | 文本嵌入（BGE-M3）、重排序（BGE-Reranker） | https://siliconflow.cn/ |
| Serper | 联网搜索 | https://serper.dev/ |
| 火山引擎豆包 | Butcanthic 可选 LLM 提供商 | https://www.volcengine.com/ |

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
  aliyun:
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

项目根目录已包含 `docker-compose.yml`，包含 7 个服务（Butcanthic 需单独部署或手动添加到 Compose）：

| 服务 | 镜像/构建 | 端口映射 | 说明 |
|------|-----------|----------|------|
| mysql | mysql:8.0 | 3306:3306 | 用户数据存储，含健康检查 |
| redis | redis/redis-stack:latest | 6379:6379 | 向量存储 + 消息转发，含健康检查 |
| neo4j | neo4j:latest | 7474:7474, 7687:7687 | 知识图谱，含 APOC 插件 |
| chatserver | Dockerfile.chatserver | 6000:6000, 8888:8888 | C++ 即时通讯网关 |
| sandbox | eruitah-sandbox/Dockerfile | 8001:8001, 5900:5900 | Python 编程沙盒 |
| ai-service | ai-service/Dockerfile | 8081:8081, 9999:9999 | Java AI 后端 |
| nginx | nginx:1.25-alpine | 80:80, 8000:8000 | 反向代理统一入口 |

> **注意**：Butcanthic 文档智能服务当前未包含在 docker-compose.yml 中，需单独启动（`python main.py`）或手动添加服务定义。

**docker-compose.yml 内容：**

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: chat-mysql
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-xieming562}
      MYSQL_DATABASE: chat
    ports:
      - "3306:3306"
    volumes:
      - mysql-data:/var/lib/mysql
      - ./docker/mysql/init.sql:/docker-entrypoint-initdb.d/init.sql
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_general_ci
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-xieming562}"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks:
      - chat-net

  redis:
    image: redis/redis-stack:latest
    container_name: chat-redis
    restart: always
    ports:
      - "6379:6379"
    environment:
      REDIS_ARGS: --requirepass ${REDIS_PASSWORD:-123456}
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-123456}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - chat-net

  neo4j:
    image: neo4j:latest
    container_name: chat-neo4j
    restart: always
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-12345678}
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
    networks:
      - chat-net

  chatserver:
    build:
      context: .
      dockerfile: Dockerfile.chatserver
    container_name: chat-server
    restart: always
    ports:
      - "6000:6000"
      - "8888:8888"
    environment:
      MYSQL_HOST: mysql
      MYSQL_USER: root
      MYSQL_PASSWORD: ${MYSQL_ROOT_PASSWORD:-xieming562}
      MYSQL_DBNAME: chat
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: ${REDIS_PASSWORD:-123456}
      AI_SERVICE_URL: http://ai-service:8081/api/ai/chat
      AI_SERVICE_BASE_URL: http://ai-service:8081
      JAVA_RPC_HOST: ai-service
      JAVA_RPC_PORT: 9999
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - chat-net

  sandbox:
    build:
      context: ./eruitah-sandbox
      dockerfile: Dockerfile
    container_name: chat-sandbox
    restart: always
    ports:
      - "8001:8001"
      - "5900:5900"
    environment:
      ERUITAH_SANDBOX_DIR: /tmp/eruitah-sandbox
      ERUITAH_API_PROVIDER: ${ERUITAH_API_PROVIDER:-openai}
      ERUITAH_MODEL_OPENAI: ${ERUITAH_MODEL_OPENAI:-mimo-v2.5}
      ERUITAH_MODEL_ANTHROPIC: ${ERUITAH_MODEL_ANTHROPIC:-claude-sonnet-4-20250514}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://token-plan-cn.xiaomimimo.com/v1}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      ERUITAH_ENABLE_VNC: ${ERUITAH_ENABLE_VNC:-false}
      ERUITAH_SCREEN_WIDTH: ${ERUITAH_SCREEN_WIDTH:-1280}
      ERUITAH_SCREEN_HEIGHT: ${ERUITAH_SCREEN_HEIGHT:-720}
    volumes:
      - /tmp/eruitah-sandbox:/tmp/eruitah-sandbox
      - /tmp/agent-worktrees:/tmp/agent-worktrees
      - ./coding-agent-ui/dist:/app/coding-agent-ui/dist:ro
    networks:
      - chat-net

  ai-service:
    build:
      context: ./ai-service
      dockerfile: Dockerfile
    container_name: chat-ai-service
    restart: always
    ports:
      - "8081:8081"
      - "9999:9999"
    environment:
      JAVA_OPTS: -Xms256m -Xmx512m
      SPRING_PROFILES_ACTIVE: prod
      SPRING_NEO4J_URI: bolt://neo4j:7687
      SPRING_NEO4J_AUTHENTICATION_USERNAME: neo4j
      SPRING_NEO4J_AUTHENTICATION_PASSWORD: ${NEO4J_PASSWORD:-12345678}
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: 6379
      SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD:-123456}
      SPRING_AI_OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      SPRING_AI_OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode}
      SPRING_AI_OPENAI_CHAT_OPTIONS_MODEL: ${OPENAI_MODEL:-qwen3.5-plus}
      MULTIMODAL_OPENAI_API_KEY: ${MULTIMODAL_API_KEY:-}
      MULTIMODAL_OPENAI_BASE_URL: ${MULTIMODAL_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode}
      MULTIMODAL_OPENAI_MODEL: ${MULTIMODAL_MODEL:-qwen3.5-omni-flash-2026-03-15}
      EMBEDDING_SILICONFLOW_API_KEY: ${EMBEDDING_API_KEY:-}
      EMBEDDING_SILICONFLOW_BASE_URL: ${EMBEDDING_BASE_URL:-https://api.siliconflow.cn}
      EMBEDDING_SILICONFLOW_MODEL: ${EMBEDDING_MODEL:-BAAI/bge-m3}
      RERANKER_SILICONFLOW_API_KEY: ${RERANKER_API_KEY:-}
      RERANKER_SILICONFLOW_BASE_URL: ${RERANKER_BASE_URL:-https://api.siliconflow.cn}
      RERANKER_SILICONFLOW_MODEL: ${RERANKER_MODEL:-BAAI/bge-reranker-v2-m3}
      SERPER_API_KEY: ${SERPER_API_KEY:-}
      SERPER_BASE_URL: ${SERPER_BASE_URL:-https://google.serper.dev}
      VOICE_DASHSCOPE_API_KEY: ${VOICE_API_KEY:-}
      VOICE_DASHSCOPE_ASR_MODEL: ${VOICE_ASR_MODEL:-fun-asr-realtime-2026-02-28}
      VOICE_DASHSCOPE_TTS_MODEL: ${VOICE_TTS_MODEL:-qwen3-tts-instruct-flash-realtime}
      VOICE_DASHSCOPE_TTS_VOICE: ${VOICE_TTS_VOICE:-Cherry}
      VOICE_STORAGE_PATH: /tmp/audio
      VOICE_STORAGE_URL_PREFIX: http://localhost/audio
      RPC_CPP_HOST: chatserver
      RPC_CPP_PORT: 8888
      RPC_PYTHON_HOST: chat-sandbox
      RPC_PYTHON_PORT: 9997
      RPC_INTERNAL_PORT: 9999
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      neo4j:
        condition: service_started
      sandbox:
        condition: service_started
      chatserver:
        condition: service_started
    volumes:
      - audio-storage:/tmp/audio
    networks:
      - chat-net

  nginx:
    image: nginx:1.25-alpine
    container_name: chat-nginx
    restart: always
    ports:
      - "80:80"
      - "8000:8000"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - chatserver
      - ai-service
      - sandbox
    networks:
      - chat-net

volumes:
  mysql-data:
  redis-data:
  neo4j-data:
  neo4j-logs:
  audio-storage:

networks:
  chat-net:
    driver: bridge
```

**启动：**

```bash
# 先配置 .env 文件（参见第14节）
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f ai-service
```

**端口说明：**

| 外部端口 | 协议 | 代理目标 | 说明 |
|----------|------|----------|------|
| 80 | HTTP | ai-service:8081 / sandbox:8001 / butcanthic:8002 | Web API + Web IDE + 文档智能 |
| 8000 | TCP | chatserver:6000 | Qt 客户端连接（Nginx TCP 代理） |
| 6000 | TCP | chatserver:6000 | ChatServer 直接端口（调试用） |
| 8081 | HTTP | ai-service:8081 | AI Service 直接端口（调试用） |
| 8001 | HTTP | sandbox:8001 | Sandbox 直接端口（调试用） |
| 8002 | HTTP | butcanthic:8002 | Butcanthic 直接端口（调试用） |
| 5900 | VNC | sandbox:5900 | VNC 远程桌面（需启用 ERUITAH_ENABLE_VNC） |

---

## 3. 配置详解（AI Service）

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

语音服务支持阿里云ASR + 双TTS引擎（阿里云实时TTS / 小米TTS），自动故障切换：

```yaml
voice:
  aliyun:
    api-key: sk-xxx
    asr-model: fun-asr-realtime-2026-02-28           # 阿里云语音识别模型
    realtime-tts-model: qwen3-tts-instruct-flash-realtime  # 阿里云实时TTS模型
    realtime-tts-voice: Cherry                         # 阿里云TTS语音角色
  xiaomi:
    api-key: sk-xxx                                    # 小米TTS API Key
    base-url: https://token-plan-cn.xiaomimimo.com/v1  # 小米TTS API地址
    tts-model: mimo-v2.5-tts                           # 小米TTS模型
    tts-voice: 冰糖                                    # 小米TTS语音角色
  storage:
    path: /tmp/audio                                   # 音频存储路径
    url-prefix: http://localhost/audio                  # 音频访问URL前缀
```

**阿里云TTS可选语音角色：** Cherry, Serena, Ethan, Chelsie 等

**小米TTS可选语音角色：** 冰糖, 等

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

### 3.16 RPC通信配置

AI Service 通过 Protobuf RPC 与 C++ ChatServer 和 Python Sandbox 通信：

```yaml
rpc:
  cpp:
    host: ${RPC_CPP_HOST:127.0.0.1}     # C++ ChatServer RPC地址
    port: ${RPC_CPP_PORT:8888}           # C++ ChatServer RPC端口
  python:
    host: ${RPC_PYTHON_HOST:127.0.0.1}   # Python Sandbox RPC地址
    port: ${RPC_PYTHON_PORT:9997}         # Python Sandbox RPC端口
  internal:
    port: ${RPC_INTERNAL_PORT:9999}       # AI Service RPC监听端口
```

**RPC通信架构：**

| 连接方向 | 协议 | 端口 | 说明 |
|----------|------|------|------|
| ChatServer → AI Service | Protobuf RPC | 9999 | 转发AI聊天请求 |
| AI Service → ChatServer | Protobuf RPC | 8888 | 推送AI回复、流式消息 |
| AI Service → Sandbox | Protobuf RPC | 9997 | 调用代码沙盒 |

### 3.17 日志级别

```yaml
logging:
  level:
    com.chat.ai: DEBUG
    org.springframework.ai: DEBUG
```

生产环境建议改为 `INFO` 或 `WARN`。

### 3.18 RAG文档处理配置

```yaml
rag:
  chunk-size: 800                        # 文档分块大小（字符数）
  chunk-overlap: 200                     # 分块重叠区域
  top-k: 5                               # 向量检索返回Top-K
  bm25-top-k: 10                         # BM25检索返回Top-K
```

### 3.19 知识图谱初始数据

系统首次启动时，需要向Neo4j导入408考研知识图谱初始数据。知识图谱包含：

- Level 0：408计算机学科专业基础
- Level 1：四大科目（数据结构、计算机组成原理、操作系统、计算机网络）
- Level 2-5：章节和考点层级

**导入方式：** 通过 `/api/graph/extract` 接口逐步构建，或通过Neo4j Browser执行Cypher脚本批量导入。

### 3.20 考情大屏静态资源

系统内置考情大屏HTML页面，访问地址：

```
http://localhost:8081/dashboard.html?userId=1
```

该页面使用ECharts可视化库，展示雷达图和活跃度折线图。

### 3.21 AI 角色注册表（AiPersonaRegistry）

系统内置 9 个 AI 角色（botId 10000-10009），每个角色拥有独立的 System Prompt、是否启用 RAG 知识检索、是否启用工具调用（联网搜索 / C++ 编译 / MCP 文件系统）的差异化配置。C++ 网关转发请求时携带 `botId`，AI Service 据此路由到对应角色处理流。

| botId | 角色名 | 风格定位 | RAG | Tools | 说明 |
|-------|--------|----------|-----|-------|------|
| 10000 | 旗舰大师 | 408 全科终极辅导专家 | ✅ | ✅ | 主对话模型，多智能体编排入口 |
| 10001 | 严厉导师 | 反问式追问教学 | ❌ | ❌ | 苏格拉底式启发 |
| 10002 | 温柔学长 | 生活化类比讲解 | ❌ | ❌ | 通俗易懂 |
| 10003 | 代码审查员 | 高冷极客 | ❌ | ✅ | 启用 MCP 文件系统工具，可读取 `/tmp/408_codes` 目录代码 |
| 10004 | 严厉大 Boss | 面试官组合 | ❌ | ❌ | 模拟面试（压力面） |
| 10005 | 慈祥老教授 | 面试官组合 | ❌ | ❌ | 模拟面试（温和） |
| 10006 | 挑刺狂魔 | 面试官组合 | ❌ | ❌ | 模拟面试（细节追问） |
| 10007 | 解题大王 | 多模态解题 | ✅ | ❌ | 使用多模态模型（qwen3.5-omni-flash）识别图片题目 |
| 10008 | 语音小助手 | 简洁语音对话 | ❌ | ❌ | 短回复，适配 TTS |
| 10009 | 心理委员 | 实时语音心理陪伴 | ❌ | ❌ | 走实时语音 WebSocket 通道 |

**角色定义位置：** `ai-service/src/main/java/com/chat/ai/service/AiPersonaRegistry.java`

**请求路由：** `AiChatRequestListener` 接收 RPC 请求后，根据 botId 分流：
- 10008/10009 → 语音助手流（HTTP 语音聊天 / 实时语音 WS）
- 10007 → 多模态解题流
- 10003 → 代码审查流（带 MCP 工具）
- 10000 → Master 多智能体编排流（AgentOrchestratorService）
- 其他 → 普通角色对话流

### 3.22 多智能体工作流（AgentOrchestratorService）

旗舰大师（botId=10000）启用多智能体编排，包含意图路由与 Solver+Reviewer 双智能体协作：

**意图路由（classify_intent）：**
- **代码求助**：调用 C++ 代码沙盒工具（cppCompilerTool）编译运行用户代码
- **理论解答**：走 RAG 知识检索 + 联网搜索（webSearchTool）
- **日常闲聊**：直接 LLM 生成

**出题 / 判卷工作流：**
- **出题技能**：从知识材料中提取选择题，结合 Neo4j 知识图谱识别用户薄弱点定向出题
- **判卷技能**：在考试状态下严格评分并给出详细解析，更新 Neo4j `COGNITION` 关系（掌握度、最后更新时间）

**Solver + Reviewer 双智能体：**
- **Solver**：生成初稿答案
- **Reviewer**：审核初稿，仅输出最终答案（保证答案质量）

### 3.23 AIOS 桌宠事件总线

AI Service 通过 `@AiosNotify` 注解 + AOP 切面，在方法成功返回后自动向 RabbitMQ 发布桌宠通知事件，C++ 桌面端通过 MQTT 订阅并弹出气泡。

**架构：**

```
AI Service 方法成功返回
        │
        ▼  (@AiosNotify 注解 + AiosNotifyAspect 切面)
RabbitMQ amq.topic 交换机
        │  路由键: aios.events.user_{userId}.{source}
        ▼  (RabbitMQ MQTT 插件)
C++ 桌面宠物 (PetMqttClient 订阅)
        │
        ▼
桌宠气泡通知 + 状态机驱动
```

**使用示例：**

```java
@AiosNotify(source = "farm_judge", successMsg = "已批改完毕，快去看看反馈吧")
public HarvestJudgment judgeFarm(...) { ... }
```

**发布的事件类型：**
- `farm_judge`：农场答题判题完成
- `ai_reply`：AI 回复完成
- `weekly_report`：周报生成完成
- 其他业务事件

### 3.24 RabbitMQ 配置

AIOS 事件总线依赖 RabbitMQ，配置如下：

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:127.0.0.1}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME:admin}
    password: ${RABBITMQ_PASSWORD:eruitah2026}
    virtual-host: /
```

**前置条件：**
- RabbitMQ 需启用 MQTT 插件（供 C++ 桌面端订阅）：`rabbitmq-plugins enable rabbitmq_mqtt`
- 管理界面：http://localhost:15672（账号 admin / 密码 eruitah2026）
- 默认交换机：`amq.topic`（topic 类型）

**Docker 部署 RabbitMQ：**

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 -p 1883:1883 \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=eruitah2026 \
  rabbitmq:3-management
# 启用 MQTT 插件
docker exec rabbitmq rabbitmq-plugins enable rabbitmq_mqtt
```

### 3.25 限流配置（@RateLimit + Redis Lua）

通过 `@RateLimit` 注解 + `RateLimitAspect` 切面 + Redis Lua 脚本（`rate_limit_single.lua`）实现原子化限流，支持 USER 和 IP 双维度。

**注解定义：**

```java
@RateLimit(dimension = "USER", count = 30, interval = 1, timeUnit = TimeUnit.MINUTES)
@PostMapping("/chat")
public ResponseEntity<?> chat(...) { ... }
```

**各接口限流策略：**

| 接口 | 维度 | 限额 | 说明 |
|------|------|------|------|
| `/api/ai/chat` | USER | 30 次/分 | 单用户聊天 |
| `/api/ai/chat` | IP | 60 次/分 | 单 IP 聊天 |
| `/api/ai/mindmap` | USER | 10 次/分 | 思维导图生成 |
| `/api/agent/chat` | USER | 20 次/分 | 多智能体对话 |
| `/api/farm/judge` | USER | 5 次/分 | 农场判题 |
| 其他接口 | USER/IP | 各自配置 | 见各 Controller 注解 |

超出限额抛 `RateLimitExceededException`，由 `GlobalExceptionHandler` 统一返回 429 状态码。

### 3.26 流式输出协议

AI Service 通过 Reactor `Flux<String>` 生成 token 流，经 `RpcPushService` 分块（`bufferTimeout(20, 200ms)`）推送到 C++ 网关，再下发到客户端，实现"打字机"效果。

**流式协议标记：**

| 标记 | 含义 |
|------|------|
| `[STREAM_START]` | 流式开始 |
| `[STREAM_CHUNK]` | 内容分片（可多个） |
| `[STREAM_END]` | 流式结束 |
| `[STREAM_CLEAR]` | 清空当前流（中断/重置） |

**流式接口：**

```bash
# HTTP SSE 流式聊天
curl -N "http://localhost:8081/api/ai/stream-chat?message=你好&sessionId=test_session"

# RPC 流式（C++ 网关转发，botId=10000 旗舰大师默认流式）
```

### 3.27 Fallback 备用模型配置

当主模型（OPENAI_MODEL）调用失败时，自动切换到备用模型（FALLBACK_MODEL），保证服务可用性。

```yaml
fallback:
  openai:
    api-key: ${FALLBACK_API_KEY:}
    base-url: ${FALLBACK_BASE_URL:https://api.siliconflow.cn}
    model: ${FALLBACK_MODEL:Qwen/Qwen2.5-72B-Instruct}
```

**环境变量：**

```bash
FALLBACK_API_KEY=your-siliconflow-api-key      # 备用模型 API Key
FALLBACK_BASE_URL=https://api.siliconflow.cn   # 备用模型地址
FALLBACK_MODEL=Qwen/Qwen2.5-72B-Instruct       # 备用模型名称
```

### 3.28 伴读功能（CompanionReadingService）

用户在客户端划选文本后，AI Service 执行：知识图谱检索 → 100 字精简讲解 → TTS 合成音频，实现"伴读"体验。

**流程：**
1. 客户端上传选中文本 + 上下文
2. 调用 Neo4j 知识图谱检索相关 Concept 节点
3. LLM 生成 100 字以内讲解
4. TTS 合成音频并返回 URL

### 3.29 考情大屏 AI 周报定时任务

`WeeklyReportScheduler` 定时任务每周自动生成用户学习周报，通过 AIOS 事件总线推送桌宠通知。

**周报内容：**
- 本周做题活跃度（按日统计）
- 四科（数据结构/组成原理/操作系统/计算机网络）掌握度雷达图数据
- 薄弱点 Top-N 概念推荐
- AI 生成的学习建议

**接口：**

```bash
# 手动触发生成周报
curl -X POST http://localhost:8081/api/analysis/dashboard/1/report
```

### 3.30 CORS 配置

```yaml
app:
  cors:
    allowed-origins:
      - "http://localhost:5173"     # Coding Agent UI 开发
      - "http://localhost:5174"     # Butcanthic Frontend 开发
      - "http://localhost:8002"     # Butcanthic 服务
    allowed-methods: GET,POST,PUT,DELETE,OPTIONS
    allow-credentials: true
```

生产环境应限制为实际域名。

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

## 6. 常见问题（AI Service）

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

## 7. C++服务器端安装配置

### 7.1 环境要求

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

### 7.2 安装muduo网络库

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

### 7.3 安装MySQL和Redis客户端库

**Ubuntu/Debian：**

```bash
sudo apt-get install -y libmysqlclient-dev libhiredis-dev
```

**CentOS/RHEL：**

```bash
sudo yum install -y mysql-devel hiredis-devel
```

### 7.4 数据库初始化

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

Docker Compose 部署时，`docker/mysql/init.sql` 会在 MySQL 容器首次启动时自动执行。

### 7.5 修改CMakeLists.txt配置

编辑 `/home/xmy/code/src/server/CMakeLists.txt`，修改muduo路径：

```cmake
# 设置muduo路径
set(MUDUO_ROOT_DIR "/home/xmy/muduo")  # 修改为你的muduo安装路径
```

### 7.6 编译服务器

```bash
cd /home/xmy/code
mkdir -p build && cd build
cmake ..
make ChatServer -j$(nproc)
```

编译产物位于 `bin/ChatServer`

### 7.7 启动服务器

```bash
# 前台运行
./bin/ChatServer

# 后台运行
nohup ./bin/ChatServer > chatserver.log 2>&1 &
```

服务器默认监听端口 **6000**（Docker 部署时通过 `CMD ["./ChatServer", "0.0.0.0", "6000"]` 指定）。

**端口说明：**
- **6000**：ChatServer TCP 监听端口，Qt 客户端直连或通过 Nginx TCP 代理（:8000）连接
- **8888**：ChatServer RPC 端口，用于 Protobuf RPC Bridge 通信
- **8000**：Nginx TCP 代理端口，将流量转发到 chatserver:6000

### 7.8 配置说明

服务器配置通过代码硬编码，主要配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 服务器端口 | 6000 | TCP监听端口 |
| RPC端口 | 8888 | Protobuf RPC Bridge 端口 |
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

Docker 部署时通过环境变量覆盖：`MYSQL_HOST`、`MYSQL_PASSWORD`、`REDIS_HOST`、`REDIS_PASSWORD` 等。

### 7.9 408 农场游戏化学习

ChatServer 内置"408 农场"游戏化学习模块，将做题与种田玩法结合，激励用户练习。农场数据存储在 MySQL 的 `farm_user`、`farm_plot`、`farm_log` 三张表中。

**玩法流程：**
1. 用户在自己农场（共 9 个地块）种下题目（选择题/判断题），标注科目（OS 操作系统 / NET 计算机网络 / DS 数据结构 / CO 组成原理）
2. 其他用户或 AI 机器人（通过 RPC 调用 AI Service 的 `/api/farm/judge`）答题
3. AI Service 评分并给出反馈（HarvestJudgment：是否答对、得分、详细解析）
4. 答对则作物成熟可收割，获得金币和经验；答错作物枯萎
5. 全服广播农场日志（Redis Pub/Sub 频道）

**涉及数据表：**

```sql
-- 农场用户表
CREATE TABLE farm_user (
    userid INT PRIMARY KEY,
    coins INT DEFAULT 0,        -- 金币
    exp INT DEFAULT 0           -- 经验
);

-- 农场地块表
CREATE TABLE farm_plot (
    ownerid INT NOT NULL,
    plotindex INT NOT NULL,     -- 0-8 共9块地
    state INT DEFAULT 0,        -- 0空地 1已种植 2成熟 3枯萎
    question VARCHAR(500),
    subject VARCHAR(50),        -- OS/NET/DS/CO
    answererid INT,
    answer VARCHAR(1000),
    score INT,
    feedback VARCHAR(500),
    PRIMARY KEY(ownerid, plotindex)
);

-- 农场日志表（全服广播）
CREATE TABLE farm_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    userid INT NOT NULL,
    action VARCHAR(100),
    detail VARCHAR(500),
    createtime DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**AI 判题调用链：**
ChatServer → `AiServiceClient` → InternalRpcClient → AI Service `/api/farm/judge` → FarmAiJudgeService → 通过 `@AiosNotify` 推送桌宠通知

### 7.10 面试群功能

ChatServer 支持创建"面试群"，群内可挂载多个面试官 AI 角色（botId 10004-10006：严厉大 Boss / 慈祥老教授 / 挑刺狂魔），模拟真实面试场景的多对一压力面试。

**消息流程：**
1. 用户在面试群发言
2. C++ 网关附带 `aiBotIds` 列表（如 [10004, 10005, 10006]）通过 RPC 转发给 AI Service
3. AI Service 并发触发多 AI 角色回复
4. 各角色回复经 `RpcPushService` 推回 C++ 网关下发到客户端

---

## 8. C++客户端安装配置

### 8.1 环境要求

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

### 8.2 安装Qt 5

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

### 8.3 编译客户端

```bash
cd /home/xmy/code
mkdir -p build && cd build
cmake ..
make QtChat -j$(nproc)
```

编译产物位于 `bin/QtChat`

### 8.4 运行客户端

```bash
./bin/QtChat
```

### 8.5 客户端配置

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

**注意：** 客户端连接端口为 **8000**（Nginx TCP 代理端口），而非 ChatServer 直接端口 6000。如果直连 ChatServer，则使用 6000。

### 8.6 Live2D资源

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

### 8.7 客户端环境变量

C++ 客户端 / 服务器通过环境变量配置连接，均带默认值：

| 环境变量 | 默认值 | 说明 | 配置位置 |
|----------|--------|------|----------|
| `MYSQL_HOST` | `127.0.0.1` | MySQL 主机 | `include/server/db/db.h` |
| `MYSQL_USER` | `root` | MySQL 用户 | 同上 |
| `MYSQL_PASSWORD` | `xieming562` | MySQL 密码 | 同上 |
| `MYSQL_DBNAME` | `chat` | 数据库名 | 同上 |
| `REDIS_HOST` | `127.0.0.1` | Redis 主机 | `server/redis/redis.cpp` |
| `REDIS_PORT` | `6379` | Redis 端口 | 同上 |
| `REDIS_PASSWORD` | `123456` | Redis 密码 | 同上 |
| `JAVA_RPC_HOST` | `127.0.0.1` | Java AI Service RPC 地址 | `server/main.cpp` |
| `JAVA_RPC_PORT` | `9999` | Java AI Service RPC 端口 | 同上 |
| `RPC_LISTEN_PORT` | `8888` | C++ RPC 监听端口 | 同上 |

### 8.8 桌面宠物 + 微服务大管家

客户端内置桌面宠物（`desktoppet.h/.cpp`），既是趣味伴学形象，也是微服务"大管家"：

**功能：**
- **待机动画**：Live2D 风格的桌宠待机/拖拽交互
- **微服务健康监控**：`ServiceMonitor` 周期轮询 `butcanthic`（:8002）、`sandbox`（:8001）、`ai-service`（:8081）三个微服务的健康端点
- **状态机气泡**：根据监控结果驱动状态机，弹出气泡报告服务异常/恢复
- **闪卡碎碎念**：Idle 时从 AI Service 拉取"闪卡知识"（间隔重复记忆卡），桌宠碎碎念推送学习卡片

**监控目标：**

| 微服务 | 健康端点 | 端口 |
|--------|----------|------|
| Butcanthic | `/api/v1/health` | 8002 |
| Eruitah Sandbox | `/api/v1/health` | 8001 |
| AI Service | `/api/ai/health` | 8081 |

### 8.9 全局事件总线（MQTT + RabbitMQ）

客户端通过 `PetMqttClient`（mosquitto MQTT 客户端）订阅 RabbitMQ 的 AIOS 事件总线，接收跨微服务事件并由 `GlobalEventBus` 单例广播到 UI 层。

**架构：**

```
各微服务事件 ──► RabbitMQ amq.topic ──► (MQTT 插件 :1883) ──► PetMqttClient ──► GlobalEventBus ──► UI 层
```

**MQTT 配置（代码硬编码）：**

| 配置项 | 默认值 | 位置 |
|--------|--------|------|
| MQTT Broker | `127.0.0.1:1883` | `petmqttclient.h` |
| 用户名 | `admin` | 同上 |
| 密码 | `eruitah2026` | 同上 |
| 订阅主题 | `aios.events.user_{userId}.#` | 同上 |

**前置条件：** RabbitMQ 必须启用 MQTT 插件（`rabbitmq-plugins enable rabbitmq_mqtt`），见 3.24 节。

### 8.10 职业辅导套件

客户端内置完整的职业辅导套件，结合 AI Service 的职业档案分析能力：

| 模块 | 文件 | 功能 |
|------|------|------|
| 职业仪表盘 | `career_dashboard_dialog.cpp` | 展示职业能力雷达图（ECharts，加载 `html/career_radar.html`） |
| 职业历史 | `career_history.cpp` | 历史职业建议记录 |
| AI 职业建议弹窗 | `careeradvicepopup.cpp` | AI 生成的职业建议（经 RPC 从 AI Service 推送） |
| 职业卡片 | `career_card_widget.cpp` | 技能卡片组件 |

**数据流：** AI Service `GraphExamService` 分析用户能力 → 通过 RPC `SendCareerAdvice` / `UpdateCareerProfile` 推送到 C++ 网关 → 客户端弹窗展示。

### 8.11 AI 数字人伴读（Live2D）

客户端集成 Live2D Cubism 数字人（Hiyori 模型），通过 Qt WebEngine + WebGL 渲染，提供 AI 伴读体验：

| 组件 | 文件 | 功能 |
|------|------|------|
| 伴读对话框 | `companionreadingdialog.cpp` | PDF 上传解析 + AI 讲解 + TTS 音频下载 |
| Live2D 渲染 | `html/avatar.html` | WebEngine 加载 Hiyori 模型，WebGL 渲染 |
| 知识图谱可视化 | `html/graph.html` | ECharts 图谱展示 |

**环境要求：**
- Linux 下需 `QT_QPA_PLATFORM=xcb` 且支持 WebGL
- `main.cpp` 中设置 `QTWEBENGINE_CHROMIUM_FLAGS` 启用 WebGL 并忽略 GPU 黑名单
- 远程调试端口 `QTWEBENGINE_REMOTE_DEBUGGING=9222`

### 8.12 qt-material-widgets 依赖

客户端 UI 使用 Material Design 风格控件，源码位于父目录 `qt-material-widgets/`，构建时通过 CMake `add_subdirectory` 引入。无需单独安装，但需确保该目录存在。

---

## 9. Butcanthic 文档智能服务安装配置

Butcanthic 是基于 FastAPI + LangGraph 的企业级文档智能处理服务，支持 Word/Excel/PPT 自动填充、PPT 生成、知识库 RAG 检索、联网搜索等功能。

### 9.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | 运行时环境（LangGraph 需要 3.11+） |
| pip | 21+ | 包管理器 |
| Node.js | 18+ | 前端构建环境（可选，仅开发 Butcanthic Frontend 时需要） |

### 9.2 安装 Python 依赖

```bash
cd /home/xmy/code/butcanthic

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**requirements.txt 核心依赖：**

| 依赖 | 版本 | 说明 |
|------|------|------|
| fastapi | 0.115+ | Web 框架 |
| uvicorn | 0.34+ | ASGI 服务器 |
| langchain | 0.3+ | LLM 编排框架 |
| langchain-openai | 0.3+ | OpenAI 兼容接口 |
| langgraph | 0.2+ | 多 Agent 工作流引擎 |
| chromadb | 0.5+ | 嵌入式向量数据库 |
| rank-bm25 | 0.2.2+ | BM25 稀疏检索 |
| jieba | 0.42+ | 中文分词 |
| openai | 1.60+ | OpenAI SDK |
| python-docx | 1.1+ | Word 文档解析 |
| python-pptx | 1.0+ | PPT 文档解析 |
| openpyxl | 3.1+ | Excel 文档解析 |
| pypdf | 6.0+ | PDF 文档解析 |
| celery | 5.4+ | 异步任务队列 |
| redis | 5.2+ | Celery Broker |
| PyJWT | 2.8+ | JWT 鉴权 |
| sqlalchemy | 2.0+ | 元数据数据库 ORM |
| networkx | 3.2+ | 知识图谱 |
| ddgs | 6.0+ | 联网搜索（DuckDuckGo） |

### 9.3 配置 AI 模型

Butcanthic 使用 `ai_models_config.json` 配置 AI 模型提供商。首次启动时会自动生成默认配置文件。

**手动创建配置文件：**

```bash
cd /home/xmy/code/butcanthic
cat > ai_models_config.json << 'EOF'
{
  "default_model": "qwen-plus",
  "models": {
    "qwen-plus": {
      "provider": "aliyun",
      "api_key": "your-dashscope-api-key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen-plus",
      "max_input_tokens": 997952,
      "max_output_tokens": 81920,
      "temperature": 0.0,
      "top_p": 0.1,
      "description": "阿里云通义千问Plus"
    },
    "doubao-seed-1-6-flash": {
      "provider": "volcano",
      "api_key": "your-volcano-api-key",
      "base_url": "https://ark.cn-beijing.volces.com/api/v3",
      "model_name": "doubao-seed-1-6-flash-250828",
      "max_input_tokens": 32000,
      "max_output_tokens": 9999,
      "temperature": 0.0,
      "top_p": 0.9,
      "description": "火山引擎豆包Flash"
    }
  },
  "embedding": {
    "api_key": "your-siliconflow-api-key",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "BAAI/bge-m3",
    "dimension": 1024
  },
  "reranker": {
    "api_key": "your-siliconflow-api-key",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "BAAI/bge-reranker-v2-m3"
  }
}
EOF
```

### 9.4 环境变量配置

Butcanthic 支持通过 `.env` 文件或环境变量覆盖配置：

```bash
cd /home/xmy/code/butcanthic
cat > .env << 'EOF'
# 嵌入模型配置（覆盖 ai_models_config.json 中的 embedding 配置）
EMBEDDING_API_KEY=your-siliconflow-api-key
DASHSCOPE_API_KEY=your-dashscope-api-key

# 可选：Celery 异步任务
USE_CELERY=true

# 可选：Unsplash 图片搜索（PPT生成使用）
UNSPLASH_ACCESS_KEY=
EOF
```

### 9.5 启动服务

**开发模式：**

```bash
cd /home/xmy/code/butcanthic
source venv/bin/activate
python main.py
```

服务默认监听端口 **8002**，访问 http://localhost:8002。

**生产模式：**

```bash
uvicorn main:app --host 0.0.0.0 --port 8002 --workers 4
```

**启动 Celery Worker（异步任务模式）：**

```bash
cd /home/xmy/code/butcanthic
source venv/bin/activate
celery -A app.core.celery_app worker --loglevel=info
```

### 9.6 Butcanthic Frontend 安装

Butcanthic 前端是基于 React + Vite 的 PPT 查看器和知识图谱可视化组件：

```bash
cd /home/xmy/code/butcanthic/frontend_vite

# 安装依赖
npm install

# 开发模式
npm run dev
# 访问 http://localhost:5174

# 构建生产版本
npm run build
```

**前端核心依赖：**

| 依赖 | 版本 | 说明 |
|------|------|------|
| React | 18.3+ | UI 框架 |
| Vite | 6.0+ | 构建工具 |
| ECharts | 6.1+ | 图表可视化 |
| echarts-for-react | 3.0+ | React ECharts 封装 |

### 9.7 LangGraph 工作流架构

Butcanthic 的核心是 LangGraph 多 Agent 工作流，支持条件路由和自我纠错：

```
START → Gateway → Router (条件路由)
                    ├─ docx → ExtractContext → RetrieveKnowledge → ReasonAndFill → CriticReview → END
                    │                                                              ↑ retry ↓
                    │                                                     increment_retry (循环，最多3次)
                    ├─ xlsx → ProcessExcel (Data Agent + Self-Correction) → END
                    ├─ pptx → ProcessPPT → END
                    └─ generate_ppt → Supervisor → [WebResearcher | KnowledgeLibrarian | GeneratePPT]
                                        └─ GeneratePPT → CriticReviewPPT ──→ PASS → END
                                                                ↑ REJECT ↓
                                                                └── (循环，最多3次)
```

**工作流节点说明：**

| 节点 | Agent名 | 功能 |
|------|---------|------|
| gateway | 包工头 | 文件类型检测与路由 |
| extract_context | ExtractAgent | Word 文档字段提取 |
| retrieve_knowledge | RetrievalAgent | RAG 知识检索（三路混合） |
| reason_and_fill | FillAgent | AI 推理填充 |
| critic_review | CriticAgent | 审查校验（pass/fail） |
| process_excel | DataAgent | Excel 数据清洗（含自我纠错） |
| process_ppt | PPTAgent | PPT 分析 |
| supervisor | Supervisor | 主管调度（指派子Agent） |
| web_researcher | WebResearcher | 联网搜索 |
| knowledge_librarian | KnowledgeLibrarian | 知识库检索 |
| generate_ppt | PPTGenAgent | PPT 生成 |
| critic_review_ppt | PPTCriticAgent | PPT 审查校验 |
| generate_summary | SummaryAgent | 长文总结 |
| auto_tagging | Auto_Tagging | 自动标签提取 |
| literature_guide | Literature_Guide | 文献导读 |

### 9.8 RAG 检索引擎

Butcanthic 内置三路混合检索引擎：

| 检索方式 | 技术 | Top-K | 说明 |
|----------|------|-------|------|
| 向量检索 | ChromaDB + BGE-M3 | 10 | 语义相似度检索 |
| 稀疏检索 | BM25 + jieba | 10 | 关键词精确匹配 |
| 图谱检索 | NetworkX + LLM | - | 实体关系推理（GraphRAG） |

三路召回结果去重合并后，经 BGE-Reranker-V2-m3 重排序，返回 Top-5。

**用户级隔离：** 每个用户拥有独立的 Chroma Collection（`kb_user_{user_id}`），数据物理隔离。

### 9.9 验证安装

```bash
# 健康检查
curl http://localhost:8002/api/v1/health

# 文档处理（需先上传知识库文档）
curl -X POST http://localhost:8002/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{"user_instruction": "帮我总结一下数据结构的知识点"}'

# 知识库上传
curl -X POST http://localhost:8002/api/v1/knowledge/upload \
  -F "file=@test.pdf"
```

### 9.10 GraphRAG 引擎

Butcanthic 在 ChromaDB 向量检索 + BM25 稀疏检索之外，额外内置 GraphRAG 引擎，基于 Neo4j 图数据库 + networkx + matplotlib 实现实体关系推理。

**三路混合检索增强为四路：**

| 检索方式 | 技术 | Top-K | 说明 |
|----------|------|-------|------|
| 向量检索 | ChromaDB + BGE-M3 | 10 | 语义相似度检索 |
| 稀疏检索 | BM25 + jieba | 10 | 关键词精确匹配 |
| 图谱检索 | Neo4j + networkx + LLM | - | 实体关系推理（GraphRAG） |
| 重排序 | BGE-Reranker-V2-m3 | Top-5 | 多路召回去重合并后重排 |

**GraphRAG 流程：**
1. LLM 从文档抽取三元组（实体-关系-实体）
2. 写入 Neo4j 图数据库
3. 查询时 LLM 提取查询实体，Neo4j 子图检索
4. networkx 分析 + matplotlib 可视化

**GraphRAG API：**

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/graph/data` | GET | 获取图谱数据 |
| `/api/v1/graph/node/{id}` | GET | 获取节点详情 |
| `/api/v1/graph/stats` | GET | 图谱统计 |
| `/api/v1/graph/search` | POST | 图谱搜索 |
| `/api/v1/graph/node/{id}/sources` | GET | 节点来源 |

### 9.11 元数据库（SQLAlchemy + SQLite）

Butcanthic 使用 SQLAlchemy + SQLite 存储元数据（`metadata.db`），包含三张核心表：

| 模型 | 表 | 说明 |
|------|-----|------|
| `User` | user | 用户表（JWT 鉴权用） |
| `DocumentMeta` | document_meta | 文档元数据（任务ID、文件名、状态、用户ID） |
| `Flashcard` | flashcard | 闪卡（间隔重复记忆卡，Q&A） |

**数据库文件：** `/home/xmy/code/butcanthic/metadata.db`（首次启动自动创建）

### 9.12 事件总线（RabbitMQ）

Butcanthic 通过 `app/core/event_bus.py`（pika 客户端）接入 AIOS 全局事件总线，向 RabbitMQ 发布文档处理进度、知识库更新等事件，供 C++ 桌面宠物订阅。

**前置条件：** RabbitMQ 已启动且账号为 admin / eruitah2026（见 3.24 节）。

### 9.13 JWT 鉴权

Butcanthic 使用 PyJWT + bcrypt + OAuth2 密码模式实现用户鉴权，部分接口需在请求头携带 `Authorization: Bearer <token>`。

**鉴权 API：**

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/auth/silent-login` | POST | 静默登录（按用户名自动注册/登录） |
| `/api/v1/auth/register` | POST | 注册 |
| `/api/v1/auth/login` | POST | 登录 |
| `/api/v1/auth/token` | POST | OAuth2 token 获取 |
| `/api/v1/auth/me` | GET | 获取当前用户信息 |

### 9.14 完整 REST API 列表

Butcanthic 提供约 60+ 个端点，均以 `/api/v1` 为前缀：

| 分类 | 端点 | 说明 |
|------|------|------|
| 鉴权 | `/auth/*` | 见 9.13 |
| 文档 | `/document/upload`、`/document/process`、`/documents/list`、`/documents/my`、`/document/download/{task_id}` | 文档上传/处理/列表/下载 |
| 任务 | `/task/submit`、`/task/stream-process`、`/task/{task_id}/stream`、`/task/{task_id}`、`/tasks/{task_id}`、`/tasks/{task_id}/followup`、`/tasks/{task_id}/delete_turn/{turn_index}` | 任务提交/SSE 流式/详情/多轮追问/删除轮次 |
| PPT | `/task/edit-slide`、`/task/export-pptx` | PPT 编辑/导出 |
| 知识库 | `/knowledge/upload`、`/knowledge/upload-file`、`/knowledge/upload-files`、`/knowledge/search`、`/knowledge/stats`、`/knowledge/transfer_to_rag/{task_id}` | 知识库上传/搜索/统计/转 RAG |
| KB 管理 | `/kb/upload`、`/kb/task_status/{task_id}`、`/kb/documents`、`/kb/documents/{document_id}` | 知识库管理（DELETE 删除） |
| 图谱 | `/graph/*` | 见 9.10 |
| 闪卡 | `/flashcards/draw`、`/flashcards/review`、`/flashcards/due` | 间隔重复闪卡（抽取/复习/到期） |
| 调试 | `/debug/graph/wipe_user` | 清空用户图谱数据 |

### 9.15 闪卡（间隔重复）功能

Butcanthic 内置间隔重复（Spaced Repetition）闪卡系统，基于 LLM 从知识库文档自动抽取 Q&A 对，存入 SQLite `flashcard` 表，供 C++ 桌宠"碎碎念"推送和客户端复习。

**闪卡 API：**

```bash
# 抽取一张闪卡
curl -X POST http://localhost:8002/api/v1/flashcards/draw \
  -H "Authorization: Bearer <token>"

# 提交复习结果（更新记忆曲线）
curl -X POST http://localhost:8002/api/v1/flashcards/review \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"card_id": 1, "rating": "good"}'

# 查询到期闪卡
curl http://localhost:8002/api/v1/flashcards/due \
  -H "Authorization: Bearer <token>"
```

### 9.16 Excel 数据对话（DuckDB）

Butcanthic 通过 DuckDB 引擎支持 Excel 多轮自然语言对话，`chat_excel_node` Agent 将用户问题转译为 SQL 在 DuckDB 中执行，返回查询结果。

**依赖：** `duckdb`（pip 安装）

**触发方式：** 上传 Excel 后，在 `/tasks/{task_id}/followup` 多轮追问接口中提问。

### 9.17 DOCX 转 HTML（Node.js + mammoth）

Butcanthic 通过 Node.js + mammoth 将 DOCX 文档转为 HTML 供前端预览，转换脚本位于 `app/services/docx_to_html_converter.js`。

**前置条件：**
- 已安装 Node.js 18+
- 已安装 mammoth 包：`cd app/services && npm install`

### 9.18 工作流节点详解

LangGraph 工作流节点（9.7 节已列出名称）的功能补充说明：

| 节点 | Agent | 功能说明 |
|------|-------|----------|
| web_researcher | WebResearcher | 联网调研 Agent，使用 ddgs（DuckDuckGo）搜索，生成调研报告填充 Word 文档 |
| knowledge_librarian | KnowledgeLibrarian | 私有知识库检索 Agent，从用户 ChromaDB Collection 检索 |
| generate_summary | SummaryAgent | 长文总结生成 |
| auto_tagging | Auto_Tagging | 自动标签提取，为文档打分类标签 |
| literature_guide | Literature_Guide | 文献导读，生成文献阅读路径 |
| chat_excel | ExcelChatAgent | Excel 多轮对话（DuckDB） |

### 9.19 Celery Worker OOM 防护

Celery Worker 配置了 OOM（内存溢出）防护，避免长任务堆积导致内存泄漏：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `max_tasks_per_child` | 5 | 每处理 5 个任务后 Worker 自动重启 |
| 内存阈值 | 300MB | 内存超 300MB 自动重启 |
| `CELERY_WORKER_CONCURRENCY` | 2 | Worker 并发数 |

**环境变量（`celery_app.py`）：**

```bash
REDIS_PASSWORD=123456
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CELERY_BROKER_URL=redis://:123456@127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://:123456@127.0.0.1:6379/1
CELERY_WORKER_CONCURRENCY=2
```

### 9.20 Vue 3 SPA 主界面

Butcanthic 主界面（`static/index.html`）是基于 Vue 3 + Tailwind CSS + ECharts 的单页应用（CDN 引入，无需构建），终端风格 UI，包含上传、任务进度流、文档预览、知识图谱可视化。

- 与 React PPT 预览组件（`frontend_vite/`，9.6 节）配合使用
- React 组件构建产物输出到 `static/ppt-viewer/`，由主界面引用

### 9.21 配置项说明（Settings）

`app/core/config.py` 中的 `Settings` 配置类（从 `.env` 读取）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROJECT_NAME` | Enterprise Document Copilot | 项目名 |
| `API_V1_PREFIX` | /api/v1 | API 前缀 |
| `ALLOWED_ORIGINS` | localhost:5174, 127.0.0.1:5174, 127.0.0.1:8002 | CORS 允许源 |
| `UPLOAD_DIR` / `OUTPUT_DIR` | uploads / output | 上传/输出目录 |
| `AI_CONFIG_PATH` | ai_models_config.json | AI 模型配置文件 |
| `EMBEDDING_MODEL` | BAAI/bge-m3 | 嵌入模型 |
| `EMBEDDING_DIMENSION` | 1024 | 嵌入维度 |
| `MAX_UPLOAD_SIZE_MB` | 50 | 最大上传大小 |
| `USE_CELERY` | True | 是否启用 Celery 异步任务 |
| `UNSPLASH_ACCESS_KEY` | （空） | Unsplash 图片搜索（PPT 生成用） |

> **注意：** 配置中存在 `QDRANT_HOST/PORT/COLLECTION` 字段，但实际未使用，向量库真正使用的是 ChromaDB（见 `rag_engine.py` 的 `_init_chroma`）。

---

## 10. Eruitah智能编程沙盒安装配置

### 10.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 运行时环境 |
| pip | 21+ | 包管理器 |
| ripgrep (rg) | - | 可选，代码搜索加速（推荐安装） |

### 10.2 安装Python依赖

```bash
cd /home/xmy/code/eruitah-sandbox

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**requirements.txt 完整内容：**

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
sentence-transformers>=2.2.0
numpy>=1.24.0
playwright>=1.40.0
pexpect>=4.8.0
pyautogui>=0.9.54
mss>=9.0.0
```

**依赖说明：**
- `sentence-transformers` + `numpy`：本地向量嵌入，用于语义搜索
- `playwright`：浏览器自动化，支持 Chromium 操作
- `pexpect`：交互式进程管理
- `pyautogui` + `mss`：GUI 自动化操作与屏幕截图（VNC 模式下使用）

### 10.3 环境变量配置

在项目根目录 `/home/xmy/code/.env` 文件中配置（参见第14节完整说明）：

```bash
# Eruitah 沙盒配置
ERUITAH_SANDBOX_DIR=/tmp/eruitah-sandbox
ERUITAH_API_PROVIDER=openai
ERUITAH_MODEL_OPENAI=mimo-v2.5
ERUITAH_MODEL_ANTHROPIC=claude-sonnet-4-20250514

# OpenAI 兼容接口
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# Anthropic Claude（可选）
ANTHROPIC_API_KEY=sk-xxx

# VNC 配置（可选）
ERUITAH_ENABLE_VNC=false
ERUITAH_SCREEN_WIDTH=1280
ERUITAH_SCREEN_HEIGHT=720

# ===== Butcanthic 文档智能服务 =====
BUTCANTHIC_HOST=0.0.0.0
BUTCANTHIC_PORT=8002
EMBEDDING_API_KEY=your-siliconflow-api-key
DASHSCOPE_API_KEY=your-dashscope-api-key
USE_CELERY=true
UNSPLASH_ACCESS_KEY=
```

### 10.4 启动服务

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

### 10.5 安装ripgrep（可选但推荐）

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

### 10.6 Docker部署

**构建镜像：**

```bash
cd /home/xmy/code/eruitah-sandbox
docker build -t eruitah-sandbox:1.0.0 .
```

**运行容器：**

```bash
docker run -d --name eruitah-sandbox \
  -p 8001:8001 \
  -p 5900:5900 \
  -v /tmp/eruitah-sandbox:/tmp/eruitah-sandbox \
  -e OPENAI_API_KEY=sk-xxx \
  -e OPENAI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1 \
  -e ERUITAH_ENABLE_VNC=false \
  eruitah-sandbox:1.0.0
```

**Docker 镜像包含的系统依赖：**

| 依赖 | 说明 |
|------|------|
| Xvfb | X11 虚拟帧缓冲，提供无头显示环境 |
| x11vnc | VNC 服务器，支持远程桌面查看 |
| xdotool / scrot / imagemagick | GUI 自动化工具（鼠标键盘模拟、截图） |
| wmctrl | 窗口管理工具 |
| fonts-noto-cjk / fonts-wqy-zenhei | 中日韩字体 |
| Chromium (Playwright) | 浏览器自动化引擎 |
| clangd | C/C++ LSP 语言服务器 |
| default-jdk + JDTLS | Java LSP 语言服务器 |
| Node.js 20 | JavaScript/TypeScript 运行环境 |
| pyright + typescript-language-server | Python/TypeScript LSP 语言服务器 |

**端口说明：**
- **8001**：HTTP/WebSocket 服务端口
- **5900**：VNC 远程桌面端口（需 `ERUITAH_ENABLE_VNC=true`）

### 10.7 VNC 配置

当 `ERUITAH_ENABLE_VNC=true` 时，容器启动脚本 `entrypoint.sh` 会自动启动 x11vnc：

1. 启动 Xvfb 虚拟桌面（`:99`，分辨率由 `ERUITAH_SCREEN_WIDTH` × `ERUITAH_SCREEN_HEIGHT` 决定）
2. 启动 x11vnc 监听 5900 端口
3. 启动 uvicorn 服务

**VNC 连接方式：**

```bash
# 使用 VNC 客户端连接
vnc://localhost:5900

# 或使用 noVNC（需额外安装）
# http://localhost:5900/vnc.html
```

### 10.8 MCP 服务配置

Sandbox 内置 MCP (Model Context Protocol) 服务，配置文件为 `eruitah-sandbox/mcp.json`：

| MCP Server | 说明 |
|------------|------|
| @modelcontextprotocol/server-filesystem | 文件系统访问 |
| @modelcontextprotocol/server-github | GitHub Issues/PR/代码搜索（需 GITHUB_PERSONAL_ACCESS_TOKEN） |
| @modelcontextprotocol/server-puppeteer | 浏览器自动化（使用系统 Chromium） |
| @modelcontextprotocol/server-postgres | PostgreSQL 数据库查询 |
| @modelcontextprotocol/server-memory | 知识图谱持久化记忆 |
| @modelcontextprotocol/server-sequential-thinking | 结构化推理 |

Docker 镜像构建时已预安装这些 MCP Server 包。

### 10.9 LSP 工具配置

Sandbox 内置多种 LSP 语言服务器，提供代码智能补全和诊断：

| LSP | 语言 | 安装方式 |
|-----|------|----------|
| clangd | C/C++ | apt 安装 |
| JDTLS | Java | 下载至 /opt/jdtls |
| pyright | Python | npm 全局安装 |
| typescript-language-server | TypeScript/JavaScript | npm 全局安装 |

**环境变量：**
- `JDTLS_HOME=/opt/jdtls`：JDTLS 安装目录
- `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`：Java 运行时

### 10.10 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ERUITAH_SANDBOX_DIR` | `/tmp/eruitah-sandbox` | 沙盒工作目录 |
| `ERUITAH_API_PROVIDER` | `openai` | API提供商（openai/anthropic） |
| `ERUITAH_MODEL_OPENAI` | `mimo-v2.5` | OpenAI兼容模型名称 |
| `ERUITAH_MODEL_ANTHROPIC` | `claude-sonnet-4-20250514` | Anthropic模型名称 |
| `OPENAI_API_KEY` | - | OpenAI API密钥 |
| `OPENAI_BASE_URL` | `https://token-plan-cn.xiaomimimo.com/v1` | OpenAI兼容API地址 |
| `ANTHROPIC_API_KEY` | - | Anthropic API密钥 |
| `ERUITAH_ENABLE_VNC` | `false` | 是否启用VNC远程桌面 |
| `ERUITAH_SCREEN_WIDTH` | `1280` | 虚拟桌面宽度 |
| `ERUITAH_SCREEN_HEIGHT` | `720` | 虚拟桌面高度 |

### 10.11 验证安装

```bash
# 健康检查
curl http://localhost:8001/api/v1/health

# 预期返回
# {"status":"ok","sandbox_dir":"/tmp/eruitah-sandbox","api_provider":"openai"}

# WebSocket测试（使用wscat）
wscat -c ws://localhost:8001/ws/coding
# 发送: {"task":"列出当前目录文件"}
```

### 10.12 "绝对网关"架构与 Supervisor（CTO 监工）

Eruitah Sandbox v4 采用"绝对网关（Absolute Gateway）"架构：所有新任务先经过 Supervisor（CTO 监工）审题，做意图判定后再决定执行模式。

**意图判定（三种）：**

| 意图 | 说明 | 执行模式 |
|------|------|----------|
| TOUR | 代码导览请求 | 调用 `tour_generator` 生成代码讲解路径 |
| AMBIGUOUS | 需求暧昧不清 | Agent 反问澄清需求 |
| CODE | 明确的编码任务 | 进入编码流程 |

**两种执行模式：**
- **极速模式**：单体 Agent 直接执行（简单任务）
- **深度模式**：红蓝对抗 Swarm 多智能体协同（复杂任务）

**专家身份系统：** Supervisor 根据任务类型为 Agent 穿上"专家外衣"：

| 专家 | 适用场景 |
|------|----------|
| CTO Router | 路由器，意图判定 |
| CPP_NETWORK_EXPERT | C++ 网络编程 |
| DB_EXPERT | 数据库 |
| QA_EXPERT | 测试 |
| GENERAL_CODER | 通用编码 |
| VISION_ARCHITECT_EXPERT | 视觉架构师（从 UML/架构图直接生成代码） |

> 动态专家 Persona：当预设专家不匹配时，Supervisor 会用 LLM 动态生成专家 Persona。

### 10.13 多智能体 Swarm

深度模式下启用多智能体协同，包含三种 Swarm 模式：

**1. 红蓝对抗（Red-Blue Swarm）：**
- **红军**：挑刺者，审查蓝军代码找问题
- **蓝军**：继承专家身份写码，根据红军反馈迭代

**2. SDD（Subagent-Driven Development）：**
- implementer：实现子 Agent
- spec 审查：规范审查子 Agent
- code-quality-reviewer：代码质量审查子 Agent

**3. P2P TCP 消息总线：**
- 多 Agent 间通过 P2P TCP 协议直接通信

### 10.14 时光倒流（Rewind）系统

Sandbox 内置时光倒流系统，采用 Git（肉体）+ SQLite（灵魂指针）混合架构，支持任务级和步骤级回退。

**支持的操作：**
- 任务级回退（rollback_task）
- 步骤级回退
- 检查点预览（preview_rollback）
- 查看检查点（view_checkpoint）
- 任务合并（merge_task）/ 撤销合并（revert_merged_task）

**持久化文件：**
- `.user_data/user_{id}/tasks/*.json`：任务元数据
- `.user_data/user_{id}/checkpoints/rewind.db`：回退指针 SQLite
- Git worktree 快照：每次工具调用后自动提交

### 10.15 代码图谱与语义检索

Sandbox 基于 Tree-sitter 多语言 AST 解析构建项目级代码图谱，提供深度语义检索能力。

**功能链路：**
```
Tree-sitter 多语言索引（Python/Java/C++）
        ▼
项目依赖图（project_grapher）
        ▼
社区聚类（graph_cluster）→ 变更影响传染分析（graph_diff）
        ▼
实时文件监听热更新（graph_watcher）
        ▼
向量语义搜索（semantic_search_tool，sentence-transformers + numpy）
```

**支持的检索类型：** symbol / definition / hierarchy / reference / outline / overview

**相关模块：**
- `tree_sitter_engine.py` / `tree_sitter_index.py`：AST 解析与索引
- `project_grapher.py`：依赖图谱构建
- `graph_diff.py`：变更影响分析
- `graph_cluster.py`：社区发现
- `graph_watcher.py`：实时热更新
- `graph_context_tool.py`：上下文剪裁
- `semantic_search_tool.py`：向量语义搜索
- `ast_tool.py`：AST 代码结构提取
- `.code_index.db`：代码索引 SQLite

### 10.16 代码导览（Tour）

基于项目依赖图自动生成代码讲解路径，用户发送 `/tour` 指令直达 `code_tour_guide`，Agent 按依赖顺序讲解代码模块。

### 10.17 LSP 集成

Sandbox 集成多种 LSP 语言服务器，提供 IDE 级代码智能能力（如 find_definition）：

| LSP | 语言 | 安装方式 | 环境变量 |
|-----|------|----------|----------|
| clangd | C/C++ | apt 安装 | - |
| JDTLS | Java | 下载至 /opt/jdtls | `JDTLS_HOME=/opt/jdtls` |
| pyright | Python | npm 全局安装 | - |
| typescript-language-server | TS/JS | npm 全局安装 | - |

**Java 运行时：** `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`

### 10.18 MCP 协议双角色

Sandbox 既是 MCP Server 又是 MCP Client：

- **MCP Server**（`mcp_server.py`）：将代码图谱 DB 封装为 MCP Server，供其他 MCP Client 调用
- **MCP Client**（`mcp_client.py`）：动态加载第三方 MCP Server 工具

**内置 MCP Server 配置（`mcp.json`）：** 见 10.8 节。

### 10.19 OS / 浏览器感知

Sandbox 具备操作系统级和浏览器级的感知与控制能力：

| 能力 | 模块 | 说明 |
|------|------|------|
| 浏览器自动化 | `browser_vision_tool.py` | Playwright 截图，让 Agent"看网页" |
| OS 键鼠控制 | `computer_use_tool.py` | pyautogui 键盘鼠标模拟 |
| 屏幕截图 | `screenshot_tool.py` | mss 截图 |
| PTY 交互终端 | `interactive_terminal.py` | `/ws/terminal` 终端 WebSocket |
| 交互式调试器 | `interactive_debugger_tool.py` | pexpect 接管 pdb |
| Notebook | `notebook_tool.py` | Jupyter Notebook 读取/编辑 |

### 10.20 进阶实验引擎

Sandbox 内置多个前沿实验性引擎（部分为研究性质）：

| 引擎 | 模块 | 说明 |
|------|------|------|
| 影子沙盒 | `shadow_sandbox.py` | CPU 分支预测式投机执行 |
| 忒修斯之船 | `theseus_rewrite.py` | AI 自我重写引擎 |
| 自我微调 | `self_distill.py` | 闭环自我微调 / RLHF |
| 算力自治 | `compute_autonomy.py` | 算力自治引擎 |
| 自我进化 | `meta_tool.py` | Agent 自动生成新工具 |
| 自动测试闭环 | `auto_test_tool.py` | Green Check 自动化测试 |

### 10.21 成本与预算治理

Sandbox 内置成本护栏，防止 LLM 调用超支：

| 机制 | 模块 | 默认值 | 说明 |
|------|------|--------|------|
| 会话成本上限 | `cost_guardrails.py` | 5 USD | SessionCostTracker，超限停止 |
| Token 预算 | `token_budget.py` | - | 单任务 Token 预算 |
| Prompt 缓存 | `prompt_caching.py` | - | 缓存 Prompt 降低成本 |

### 10.22 AIOS 事件总线与职业档案分析

Sandbox 通过 `event_bus.py`（pika）接入 AIOS 全局事件总线，发布 Agent 状态事件（thinking/idle）。

**护盾协程（_shielded_career_analysis）：** 任务结束后异步执行职业档案分析，通过 `rpc_entry.py`（protobuf RPC）上报 Java 中台（AI Service），更新用户职业档案。

**RPC 桥路径：** `RPC_BRIDGE_DIR=../protobuf-rpc-bridge/python`

### 10.23 完整 REST API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页 |
| `/ide` | GET | Web IDE 页面 |
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/execute` | POST | 同步执行任务 |
| `/api/v1/files` | GET | 文件列表 |
| `/api/v1/browse` | GET | 浏览目录 |
| `/api/v1/file` | GET | 读取文件 |
| `/api/v1/tasks` | GET/POST | 任务 CRUD |
| `/api/v1/semantic_search` | POST | 语义搜索 |

**完整 WebSocket 端点：**

| 端点 | 说明 |
|------|------|
| `/ws/coding` | 核心 Agent 双向通信（别名 `/ws/simple-ide`） |
| `/ws/coding/persistent` | 多任务长连接 |
| `/ws/terminal` | PTY 交互式终端 |

### 10.24 0-Token 系统指令

Sandbox 支持绕过大模型的 0-Token 系统指令（直接执行 Python），通过 `_handle_system_command` 拦截：

| 指令 | 说明 |
|------|------|
| `list_tasks` | 列出所有任务 |
| `rollback_task` | 回退任务 |
| `preview_rollback` | 预览回退 |
| `view_checkpoint` | 查看检查点 |
| `stop_agent` | 停止 Agent |
| `switch_task` | 切换任务 |
| `merge_task` | 合并任务 |
| `revert_merged_task` | 撤销合并 |
| `delete_task` | 删除任务 |
| `generate_graph` | 生成代码图谱 |
| `analyze_node` | 分析图谱节点 |

### 10.25 补充环境变量

除 10.10 节列出的环境变量外，Sandbox 还读取以下变量：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ERUITAH_USE_SUBPROCESS` | `true` | 是否用子进程隔离运行 Agent |
| `ERUITAH_VNC_PORT` | `5900` | VNC 端口 |
| `DISPLAY` | `:99` | X 显示号 |
| `JDTLS_HOME` | `/opt/jdtls` | Java LSP 路径 |
| `JAVA_HOME` | `/usr/lib/jvm/java-17-openjdk-amd64` | JDK 路径 |
| `PUPPETEER_EXECUTABLE_PATH` | `/usr/bin/chromium` | 浏览器可执行路径 |
| `RPC_BRIDGE_DIR` | `../protobuf-rpc-bridge/python` | Java 中台 RPC 桥路径 |
| `ERUITAH_MODEL_OPENAI` | `gpt-4o` | OpenAI 默认模型（本地默认值，Docker 中为 mimo-v2.5） |

> **注意：** `.env` 文件从**父目录**（`../.env`）加载（`main.py` 第 40 行），而非 Sandbox 目录本身。

### 10.26 运行时数据目录

Sandbox 运行时产生以下数据目录：

| 目录/文件 | 说明 |
|-----------|------|
| `.user_data/user_{id}/tasks/*.json` | 多租户任务元数据 |
| `.user_data/user_{id}/checkpoints/rewind.db` | 时光倒流指针 SQLite |
| `.eruitah_cache/sessions.db` | 会话存储 SQLite |
| `.code_index.db` | 代码索引 SQLite |
| `.theseus/shadow_*/` | 忒修斯之船影子重写快照 |
| `/tmp/eruitah-sandbox/` | Agent 工作根目录 |
| `/tmp/agent-worktrees/` | Git worktree 沙盒池 |

### 10.27 多租户会话隔离

`SessionManager`（`task_manager.py`）按 `user_id` 隔离会话，每个用户拥有独立的 worktree 沙盒。`GitSandboxManager v3`（`sandbox_manager.py`）维护 worktree WarmPool 预热池（默认 pool_size=3），加速任务创建。

### 10.28 示例子项目说明

Sandbox 根目录下包含三个示例子项目（Agent 工作区样例，非核心代码）：

| 目录 | 技术栈 | 说明 |
|------|--------|------|
| `cloud-storage/` | Node.js + Express | 网盘应用示例 |
| `spring-cloud-demo/` | Java Spring Cloud | 微服务示例（consumer/gateway/provider） |
| `threadpool-rs/` | Rust | 线程池库示例（Cargo） |

### 10.29 补充 Python 依赖

除 10.2 节列出的依赖外，requirements.txt 还包含：

| 依赖 | 说明 |
|------|------|
| `protobuf` | Protobuf 序列化（RPC 桥） |
| `tree-sitter` + `tree-sitter-python/java/cpp` | 多语言 AST 解析 |
| `pika` | RabbitMQ 客户端（AIOS 事件总线） |

### 10.30 兄弟项目依赖

Sandbox 依赖以下兄弟项目（位于同级目录）：

| 项目 | 路径 | 用途 |
|------|------|------|
| Coding Agent UI | `../coding-agent-ui` | Vue 前端，dist 挂载到 `/assets` 与 `/ide` |
| Protobuf RPC Bridge | `../protobuf-rpc-bridge/python` | Java 中台 RPC 桥（职业档案上报） |

---

## 11. Protobuf RPC Bridge 安装配置

Protobuf RPC Bridge 是跨语言通信的核心组件，使用 Protobuf 定义消息格式，通过 TCP 长连接实现 C++（ChatServer）、Java（AI Service）、Python（Sandbox）之间的 RPC 调用。

### 11.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| protoc | 3.x | Protobuf 编译器 |
| CMake | 3.10+ | C++ 构建工具 |
| GCC | 9+ | C++ 编译器（C++17） |
| muduo | - | 网络库（C++ RPC Bridge 依赖） |

### 11.2 安装 protoc

**Ubuntu/Debian：**

```bash
sudo apt-get install -y protobuf-compiler libprotobuf-dev
protoc --version
```

**CentOS/RHEL：**

```bash
sudo yum install -y protobuf-devel protobuf-compiler
```

**macOS：**

```bash
brew install protobuf
```

**手动安装（推荐，确保版本兼容）：**

```bash
# 下载 protoc
PROTOC_VERSION=25.3
curl -LO https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-x86_64.zip
unzip protoc-${PROTOC_VERSION}-linux-x86_64.zip -d /usr/local
protoc --version
```

### 11.3 生成 proto 代码

Proto 定义文件位于 `protobuf-rpc-bridge/proto/chat.proto`，包含聊天核心、群聊、伴读服务、考情大屏、PDF 解析、Sandbox 编程沙盒、Agent Swarm P2P 网络、C++ ↔ Java 内部路由等消息定义。

**生成 C++ 代码：**

```bash
cd /home/xmy/code/protobuf-rpc-bridge

# 生成 C++ pb.cc 和 pb.h
protoc --cpp_out=cpp/include proto/chat.proto
```

**生成 Python 代码：**

```bash
# 生成 Python 模块
protoc --python_out=python proto/chat.proto
```

**生成 Java 代码：**

Java 的 Protobuf 代码通过 Maven 插件在构建时自动生成，无需手动执行 protoc。`ai-service/pom.xml` 中已配置 `protobuf-maven-plugin`。

### 11.4 编译 C++ RPC 桥接

```bash
cd /home/xmy/code/protobuf-rpc-bridge/cpp

mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

编译产物：
- `build/bin/chat_server`：C++ RPC 桥接服务
- `build/bin/crosslang_test`：跨语言测试工具

**CMakeLists.txt 说明：**
- 依赖 `Protobuf` 和 `muduo` 库
- `MUDUO_INCLUDE_DIR` 和 `MUDUO_LIB_DIR` 默认为 `/usr/local/include` 和 `/usr/local/lib`
- 如果 muduo 安装在其他路径，需修改 `CMakeLists.txt` 中的路径

### 11.5 Python RPC 桥接

Python RPC 桥接依赖已包含在 `eruitah-sandbox/requirements.txt` 中：

```
protobuf>=4.21.0
httpx>=0.25.0
websockets>=12.0
```

无需单独安装，安装 Sandbox 依赖时自动安装。

### 11.6 Java RPC 桥接

Java RPC 桥接依赖已包含在 `ai-service/pom.xml` 中，通过 `protobuf-maven-plugin` 自动编译 proto 文件并生成 Java 类。

### 11.7 Docker 部署

Protobuf RPC Bridge 提供独立的 Dockerfile（`protobuf-rpc-bridge/Dockerfile`），构建 Java 版本的 RPC Bridge：

```bash
cd /home/xmy/code/protobuf-rpc-bridge
docker build -t protobuf-rpc-bridge:1.0.0 .
```

**注意：** 在 Docker Compose 部署中，RPC 通信通过各服务间的内部端口实现，无需单独部署 RPC Bridge 容器：
- AI Service 暴露 9999 端口（`RPC_INTERNAL_PORT`），供 ChatServer 和 Sandbox 调用
- ChatServer 暴露 8888 端口（`RPC_CPP_PORT`），供 AI Service 回调
- Sandbox 暴露 9997 端口（`RPC_PYTHON_PORT`），供 AI Service 调用

---

## 12. Coding Agent UI 安装配置

Coding Agent UI 是基于 Vue 3 + Vite 的 Web IDE 前端，提供代码编辑器（Monaco Editor）和终端（xterm.js）功能。

### 12.1 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Node.js | 18+ | 运行和构建环境 |
| npm | 9+ | 包管理器 |

### 12.2 安装依赖

```bash
cd /home/xmy/code/coding-agent-ui
npm install
```

**主要依赖：**
- `vue` 3.4+：前端框架
- `monaco-editor` 0.45+：代码编辑器
- `@xterm/xterm` 5.5+：终端模拟器
- `@guolao/vue-monaco-editor`：Vue Monaco Editor 封装
- `mermaid`：图表渲染
- `pinia`：状态管理
- `tailwindcss`：CSS 框架

### 12.3 开发模式

```bash
cd /home/xmy/code/coding-agent-ui
npm run dev
```

开发服务器启动后，访问 http://localhost:5173。

**Vite 代理配置**（`vite.config.js`）：

开发模式下，以下路径会代理到本地 Sandbox 服务（`http://127.0.0.1:8001`）：

| 路径 | 代理目标 | 说明 |
|------|----------|------|
| `/ws/simple-ide` | `ws://127.0.0.1:8001/ws/coding` | 简化 IDE WebSocket |
| `/ws/coding` | `ws://127.0.0.1:8001/ws/coding` | 编码 WebSocket |
| `/ws/terminal` | `ws://127.0.0.1:8001/ws/terminal` | 终端 WebSocket |
| `/api` | `http://127.0.0.1:8001/api` | REST API |

### 12.4 构建生产版本

```bash
cd /home/xmy/code/coding-agent-ui
npm run build
```

构建产物输出到 `dist/` 目录。

**注意：** `dist/` 目录会被 Sandbox 服务挂载使用。在 Docker Compose 部署中，通过卷挂载 `./coding-agent-ui/dist:/app/coding-agent-ui/dist:ro` 提供给 Sandbox 容器。因此需要先构建 Coding Agent UI，再启动 Sandbox 服务。

### 12.5 预览构建结果

```bash
cd /home/xmy/code/coding-agent-ui
npm run preview
```

---

## 13. Nginx 反向代理配置

Nginx 作为系统的统一入口，负责 TCP 代理、HTTP 反向代理和 WebSocket 代理。配置文件位于 `docker/nginx/nginx.conf`。

### 13.1 TCP 代理（Qt 客户端连接）

```nginx
stream {
    upstream chat_backend {
        server chatserver:6000 weight=1 max_fails=3 fail_timeout=30s;
    }

    server {
        listen 8000;
        proxy_connect_timeout 5s;
        proxy_timeout 300s;
        proxy_pass chat_backend;
        tcp_nodelay on;
    }
}
```

- 外部端口 **8000** 代理到 ChatServer **6000**
- Qt 客户端通过 `host:8000` 连接，Nginx 转发到 ChatServer

### 13.2 HTTP 代理（AI Service + Sandbox）

```nginx
http {
    upstream ai_backend {
        server ai-service:8081;
    }

    upstream sandbox_backend {
        server sandbox:8001;
    }
}
```

**路由规则：**

| 路径 | 代理目标 | 说明 |
|------|----------|------|
| `/api/` | ai-service:8081 | AI Service REST API |
| `/audio/` | ai-service:8081 | 音频文件访问 |
| `/api/v1/` | sandbox:8001 | Sandbox REST API |
| `/sandbox/` | sandbox:8001 | Sandbox 通用代理 |
| `/ide` | sandbox:8001 | Web IDE 页面 |
| `/assets/` | sandbox:8001 | 静态资源（缓存30天） |

### 13.3 WebSocket 代理

```nginx
# AI Service WebSocket
location /ws/ai/ {
    proxy_pass http://ai_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /ws/voice/ {
    proxy_pass http://ai_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /ws/ {
    proxy_pass http://ai_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

# Sandbox WebSocket
location /sandbox/ws/coding {
    proxy_pass http://sandbox_backend/ws/coding;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /sandbox/ws/terminal {
    proxy_pass http://sandbox_backend/ws/terminal;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

**WebSocket 路由说明：**

| 路径 | 代理目标 | 说明 |
|------|----------|------|
| `/ws/ai/` | ai-service:8081 | AI 实时对话 |
| `/ws/voice/` | ai-service:8081 | 实时语音 |
| `/ws/` | ai-service:8081 | 通用 WebSocket |
| `/sandbox/ws/coding` | sandbox:8001 | 编码 Agent WebSocket |
| `/sandbox/ws/terminal` | sandbox:8001 | 终端 WebSocket |

### 13.4 其他配置

- `client_max_body_size 50m`：最大上传 50MB（与 AI Service 配置一致）
- `proxy_read_timeout 300s`：HTTP 代理超时 5 分钟
- `proxy_read_timeout 3600s`：WebSocket 代理超时 1 小时
- `map $http_upgrade $connection_upgrade`：WebSocket 连接升级映射

---

## 14. .env 环境变量详解

在项目根目录创建 `.env` 文件，Docker Compose 会自动读取。所有变量均支持默认值（`:-` 后的值），未配置时使用默认值。

### 14.1 数据库

```bash
# MySQL
MYSQL_ROOT_PASSWORD=xieming562          # MySQL root 密码

# Redis
REDIS_PASSWORD=123456                   # Redis 密码

# Neo4j
NEO4J_PASSWORD=12345678                 # Neo4j 密码
```

### 14.2 OpenAI 兼容接口（AI Service 主模型）

```bash
# OpenAI 兼容 API（默认使用 DashScope）
OPENAI_API_KEY=                         # DashScope API Key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode
OPENAI_MODEL=qwen3.5-plus              # 主对话模型
```

### 14.3 Anthropic（Sandbox 可选）

```bash
ANTHROPIC_API_KEY=                      # Anthropic API Key
```

### 14.4 多模态

```bash
MULTIMODAL_API_KEY=                     # 多模态 API Key（通常与 OPENAI_API_KEY 相同）
MULTIMODAL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode
MULTIMODAL_MODEL=qwen3.5-omni-flash-2026-03-15
```

### 14.5 向量嵌入

```bash
EMBEDDING_API_KEY=                      # SiliconFlow API Key
EMBEDDING_BASE_URL=https://api.siliconflow.cn
EMBEDDING_MODEL=BAAI/bge-m3
```

### 14.6 重排序

```bash
RERANKER_API_KEY=                       # SiliconFlow API Key（通常与 EMBEDDING_API_KEY 相同）
RERANKER_BASE_URL=https://api.siliconflow.cn
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

### 14.7 联网搜索

```bash
SERPER_API_KEY=                         # Serper API Key
SERPER_BASE_URL=https://google.serper.dev
```

### 14.8 语音

```bash
# 阿里云 ASR + 实时 TTS
ALI_ASR_API_KEY=your-dashscope-api-key
ALI_ASR_MODEL=fun-asr-realtime-2026-02-28
ALI_REALTIME_TTS_MODEL=qwen3-tts-instruct-flash-realtime
ALI_REALTIME_TTS_VOICE=Cherry

# 小米 TTS（可选，第二引擎）
XIAOMI_TTS_API_KEY=your-xiaomi-tts-api-key
XIAOMI_TTS_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
XIAOMI_TTS_MODEL=mimo-v2.5-tts
XIAOMI_TTS_VOICE=冰糖
```

### 14.9 Sandbox

```bash
ERUITAH_API_PROVIDER=openai             # API 提供商（openai/anthropic）
ERUITAH_MODEL_OPENAI=mimo-v2.5          # OpenAI 兼容模型
ERUITAH_MODEL_ANTHROPIC=claude-sonnet-4-20250514  # Anthropic 模型
ERUITAH_ENABLE_VNC=false                # 是否启用 VNC 远程桌面
ERUITAH_SCREEN_WIDTH=1280               # 虚拟桌面宽度
ERUITAH_SCREEN_HEIGHT=720               # 虚拟桌面高度
```

### 14.10 完整 .env 模板

```bash
# ===== 数据库 =====
MYSQL_ROOT_PASSWORD=xieming562
REDIS_PASSWORD=123456
NEO4J_PASSWORD=12345678

# ===== OpenAI 兼容接口 =====
OPENAI_API_KEY=your-dashscope-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode
OPENAI_MODEL=qwen3.5-plus

# ===== Anthropic =====
ANTHROPIC_API_KEY=

# ===== 多模态 =====
MULTIMODAL_API_KEY=your-dashscope-api-key
MULTIMODAL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode
MULTIMODAL_MODEL=qwen3.5-omni-flash-2026-03-15

# ===== 向量嵌入 =====
EMBEDDING_API_KEY=your-siliconflow-api-key
EMBEDDING_BASE_URL=https://api.siliconflow.cn
EMBEDDING_MODEL=BAAI/bge-m3

# ===== 重排序 =====
RERANKER_API_KEY=your-siliconflow-api-key
RERANKER_BASE_URL=https://api.siliconflow.cn
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# ===== 联网搜索 =====
SERPER_API_KEY=your-serper-api-key
SERPER_BASE_URL=https://google.serper.dev

# ===== 语音（阿里云 ASR + 双 TTS 引擎） =====
ALI_ASR_API_KEY=your-dashscope-api-key
ALI_ASR_MODEL=fun-asr-realtime-2026-02-28
ALI_REALTIME_TTS_MODEL=qwen3-tts-instruct-flash-realtime
ALI_REALTIME_TTS_VOICE=Cherry
XIAOMI_TTS_API_KEY=your-xiaomi-tts-api-key
XIAOMI_TTS_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
XIAOMI_TTS_MODEL=mimo-v2.5-tts
XIAOMI_TTS_VOICE=冰糖

# ===== Sandbox =====
ERUITAH_API_PROVIDER=openai
ERUITAH_MODEL_OPENAI=mimo-v2.5
ERUITAH_MODEL_ANTHROPIC=claude-sonnet-4-20250514
ERUITAH_ENABLE_VNC=false
ERUITAH_SCREEN_WIDTH=1280
ERUITAH_SCREEN_HEIGHT=720
```

---

## 15. 完整部署架构

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              部署架构图                                           │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                       │
│   │ QtChat      │     │ QtChat      │     │ Web Client  │                       │
│   │ (Linux)     │     │ (Windows)   │     │ (Browser)   │                       │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                       │
│          │                   │                   │                               │
│          │ TCP:8000          │                   │ HTTP:80 / WS:80               │
│          └───────────────────┼───────────────────┘                               │
│                              │                                                   │
│                              ▼                                                   │
│                    ┌─────────────────┐                                           │
│                    │     Nginx       │                                           │
│                    │  :80 (HTTP/WS)  │                                           │
│                    │  :8000 (TCP)    │                                           │
│                    └────────┬────────┘                                           │
│                             │                                                    │
│          ┌──────────────────┼──────────────────────┬──────────────────┐          │
│          │                  │                      │                  │          │
│          │ TCP:6000         │ HTTP:8081            │ HTTP:8001        │ HTTP:8002│
│          ▼                  ▼                      ▼                  ▼          │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  ┌──────────────┐  │
│   │ ChatServer  │    │  AI Service │    │  Eruitah        │  │  Butcanthic  │  │
│   │ (C++ muduo) │    │  (Java)     │    │  Sandbox        │  │  (Python)    │  │
│   │ :6000 TCP   │◄──►│  :8081 HTTP │    │  (Python)       │  │  :8002 HTTP  │  │
│   │ :8888 RPC   │    │  :9999 RPC  │◄──►│  :8001 HTTP/WS  │  │  LangGraph   │  │
│   └──────┬──────┘    └──────┬──────┘    │  :5900 VNC      │  │  ChromaDB    │  │
│          │                  │           └────────┬────────┘  └──────┬───────┘  │
│          │                  │                    │                  │           │
│     ┌────┴────┐       ┌────┴────┐          ┌────┴────┐      ┌─────┴─────┐     │
│     │         │       │         │          │         │      │           │     │
│     ▼         ▼       ▼         ▼          ▼         ▼      ▼           ▼     │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│  │MySQL │ │Redis │ │Neo4j │ │Redis │  │ LLM  │ │ LLM  │ │ LLM  │ │ LLM  │   │
│  │:3306 │ │:6379 │ │:7687 │ │Stack │  │OpenAI│ │Anthr.│ │Qwen  │ │Doubao│   │
│  └──────┘ └──────┘ └──────┘ └──────┘  └──────┘ └──────┘ └──────┘ └──────┘   │
│                                                                                  │
│  Protobuf RPC Bridge: C++(:8888) ◄──► Java(:9999) ◄──► Python(:9997)           │
│                                                                                  │
│  Butcanthic: FastAPI(:8002) + LangGraph + ChromaDB + Celery + Redis             │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 16. 依赖版本汇总

### Java AI 服务

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

### C++ 服务器端

| 依赖 | 版本 | 说明 |
|------|------|------|
| muduo | master | 陈硕网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |
| nlohmann/json | 3.x | JSON解析 |

### C++ 客户端

| 依赖 | 版本 | 说明 |
|------|------|------|
| Qt | 5.12+ | GUI框架 |
| muduo | master | 网络库 |
| hiredis | 1.0+ | Redis C客户端 |
| mysqlclient | 8.0+ | MySQL C客户端 |

### Eruitah 智能编程沙盒

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 运行时环境 |
| FastAPI | 0.104+ | Web框架 |
| uvicorn | 0.24+ | ASGI服务器 |
| openai | 1.6+ | OpenAI SDK |
| anthropic | 0.39+ | Anthropic SDK |
| pydantic | 2.5+ | 数据验证 |
| websockets | 12.0+ | WebSocket支持 |
| sentence-transformers | 2.2+ | 本地向量嵌入 |
| numpy | 1.24+ | 数值计算 |
| playwright | 1.40+ | 浏览器自动化 |
| pexpect | 4.8+ | 交互式进程管理 |
| pyautogui | 0.9.54+ | GUI自动化 |
| mss | 9.0+ | 屏幕截图 |
| ripgrep | - | 可选，代码搜索加速 |

### Butcanthic 文档智能服务

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 运行时环境（LangGraph 需要） |
| FastAPI | 0.115+ | Web框架 |
| uvicorn | 0.34+ | ASGI服务器 |
| langchain | 0.3+ | LLM编排框架 |
| langchain-openai | 0.3+ | OpenAI兼容接口 |
| langgraph | 0.2+ | 多Agent工作流引擎 |
| chromadb | 0.5+ | 嵌入式向量数据库 |
| rank-bm25 | 0.2.2+ | BM25稀疏检索 |
| jieba | 0.42+ | 中文分词 |
| openai | 1.60+ | OpenAI SDK |
| python-docx | 1.1+ | Word文档解析 |
| python-pptx | 1.0+ | PPT文档解析 |
| openpyxl | 3.1+ | Excel文档解析 |
| pypdf | 6.0+ | PDF文档解析 |
| celery | 5.4+ | 异步任务队列 |
| redis | 5.2+ | Celery Broker |
| PyJWT | 2.8+ | JWT鉴权 |
| sqlalchemy | 2.0+ | 元数据数据库ORM |
| networkx | 3.2+ | 知识图谱 |
| ddgs | 6.0+ | 联网搜索（DuckDuckGo） |

### Butcanthic Frontend

| 依赖 | 版本 | 说明 |
|------|------|------|
| Node.js | 18+ | 运行和构建环境 |
| React | 18.3+ | UI框架 |
| Vite | 6.0+ | 构建工具 |
| ECharts | 6.1+ | 图表可视化 |
| echarts-for-react | 3.0+ | React ECharts封装 |

### Protobuf RPC Bridge

| 依赖 | 版本 | 说明 |
|------|------|------|
| protobuf | 3.x / 4.21+ | 消息定义与序列化 |
| CMake | 3.10+ | C++ 构建工具 |
| muduo | master | C++ RPC 网络层 |

### Coding Agent UI

| 依赖 | 版本 | 说明 |
|------|------|------|
| Node.js | 18+ | 运行和构建环境 |
| Vue | 3.4+ | 前端框架 |
| Vite | 5.4+ | 构建工具 |
| Monaco Editor | 0.45+ | 代码编辑器 |
| xterm.js | 5.5+ | 终端模拟器 |
| Tailwind CSS | 3.4+ | CSS框架 |

---

## 17. 快速验证清单

### Java AI 服务

```bash
# 健康检查
curl http://localhost:8081/api/ai/health

# 基础聊天
curl -X POST http://localhost:8081/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "botId":10000, "message":"你好"}'

# 语音服务健康检查
curl http://localhost:8081/api/voice/health

# 农场服务健康检查
curl http://localhost:8081/api/farm/health

# RAG文档上传
curl -X POST http://localhost:8081/api/rag/upload \
  -F "file=@test.txt"

# 知识图谱（需先有数据）
curl http://localhost:8081/api/graph/user/1/tree

# 考情大屏
curl http://localhost:8081/api/analysis/dashboard/1

# 考情大屏页面
curl http://localhost:8081/dashboard.html?userId=1

# 多智能体工作流
curl -X POST http://localhost:8081/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "message":"请解释一下TCP三次握手"}'

# MCP文件系统工具验证（代码审查员）
curl -X POST http://localhost:8081/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"userId":1, "botId":10003, "message":"帮我看看这段代码有没有问题"}'

# 流式聊天
curl -N "http://localhost:8081/api/ai/stream-chat?message=你好&sessionId=test_session"

# Redis连接验证
redis-cli -a 123456 ping
```

### C++ 服务器

```bash
# 检查服务状态（ChatServer 直接端口）
netstat -tlnp | grep 6000

# 检查 Nginx TCP 代理
netstat -tlnp | grep 8000

# 查看日志
tail -f chatserver.log
```

### C++ 客户端

```bash
# 启动客户端
./bin/QtChat

# 或命令行版本
./bin/ChatClient
```

### Eruitah 智能编程沙盒

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

### Butcanthic 文档智能服务

```bash
# 健康检查
curl http://localhost:8002/api/v1/health

# 文档处理测试
curl -X POST http://localhost:8002/api/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"user_instruction": "帮我总结一下数据结构的知识点"}'

# 知识库上传测试
curl -X POST http://localhost:8002/api/v1/knowledge/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@test.pdf"

# PPT生成测试
curl -X POST http://localhost:8002/api/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"user_instruction": "帮我生成一个关于操作系统的PPT"}'
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

### Nginx 代理验证

```bash
# HTTP 代理（AI Service）
curl http://localhost/api/ai/health

# HTTP 代理（Sandbox）
curl http://localhost/api/v1/health

# TCP 代理（ChatServer，需 Qt 客户端连接 localhost:8000）
```

---

## 18. 常见问题（C++端）

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
1. 确认服务器已启动：`netstat -tlnp | grep 6000`（直连）或 `netstat -tlnp | grep 8000`（Nginx代理）
2. 检查防火墙：`sudo ufw allow 8000`
3. 确认客户端配置的服务器地址和端口正确
4. 如果通过 Nginx 代理，确认 Nginx 容器正常运行：`docker-compose ps nginx`

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
4. Docker 部署时检查环境变量 `MYSQL_HOST`、`MYSQL_PASSWORD` 是否正确

### Q19：Redis连接失败

**排查步骤：**
1. 确认Redis服务已启动：`redis-cli ping`
2. 检查密码是否正确（修改 `src/server/redis/redis.cpp`）
3. 确认hiredis库已安装
4. Docker 部署时检查环境变量 `REDIS_HOST`、`REDIS_PASSWORD` 是否正确

---

## 19. 常见问题（Eruitah沙盒）

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
4. 如果通过 Nginx 代理，测试：`wscat -c ws://localhost/sandbox/ws/coding`

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

### Q26：VNC 无法连接

**排查步骤：**
1. 确认 `ERUITAH_ENABLE_VNC=true` 已设置
2. 检查 5900 端口是否开放：`netstat -tlnp | grep 5900`
3. 确认 x11vnc 进程是否运行：`docker exec chat-sandbox ps aux | grep x11vnc`
4. 检查 Xvfb 是否正常启动：`docker exec chat-sandbox ps aux | grep Xvfb`

### Q27：LSP 语言服务器不工作

**排查步骤：**
1. 确认 LSP 工具已安装：`docker exec chat-sandbox which clangd`
2. 检查 JDTLS：`docker exec chat-sandbox ls /opt/jdtls/`
3. 检查 pyright：`docker exec chat-sandbox which pyright`
4. 查看 Sandbox 日志中的 LSP 启动信息

### Q28：MCP Server 启动失败

**排查步骤：**
1. 确认 Node.js 已安装：`docker exec chat-sandbox node --version`
2. 检查 MCP Server 包是否已安装：`docker exec chat-sandbox npm list -g`
3. 查看 `mcp.json` 配置是否正确
4. 手动测试 MCP Server：`npx -y @modelcontextprotocol/server-filesystem /tmp`

---

## 20. 常见问题（Butcanthic 文档智能服务）

### Q29：Butcanthic 启动报错 "No module named 'langgraph'"

**排查步骤：**
1. 确认 Python 版本：`python3 --version`（需 3.11+）
2. 确认虚拟环境已激活：`which python`
3. 重新安装依赖：`pip install -r requirements.txt`
4. 如果仍然失败，单独安装：`pip install langgraph>=0.2.0`

### Q30：RAG 引擎初始化失败 "ChromaDB error"

**排查步骤：**
1. 确认 `chromadb` 已安装：`pip show chromadb`
2. 检查 `chroma_db/` 目录是否有写入权限
3. 删除损坏的数据库重建：`rm -rf chroma_db/`
4. 确认嵌入模型 API Key 有效

### Q31：文档处理返回空结果

**排查步骤：**
1. 确认 `ai_models_config.json` 中 API Key 已配置
2. 检查 LLM Client 是否初始化成功（查看启动日志）
3. 确认上传的文件格式受支持（docx/xlsx/pptx/pdf）
4. 检查文件大小是否超过 50MB 限制

### Q32：PPT 生成质量不佳

**排查步骤：**
1. 确认使用的 LLM 模型能力足够（推荐 qwen-plus 或更强模型）
2. 提供更详细的用户指令，包含主题、页数、风格等要求
3. 检查 `critic_review_ppt` 节点是否正常工作（最多自动重试3次）
4. 确认知识库中是否有相关领域的数据

### Q33：Celery Worker 无法连接 Redis

**排查步骤：**
1. 确认 Redis 服务已启动：`redis-cli -a 123456 ping`
2. 检查 Butcanthic `.env` 中 Redis 连接配置
3. 确认 Celery Broker URL 配置正确
4. 如果不使用异步任务，设置 `USE_CELERY=false`

### Q34：知识库上传后检索不到内容

**排查步骤：**
1. 确认嵌入模型 API Key 有效（SiliconFlow）
2. 检查 ChromaDB 中是否存在对应用户的 Collection：`kb_user_{user_id}`
3. 确认文档解析成功（查看日志中的分块信息）
4. BM25 索引需要重建，重启服务后生效

### Q35：Butcanthic Frontend 构建失败

**排查步骤：**
1. 确认 Node.js 版本：`node --version`（需 18+）
2. 删除 `node_modules` 重新安装：`rm -rf node_modules && npm install`
3. 检查 `vite.config.ts` 中的代理配置是否正确
4. 确认 TypeScript 编译无错误：`npx tsc --noEmit`

### Q36：Excel 数据清洗自我纠错失败

**排查步骤：**
1. 检查生成的 Python 代码是否语法正确
2. 确认 `pandas` 和 `openpyxl` 已安装
3. 查看 `code_execution_error` 日志了解具体错误
4. Data Agent 最多自我纠错3次，复杂表格可能需要人工干预
