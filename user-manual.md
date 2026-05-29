# 智能聊天应用系统 用户手册

## 1. 项目简介

智能聊天应用系统是一个面向 **408计算机考研** 的多语言微服务系统，包含以下五大子系统：

| 子系统 | 技术栈 | 核心职责 |
|--------|--------|----------|
| **C++/Qt 桌面客户端** | C++17 + Qt 5 + muduo + Material Design | 即时通讯客户端，聊天/群聊/农场/知识图谱/语音 |
| **Java AI 后端** | Spring Boot 3.2 + Spring AI + Neo4j + Redis | AI角色、RAG知识库、知识图谱、语音交互、多智能体编排 |
| **Python 编程沙盒** | FastAPI + WebSocket + Agent Loop | AI编程助手、代码编辑/执行/回退、多智能体协同 |
| **Python 文档智能服务** | FastAPI + LangGraph + ChromaDB + Celery | 文档自动填充、PPT生成、知识库RAG、多Agent工作流 |
| **Vue Web IDE** | Vue 3 + Vite + Pinia + Monaco + xterm.js | 浏览器端编程界面、代码编辑、终端、文件树 |

### 核心特性

- **多角色AI聊天**：10个不同性格的AI角色，覆盖考研辅导、代码审查、面试模拟等场景
- **RAG知识库**：支持文档上传、向量检索、混合检索+重排序，确保回答有据可依
- **多智能体编排**：Router → Solver → Reflection 三阶段流水线，自动根据意图选择最优策略
- **语音交互**：ASR语音识别 + TTS语音合成，支持实时WebSocket语音对话
- **知识图谱**：基于Neo4j的认知图谱，追踪学习掌握度，智能推荐薄弱考点
- **智能出题与判卷**：基于知识库和图谱自动出题，AI严格判卷并更新掌握度
- **群聊多智能体**：面试群组智能路由，多位面试官协作追问
- **伴读功能**：划选文本即可获得语音+文字讲解
- **考情大屏**：雷达图、活跃度、周报等学习数据分析
- **AI编程沙盒**：Eruitah 智能编程助手，支持代码编写/执行/回退/多智能体协同
- **跨语言 RPC**：C++ ↔ Java ↔ Python 三语言 Protobuf RPC 通信
- **一键部署**：Docker Compose 编排 8 个服务，Nginx 反向代理统一入口
- **文档智能处理**：Butcanthic 文档智能服务，支持 Word/Excel/PPT 自动填充、PPT 生成、知识库 RAG 检索
- **LangGraph 多Agent工作流**：16个节点条件路由，自我纠错循环，Critic 审查机制
- **双TTS语音引擎**：阿里云实时TTS + 小米TTS，自动故障切换

---

## 2. AI角色一览

系统内置10个AI角色，每个角色拥有独特的性格、知识范围和回答风格：

| 角色ID | 角色名称 | 核心定位 | RAG | 工具 | 回复字数 |
|--------|----------|----------|-----|------|----------|
| 10000 | 旗舰大师 | 408考研终极辅导专家，四科全覆盖 | ✅ | ✅ | ≤300字 |
| 10001 | 严厉导师 | 严厉一丝不苟，反问式引导 | ✅ | ❌ | ≤150字 |
| 10002 | 温柔学长 | 生活化类比，耐心鼓励 | ❌ | ❌ | ≤150字 |
| 10003 | 代码审查员 | 高冷极客，审查Bug和性能 | ❌ | ✅ | ≤100字 |
| 10004 | 严厉大Boss | 底层原理面试官（OS/计网） | ✅ | ❌ | ≤200字 |
| 10005 | 慈祥老教授 | 项目经验面试官（软技能） | ❌ | ❌ | ≤200字 |
| 10006 | 挑刺狂魔 | 算法代码面试官（DS/算法） | ❌ | ✅ | ≤200字 |
| 10007 | 解题大王 | 多模态视觉解题，支持图片 | ✅ | ❌ | ≤400字 |
| 10008 | 语音小助手 | 语音对话，简洁友好 | ❌ | ❌ | ≤100字 |
| 10009 | 心理委员 | 心理疏导，温暖陪伴 | ❌ | ❌ | ≤80字 |

### 角色权限说明

- **RAG权限**（hasRag）：角色可访问知识库检索结果，回答更有依据
- **工具权限**（hasTools）：角色可调用C++编译器或联网搜索等工具
- **旗舰大师**拥有最高权限，使用多智能体编排（Router → Solver → Reflection），自动挂载RAG和工具
- **代码审查员**额外挂载MCP文件系统工具（read_file/list_directory/search_files），可直接读取和搜索代码文件
- **解题大王**使用独立的多模态ChatClient（qwen3.5-omni-flash），支持图片识别和视觉解题
- **语音小助手**和**心理委员**支持语音交互，其中心理委员支持实时WebSocket语音对话

---

## 3. API接口详解

### 3.1 AI聊天接口

#### 1v1聊天

```
POST /api/ai/chat
```

**请求体：**

```json
{
  "userId": 1,
  "botId": 10000,
  "message": "请解释一下TCP三次握手",
  "images": [
    {
      "base64": "data:image/png;base64,...",
      "mimeType": "image/png"
    }
  ]
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userId | Integer | 是 | 用户ID |
| botId | Integer | 否 | AI角色ID，默认10000（旗舰大师） |
| message | String | 是 | 用户消息内容 |
| images | List | 否 | 图片列表（仅解题大王10007支持） |

**响应体：**

```json
{
  "message": "TCP三次握手是...",
  "success": true,
  "error": null,
  "sessionId": "chat_1_10000"
}
```

**限流规则：** 每用户30次/分钟，每IP 60次/分钟

#### 流式聊天

```
GET /api/ai/stream-chat?message=请解释TCP三次握手&sessionId=chat_1_10000
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | String | 是 | 用户消息 |
| sessionId | String | 否 | 会话ID |

**响应：** `text/plain` 流式输出，首行包含 `[SESSION:xxx]` 会话标识

#### 清除会话

```
DELETE /api/ai/session/{sessionId}
```

#### 健康检查

```
GET /api/ai/health
```

---

### 3.2 思维导图

```
POST /api/ai/mindmap
```

**请求体：**

```json
{
  "userId": 1,
  "topic": "操作系统"
}
```

**响应：** 返回Mermaid格式的思维导图代码

**限流规则：** 每用户10次/分钟，每IP 20次/分钟

---

### 3.3 伴读功能

```
POST /api/ai/companion-read
```

**请求体：**

```json
{
  "userId": 1,
  "text": "虚拟内存是将程序的一部分装入内存，其余部分留在外存..."
}
```

**响应体：**

```json
{
  "audioUrl": "http://localhost:8081/audio/ai_xxx.wav",
  "explanationText": "同学你好~虚拟内存就像你的书桌...",
  "success": true,
  "error": null
}
```

**限流规则：** 每用户20次/分钟，每IP 40次/分钟

---

### 3.4 PDF解析

```
POST /api/ai/parse-pdf
```

**请求：** `multipart/form-data`，字段 `file` 为PDF文件

**响应体：**

```json
{
  "text": "PDF提取的文本内容...",
  "filename": "example.pdf"
}
```

---

### 3.5 RAG知识库

#### 上传文档

```
POST /api/rag/upload
```

**请求：** `multipart/form-data`，字段 `file` 为文档文件

**支持格式：** `.txt`、`.pdf`

**响应体：**

```json
{
  "success": true,
  "message": "知识库文档上传并索引成功",
  "filename": "数据结构笔记.pdf",
  "chunkCount": 42
}
```

**限流规则：** 每用户10次/分钟，每IP 20次/分钟

**说明：**
- PDF文件优先使用 `PagePdfDocumentReader` 提取文本
- 如果是扫描版PDF，自动调用 `pdftoppm` + `tesseract` 进行OCR识别
- 文档会被自动切分为多个Chunk，写入Redis向量存储

---

### 3.6 多智能体工作流

```
POST /api/agent/chat
```

**请求体：**

```json
{
  "userId": 1,
  "message": "帮我刷一道数据结构的题"
}
```

**响应体：**

```json
{
  "success": true,
  "intent": "技能:出题",
  "draftAnswer": "...",
  "finalAnswer": "🎴 智能抽卡 — 408考研挑战卡\n\n【数据结构】\n\n..."
}
```

**工作流说明：**

1. **出题意图检测**：消息包含"刷题""考考我""出题"等关键词时触发
2. **意图路由**：Router AI识别为"代码求助""理论解答"或"日常闲聊"
3. **代码求助**：挂载C++编译器工具，可编译验证代码
4. **理论解答**：挂载RAG知识库 + 联网搜索，混合检索+重排序
5. **日常闲聊**：纯Prompt聊天

**限流规则：** 每用户20次/分钟，每IP 40次/分钟

---

### 3.7 群聊接口

#### 接收群消息

```
POST /api/group/message
```

**请求体：**

```json
{
  "groupId": 1001,
  "senderId": 1,
  "content": "@旗舰大师 请解释一下进程和线程的区别",
  "aiBotIds": [10000, 10001, 10002]
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| groupId | Long | 是 | 群组ID |
| senderId | Integer | 是 | 发送者ID |
| content | String | 是 | 消息内容 |
| aiBotIds | List\<Integer\> | 否 | 群内AI角色ID列表 |

**群聊路由逻辑：**

1. **摘要请求**：消息包含 `@AI 总结一下群里聊了什么` 时，触发群聊摘要
2. **显式路由**：消息包含 `@角色名` 时，仅被@的AI回复
3. **智能路由**：面试群组（含10004/10005/10006）由Router AI决定哪个面试官回复
4. **默认路由**：所有AI角色并发回复

#### 生成群聊摘要

```
POST /api/group/summary?groupId=1001&messageCount=100
```

#### 提交摘要任务（异步）

```
POST /api/group/task?groupId=1001&replyTo=1&replyToName=张三
```

#### 获取群聊信息

```
GET /api/group/info?groupId=1001
```

#### 清除群聊记录

```
DELETE /api/group/messages?groupId=1001
```

---

### 3.8 语音接口

#### 上传语音

```
POST /api/voice/upload
```

**请求：** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| audio | MultipartFile | 是 | 音频文件（WAV格式） |
| userId | Integer | 是 | 发送者ID |
| toId | Integer | 是 | 接收者ID |
| duration | Integer | 是 | 音频时长（秒） |

**响应体：**

```json
{
  "success": true,
  "url": "http://localhost:8081/audio/xxx.wav",
  "fileName": "xxx.wav",
  "duration": 5
}
```

#### 语音聊天

```
POST /api/voice/chat
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| audioUrl | String | 是 | 音频文件URL |
| userId | Integer | 是 | 用户ID |
| botId | Integer | 是 | AI角色ID |
| duration | Integer | 否 | 音频时长（秒） |

**响应体：**

```json
{
  "success": true,
  "textReply": "TCP三次握手是...",
  "voiceUrl": "http://localhost:8081/audio/ai_xxx.wav",
  "duration": 12
}
```

**处理流程：** 下载音频 → ASR语音识别（阿里云） → LLM生成回复 → TTS语音合成（阿里云/小米双引擎，自动故障切换） → 返回文字+语音

---

### 3.9 实时语音WebSocket

```
WS /ws/realtime-voice
```

**连接后交互协议：**

#### 开始会话

```json
{"action": "start", "userId": 1, "botId": 10009}
```

服务端响应：

```json
{"type": "session_started", "userId": 1, "botId": 10009, "botName": "心理委员"}
```

#### 发送音频

客户端发送二进制帧（PCM 16kHz 16bit 单声道）

服务端响应：

```json
{"type": "asr_result", "text": "你好", "isEnd": false}
```

```json
{"type": "asr_result", "text": "你好，请问有什么可以帮助你的", "isEnd": true}
```

#### LLM流式响应

```json
{"type": "llm_start", "text": "你好，请问有什么可以帮助你的"}
{"type": "llm_chunk", "text": "我是"}
{"type": "llm_chunk", "text": "心理委员"}
{"type": "llm_end", "fullText": "我是心理委员，很高兴认识你~"}
```

#### TTS音频回传

服务端发送二进制帧（PCM 24kHz 16bit 单声道）

#### 用户打断

```json
{"action": "interrupt"}
```

服务端响应：

```json
{"type": "interrupted", "partialResponse": "..."}
```

#### 停止会话

```json
{"action": "stop"}
```

---

### 3.10 知识图谱接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/graph/user/{userId}/tree` | GET | 获取完整知识树 |
| `/api/graph/user/{userId}/tree/{parentName}?depth=3` | GET | 懒加载子树 |
| `/api/graph/user/{userId}/tree-stats` | GET | 知识树统计 |
| `/api/graph/user/{userId}/echarts` | GET | ECharts图谱数据 |
| `/api/graph/user/{userId}/review` | GET | 复习推荐 |
| `/api/graph/user/{userId}/review-ai` | GET | AI复习建议 |
| `/api/graph/user/{userId}/exam-dashboard` | GET | 考情大屏数据 |
| `/api/graph/user/{userId}/weak-points` | GET | 薄弱知识点链 |
| `/api/graph/user/{userId}/learning-path` | GET | 动态学习路径 |
| `/api/graph/user/{userId}/next-concept` | GET | 下一个推荐考点 |
| `/api/graph/search?keyword=TCP` | GET | 搜索概念 |
| `/api/graph/subject/{subject}/tree` | GET | 科目知识树 |
| `/api/graph/extract` | POST | 提取知识三元组 |
| `/api/graph/user/{userId}/mastery-cache` | DELETE | 清除掌握度缓存 |

**知识提取示例：**

```
POST /api/graph/extract?userMessage=什么是死锁&aiFeedback=死锁是...&subjectName=用户
```

---

### 3.11 农场游戏接口

```
POST /api/farm/judge
```

**请求体：**

```json
{
  "userId": 1,
  "plotId": 101,
  "ownerId": 2,
  "question": "什么是死锁？",
  "answer": "死锁是两个或多个进程互相等待对方释放资源..."
}
```

**响应体：**

```json
{
  "canHarvest": true,
  "score": 85,
  "feedback": "回答较为准确，但缺少死锁的四个必要条件..."
}
```

**限流规则：** 每用户5次/分钟，每IP 10次/分钟

---

### 3.12 考情大屏接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/analysis/dashboard/{userId}` | GET | 完整大屏数据（雷达图+活跃度） |
| `/api/analysis/dashboard/{userId}/radar` | GET | 雷达图数据（四科掌握度） |
| `/api/analysis/dashboard/{userId}/activity` | GET | 本周活跃度数据 |
| `/api/analysis/dashboard/{userId}/summary` | GET | 考情摘要 |
| `/api/analysis/dashboard/{userId}/report` | POST | 生成AI周报 |

**雷达图数据示例：**

```json
{
  "data": [0.75, 0.45, 0.60, 0.80],
  "subjects": ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
}
```

---

### 3.13 Butcanthic 文档智能服务接口

Butcanthic 是独立的文档智能处理微服务，端口 **8002**，提供文档上传/处理、知识库管理、PPT 生成等接口。

#### 3.13.1 认证接口

**静默登录（Qt客户端对接）：**

```
POST /api/v1/auth/silent-login
```

```json
{"user_id": 1}
```

**响应：**

```json
{"access_token": "eyJ...", "token_type": "bearer", "user_id": "uuid", "username": "qt_user_1"}
```

**用户注册：**

```
POST /api/v1/auth/register
```

```json
{"username": "student01", "password": "123456"}
```

**用户登录：**

```
POST /api/v1/auth/login
```

标准 OAuth2 表单登录（`username` + `password`）。

#### 3.13.2 文档上传

```
POST /api/v1/document/upload
```

**请求：** `multipart/form-data`，字段 `file` 为文档文件

**支持格式：** `.docx`、`.xlsx`、`.pptx`、`.csv`

**文件大小限制：** 50MB

**响应体：**

```json
{
  "task_id": "a1b2c3d4e5f6",
  "filename": "数据结构笔记.docx",
  "file_type": "docx",
  "file_size": 102400,
  "message": "文件上传成功，已进入处理队列"
}
```

#### 3.13.3 文档处理

```
POST /api/v1/document/process
```

**请求体：**

```json
{
  "task_id": "a1b2c3d4e5f6",
  "model": null,
  "max_retries": 3,
  "selected_tables": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | String | 是 | 上传时返回的任务ID |
| model | String | 否 | 指定AI模型（默认使用配置中的默认模型） |
| max_retries | Integer | 否 | 每个表格最大重试次数（1-5，默认3） |
| selected_tables | List\<Integer\> | 否 | 指定处理的表格索引列表，null则处理全部 |

**响应体：**

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "processing",
  "message": "处理请求已提交"
}
```

#### 3.13.4 SSE 流式处理

```
POST /api/v1/task/stream-process
```

**请求：** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | List\<File\> | 否 | 上传的文件列表（支持多文件同时上传） |
| user_instruction | String | 否 | 用户指令（如"帮我生成一个关于操作系统的PPT"） |
| model | String | 否 | 指定AI模型 |
| max_retries | Integer | 否 | 最大重试次数（默认3） |
| thread_id | String | 否 | 会话ID（支持跨轮对话记忆） |

**响应：** `text/event-stream`（SSE格式）

```
data: {"status": "session_info", "thread_id": "thread_a1b2c3d4"}
data: {"status": "progress", "node": "gateway", "action": "检测文件类型..."}
data: {"status": "progress", "node": "extract_context", "action": "提取Word文档字段..."}
data: {"status": "progress", "node": "retrieve_knowledge", "action": "RAG知识检索..."}
data: {"status": "progress", "node": "reason_and_fill", "action": "AI推理填充..."}
data: {"status": "progress", "node": "critic_review", "action": "审查校验..."}
data: {"status": "ppt_ready", "ppt_data": {...}}
data: {"status": "success", "output_path": "..."}
```

**特色功能：**
- 支持无文件纯文本模式（仅提供 `user_instruction` 即可生成 PPT）
- 支持 `thread_id` 会话保持，实现跨轮对话记忆
- 登录用户自动将 `user_id` 注入工作流状态，确保 RAG 检索在专属 Collection 中执行

#### 3.13.5 PPT 编辑

```
POST /api/v1/task/edit-slide
```

**请求体：**

```json
{
  "slide_index": 0,
  "instruction": "将标题改为红色",
  "original_slide": {"components": [...]}
}
```

#### 3.13.6 PPT 导出

```
POST /api/v1/task/export-pptx
```

**请求体：** PPT JSON 数据

**响应：** 直接下载 `.pptx` 文件

#### 3.13.7 知识库上传

**单文件上传：**

```
POST /api/v1/knowledge/upload-file
```

**请求：** `multipart/form-data`，字段 `file`

**支持格式：** `.txt`、`.jsonl`、`.pdf`、`.docx`、`.md`

**多文件上传：**

```
POST /api/v1/knowledge/upload-files
```

**请求：** `multipart/form-data`，字段 `files`（多文件）

**支持格式：** `.docx`、`.pptx`、`.xlsx`、`.pdf`、`.txt`、`.md`、`.jsonl`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chunk_size | Integer | 1000 | 文本分块大小 |
| chunk_overlap | Integer | 100 | 分块重叠字符数 |

**响应体：**

```json
{
  "status": "success",
  "collection_name": "kb_user_xxx",
  "record_count": 42,
  "filename": "数据结构笔记.pdf"
}
```

**说明：**
- 数据存入用户专属集合（`kb_{user_id}`），实现 Collection 物理隔离
- PDF/DOCX 自动调用 OCR+Vision 识别图片中的文字
- 自动文本分块（RecursiveCharacterTextSplitter），支持自定义 chunk_size 和 chunk_overlap

#### 3.13.8 文档列表与下载

**我的文档列表：**

```
GET /api/v1/documents/my?page=1&page_size=20
```

**文档下载：**

```
GET /api/v1/document/download/{task_id}
```

**输出文件下载：**

```
GET /api/v1/files/output/{filename}
```

#### 3.13.9 任务进度查询

```
GET /api/v1/task/progress/{task_id}
```

**响应体：**

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "processing",
  "progress": 65.0,
  "stage": "AI推理填充",
  "tables_total": 3,
  "tables_completed": 2,
  "error_message": null
}
```

#### 3.13.10 健康检查

```
GET /api/v1/health
```

```json
{"version": "1.0.0", "uptime": 86400.0}
```

---

## 4. 多智能体编排详解

### 4.1 旗舰大师工作流

旗舰大师（botId=10000）使用三阶段流水线：

```
用户消息 → Router(意图识别) → Solver(解答生成) → Reflection(审核反思) → 最终回复
```

**Router** 识别三种意图：
- **代码求助**：挂载 `cppCompilerTool`，可编译运行C++代码
- **理论解答**：挂载 `webSearchTool` + RAG知识库（混合检索+重排序）
- **日常闲聊**：纯Prompt聊天

### 4.2 出题与判卷工作流

当用户消息包含"刷题""考考我""出题"等关键词时：

```
出题意图 → 图谱分析(薄弱考点) → RAG检索(知识召回) → AI出题 → 设置考试状态
```

用户回答后：

```
用户答案 → AI判卷 → 更新知识图谱掌握度 → 推荐薄弱考点 → 清除考试状态
```

### 4.3 群聊多智能体工作流

```
群消息 → 两级责任链路由 → 并发调用AI角色 → Redis Pub/Sub推送回复
```

**两级责任链：**
1. **显式路由**：检查 `@角色名`，仅被@的AI回复
2. **智能路由**：面试群组由Router AI选择最合适的面试官

---

## 5. 工具能力

### 5.1 C++代码沙盒

- **工具名**：`cppCompilerTool`
- **功能**：编译并运行C++代码，返回编译错误或运行结果
- **超时**：编译3秒，运行3秒
- **安全**：临时文件自动清理

### 5.2 联网搜索

- **工具名**：`webSearchTool`
- **功能**：通过Serper API搜索互联网实时信息
- **适用场景**：最新分数线、招生政策、时效性内容

### 5.3 MCP文件系统工具

系统集成了Spring AI MCP（Model Context Protocol），为代码审查员提供文件系统操作能力：

- **工具来源**：`@modelcontextprotocol/server-filesystem@0.6.2`
- **工作目录**：`/tmp/408_codes`
- **可用工具**：
  - `read_file`：读取文件内容，参数 `path`
  - `list_directory`：列出目录内容，参数 `path`
  - `search_files`：搜索文件内容，参数 `path` + `pattern`
- **启动方式**：通过 `npx` 启动MCP Server，使用stdio传输协议
- **依赖**：需要安装 Node.js 和 npx

---

## 6. RAG检索管线

系统采用工业级混合检索+重排序管线，确保知识检索的准确性和全面性：

```
用户查询 → QueryRewrite(查询改写) → HybridRetrieval(混合召回) → Reranker(精排重排) → 最终知识上下文
```

### 6.1 查询改写（QueryRewriteService）

- 将用户简短/模糊的查询改写为2-4个具体子问题
- 每个子问题使用专业术语，覆盖原始查询的不同方面
- 示例：`"考考我网络"` → `["TCP拥塞控制机制", "HTTP状态码分类", "IP分片与重组机制"]`

### 6.2 混合检索（HybridRetrievalService）

- **向量检索**：基于 `VectorStore.similaritySearch()` 语义相似度检索
- **BM25检索**：基于Redis Search的全文检索（关键词匹配）
- 两种检索结果去重合并，兼顾语义理解和关键词精确匹配
- BM25 Top-K：10

### 6.3 重排序（RerankerService）

- 使用SiliconFlow的 `BAAI/bge-reranker-v2-m3` 模型
- 对混合检索的候选文档进行精排
- 返回Top-N（默认3个）最相关文档
- 每个文档附带 `rerank_score` 和 `rerank_position` 元数据
- 降级策略：重排失败时返回原始文档前N个

---

## 7. 知识图谱体系

### 7.1 图谱结构

知识图谱基于Neo4j，核心节点和关系：

| 节点/关系 | 说明 |
|-----------|------|
| `User` | 用户节点，属性 `userId` |
| `Concept` | 知识概念节点，属性 `name`, `subject`, `level`, `size` |
| `BELONGS_TO` | 概念层级关系（子概念→父概念） |
| `COGNITION` | 用户认知关系，属性 `score`(0-1), `last_update` |

**概念层级**：
- Level 0：408计算机学科专业基础（根节点）
- Level 1：四大科目（数据结构、计算机组成原理、计算机操作系统、计算机网络）
- Level 2：章节级别
- Level 3-5：具体考点级别（出题和追踪的主要层级）

### 7.2 知识追踪算法

采用指数移动平均（EMA）算法更新用户掌握度：

```
新掌握度 = 旧掌握度 + α × (新得分 - 旧掌握度)
其中 α = 1 / concept.size（概念重要度越高，更新越快）
```

掌握度阈值：
- **≥0.7**：已掌握（绿色）
- **0.4~0.7**：熟悉（黄色）
- **<0.4**：薄弱（红色）

### 7.3 知识提取（KnowledgeExtractorService）

从对话中自动提取认知三元组：

```json
[
  {"subject": "用户", "relation": "掌握", "object": "TCP三次握手", "rationale": "用户准确描述了三次握手过程"},
  {"subject": "用户", "relation": "模糊", "object": "拥塞控制", "rationale": "用户混淆了拥塞控制和流量控制"},
  {"subject": "用户", "relation": "未掌握", "object": "页面置换算法", "rationale": "用户对LRU的理解有误"}
]
```

三种关系：`掌握`、`模糊`、`未掌握`，分别对应不同的分数调整策略。

### 7.4 知识树（KnowledgeTreeService）

- 支持全量加载和懒加载两种模式
- 掌握度数据通过Redis缓存（TTL 24小时），避免频繁查询Neo4j
- 缓存Key：`mastery:user:{userId}`
- 支持增量更新缓存，无需全量刷新

### 7.5 智能出题策略

出题时按以下优先级选择考点：

1. **关键薄弱点**：掌握度<0.6且影响后续考点最多的概念
2. **学习路径推荐**：未掌握且level 3-5的概念
3. **随机选择**：level 3-5的随机概念（兜底策略）
4. **去重机制**：最近24小时内出过的考点不会重复（Redis Set存储，最多20个）

---

## 8. Redis消息通信与异步任务

### 8.1 Redis Pub/Sub频道

系统通过Redis Pub/Sub与C++网关（ChatServer）通信：

| 频道 | 方向 | 用途 |
|------|------|------|
| `9999` | C++→AI | 私聊AI请求（AiChatRequestListener监听） |
| `9998` | C++→AI | 群聊AI请求（AiChatRequestListener监听） |
| `9997` | AI→C++ | 群聊消息分发（msgid=17） |
| `9996` | AI→C++ | 农场游戏消息（msgid=73/78） |
| `9995` | C++→AI | 农场答题请求（FarmRedisListener监听） |
| `{userId}` | AI→C++ | 私聊消息推送（msgid=6） |

### 8.2 Redis Stream

系统还使用Redis Stream进行异步任务处理：

| Stream | 消费组 | 任务类型 |
|--------|--------|----------|
| `ai_task_stream` | `ai_group` | `PRIVATE_CHAT`（私聊）、`FARM_JUDGE`（农场判题） |

### 8.3 异步任务队列

| 队列Key | 任务类型 | 消费者 |
|---------|----------|--------|
| `ai:task:queue` | `SUMMARY`（群聊摘要）、`CHAT_REPLY` | AiTaskConsumer |

**AiTaskConsumer**：启动时创建与CPU核心数相同的工作线程，持续从Redis List队列消费任务。

### 8.4 流式消息协议

私聊消息支持流式输出，通过Redis Pub/Sub推送：

| 消息格式 | 说明 |
|----------|------|
| `[STREAM_CHUNK]: ` | 流式开始（空内容，触发思考提示） |
| `[STREAM_CHUNK]:{text}` | 流式文本块 |
| `[STREAM_CHUNK]:[STREAM_END]` | 流式结束 |
| `[STREAM_CHUNK]:[STREAM_CLEAR]` | 清除之前的提示内容 |

### 8.5 考试状态管理

- **存储**：Redis Key `STATE:EXAMING:{userId}`
- **TTL**：30分钟
- **内容**：JSON序列化的 `ExamContext`（科目、题干、标准答案、题目来源）
- **生命周期**：出题时进入考试状态 → 用户回答后判卷 → 判卷完成后清除

---

## 9. 定时任务

### 9.1 周报自动生成

| 任务 | Cron表达式 | 说明 |
|------|------------|------|
| `generateWeeklyReports` | `0 0 22 ? * SUN` | 每周日22:00为所有活跃用户生成学习周报 |
| `sendWeeklyReportSummary` | `0 5 22 ? * SUN` | 每周日22:05生成系统运行汇总 |

**周报生成流程**：
1. 查询所有活跃用户（Neo4j `UserNode`）
2. 计算各科掌握度
3. 调用AI生成Markdown格式周报
4. 通过Redis Pub/Sub推送至用户
5. 支持重试（`@Retryable`，最多3次，指数退避）

---

## 10. 结构化输出与重试

### 10.1 StructuredOutputInvoker

系统封装了结构化输出调用器，解决AI返回JSON格式不稳定的问题：

- **最大重试次数**：2次（可配置）
- **重试策略**：重试时附加严格JSON指令和上次错误信息
- **指标监控**：通过Micrometer记录调用次数、尝试次数、延迟（按context和status标签）
- **指标名称**：
  - `app.ai.structured_output.invocations`：调用次数
  - `app.ai.structured_output.attempts`：尝试次数
  - `app.ai.structured_output.latency`：调用延迟

---

## 11. 限流策略

系统使用基于Redis + Redisson的分布式限流，支持用户维度和IP维度：

**注解方式**：使用 `@RateLimit` 自定义注解 + AOP切面实现

| 接口 | 用户维度 | IP维度 |
|------|----------|--------|
| /api/ai/chat | 30次/分钟 | 60次/分钟 |
| /api/ai/mindmap | 10次/分钟 | 20次/分钟 |
| /api/ai/companion-read | 20次/分钟 | 40次/分钟 |
| /api/rag/upload | 10次/分钟 | 20次/分钟 |
| /api/agent/chat | 20次/分钟 | 40次/分钟 |
| /api/farm/judge | 5次/分钟 | 10次/分钟 |

**限流实现**：
- 用户维度：基于 `userId` 参数，Redisson `RateLimiter`
- IP维度：基于 `HttpServletRequest.getRemoteAddr()`
- 超限时抛出 `RateLimitExceededException`，由 `GlobalExceptionHandler` 统一处理

---

## 12. 记忆管理

### 12.1 私聊记忆

- 基于 `RedisChatMemory` 实现
- 每个用户-角色对独立会话：`chat_{userId}_{botId}`
- 最大历史轮数：10轮
- TTL：30分钟
- 支持 `add()`、`get()`、`clear()` 操作
- 旗舰大师记忆前缀：`chat:{userId}:{botId}`

### 12.2 群聊记忆

- 独立的 `GroupChatMemoryService`
- 最大消息数：100条
- TTL：24小时
- 存储格式：Redis List，Key `group:messages:{groupId}`
- 每条消息包含：`senderId`、`senderName`、`content`、`timestamp`

---

## 13. 错误处理

系统通过 `GlobalExceptionHandler` 统一处理异常：

| 异常类型 | HTTP状态码 | 处理方式 |
|----------|------------|----------|
| `RateLimitExceededException` | 429 | 返回限流提示 |
| `MethodArgumentNotValidException` | 400 | 返回参数校验错误 |
| `MissingServletRequestParameterException` | 400 | 返回缺失参数提示 |
| `MaxUploadSizeExceededException` | 413 | 返回文件过大提示 |
| `Exception` | 500 | 返回通用错误信息 |

**统一错误响应格式：**

```json
{
  "success": false,
  "error": "错误描述信息"
}
```

---

## 14. 考情大屏与数据分析

### 14.1 大屏数据结构

完整大屏数据包含：

```json
{
  "radar": {
    "data": [0.75, 0.45, 0.60, 0.80],
    "subjects": ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
  },
  "activity": {
    "labels": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    "data": [5, 8, 3, 12, 6, 15, 10]
  }
}
```

### 14.2 AI周报

通过 `/api/analysis/dashboard/{userId}/report` 生成，包含：

- 各科掌握度分析
- 本周学习活跃度
- 薄弱知识点提醒
- 下周学习建议

### 14.3 静态大屏页面

系统内置考情大屏HTML页面，访问路径：

```
GET http://localhost:8081/dashboard.html?userId=1
```

该页面展示完整的考情数据可视化，包括雷达图、活跃度折线图等。

---

## 15. Java AI服务项目结构

```
ai-service/
├── src/main/java/com/chat/ai/
│   ├── AiServiceApplication.java          # 启动类
│   ├── config/                            # 配置类
│   │   ├── ChatClientConfig.java          # ChatClient配置（smart/fast两套模型）
│   │   ├── ChatMemoryConfig.java          # 聊天记忆配置
│   │   ├── CodeSandboxToolConfig.java     # C++沙盒工具
│   │   ├── CorsConfig.java               # 跨域配置
│   │   ├── EmbeddingConfig.java          # 向量嵌入配置（SiliconFlow BGE-M3）
│   │   ├── McpConfig.java                # MCP文件系统工具配置
│   │   ├── MultimodalConfig.java         # 多模态配置（解题大王）
│   │   ├── RagConfig.java                # RAG配置
│   │   ├── RedisConfig.java              # Redis配置
│   │   ├── RedissonConfig.java           # Redisson分布式锁/限流配置
│   │   ├── RedisVectorStoreConfig.java   # Redis向量存储配置
│   │   ├── VoiceConfig.java              # 语音配置（ASR/TTS）
│   │   ├── VoiceWebConfig.java           # 语音Web配置
│   │   ├── WebSearchToolConfig.java      # 联网搜索工具（Serper）
│   │   ├── WebClientConfig.java          # WebClient配置
│   │   ├── ai/                           # 结构化输出配置
│   │   │   └── StructuredOutputInvoker.java  # 结构化输出调用器（含重试/指标）
│   │   ├── annotation/                   # @RateLimit限流注解
│   │   └── aspect/                       # RateLimitAspect限流切面
│   ├── controller/                        # 控制器
│   │   ├── AiController.java             # AI聊天/思维导图/伴读/PDF
│   │   ├── AiStreamController.java       # 流式聊天
│   │   ├── AgentController.java          # 多智能体工作流
│   │   ├── DashboardController.java      # 考情大屏
│   │   ├── FarmController.java           # 农场游戏
│   │   ├── GroupChatController.java      # 群聊
│   │   ├── KnowledgeGraphController.java # 知识图谱
│   │   ├── RagController.java            # RAG知识库
│   │   ├── VoiceController.java          # 语音接口
│   │   ├── CareerDashboardController.java # 职业规划大屏
│   │   ├── ChatRequest.java              # 聊天请求DTO
│   │   └── ChatResponse.java             # 聊天响应DTO
│   ├── service/                           # 业务服务
│   │   ├── AiChatService.java            # 1v1聊天核心
│   │   ├── AiPersonaRegistry.java        # AI角色注册中心（10个角色定义）
│   │   ├── AgentOrchestratorService.java # 多智能体编排（Router→Solver→Reflection）
│   │   ├── GroupChatService.java         # 群聊服务
│   │   ├── RagService.java               # RAG文档处理（PDF/OCR/分块/向量化）
│   │   ├── VoiceChatService.java         # 语音聊天（ASR→LLM→TTS）
│   │   ├── CompanionReadingService.java  # 伴读服务（文字+语音讲解）
│   │   ├── MultimodalChatService.java    # 多模态聊天（图片识别）
│   │   ├── CodeReviewerService.java      # 代码审查服务（MCP文件系统）
│   │   ├── FarmService.java              # 农场游戏核心逻辑
│   │   ├── FarmAiJudgeService.java       # 农场AI判题
│   │   ├── GraphExamService.java         # 图谱考试服务（出题/判卷/掌握度更新）
│   │   ├── GraphRetrievalService.java    # 图谱检索（Cypher查询）
│   │   ├── KnowledgeExtractorService.java # 知识三元组提取
│   │   ├── KnowledgeTreeService.java     # 知识树构建与缓存
│   │   ├── ReviewService.java            # 复习推荐服务
│   │   ├── HybridRetrievalService.java   # 混合检索（向量+BM25）
│   │   ├── RerankerService.java          # 重排序服务（BGE-Reranker）
│   │   ├── QueryRewriteService.java      # 查询改写服务
│   │   ├── ChatMemoryService.java        # 私聊记忆管理
│   │   ├── GroupChatMemoryService.java   # 群聊记忆管理
│   │   ├── ExamStateManager.java         # 考试状态管理（Redis）
│   │   ├── RedisPubSubService.java       # Redis消息发布
│   │   ├── AiChatRequestListener.java    # Redis Pub/Sub私聊/群聊请求监听
│   │   ├── AiTaskConsumer.java           # 异步任务消费者（线程池）
│   │   ├── AiTaskStreamConsumer.java     # Redis Stream消费者（私聊/农场）
│   │   └── FarmRedisListener.java        # 农场Redis消息监听
│   ├── model/                             # 数据模型
│   │   ├── AiTask.java                   # AI异步任务模型
│   │   ├── ChatMessage.java              # 聊天消息模型
│   │   ├── HarvestJudgment.java          # 农场判题结果模型
│   │   └── graph/                        # 图谱模型
│   │       ├── KnowledgeTriplet.java     # 知识三元组
│   │       └── ExamContext.java          # 考试上下文
│   ├── memory/                            # 记忆实现
│   │   └── RedisChatMemory.java          # Redis聊天记忆
│   ├── repository/                        # 数据访问
│   │   └── KnowledgeGraphRepository.java # Neo4j图谱仓库
│   ├── websocket/                         # WebSocket处理器
│   │   ├── RealtimeVoiceWebSocketHandler.java  # 实时语音WebSocket
│   │   └── SimpleIdeWebSocketHandler.java      # 简化IDE WebSocket
│   ├── rpc/                               # Protobuf RPC通信
│   │   ├── InternalRpcServer.java        # Netty RPC服务端（接收C++请求）
│   │   ├── ProtobufRpcClient.java        # Protobuf RPC客户端（连接C++/Python）
│   │   ├── RpcPushService.java           # 消息推送服务（私聊/群聊/流式/语音/农场）
│   │   ├── ProtobufEncoder.java          # Protobuf编码器
│   │   └── ProtobufDecoder.java          # Protobuf解码器
│   ├── exception/                         # 异常处理
│   │   ├── GlobalExceptionHandler.java   # 全局异常处理器
│   │   └── RateLimitExceededException.java # 限流异常
│   └── scheduler/                         # 定时任务
│       └── WeeklyReportScheduler.java    # 周报自动生成
├── src/main/resources/
│   ├── application.yml                    # 主配置文件
│   ├── scripts/                           # Lua脚本（限流等）
│   └── static/                            # 静态资源
│       └── dashboard.html                 # 考情大屏页面
├── Dockerfile                             # Docker构建文件
└── pom.xml                                # Maven配置
```

---

## 16. C++服务器端（ChatServer）

### 16.1 架构概述

C++服务器端是基于 **muduo网络库** 构建的高性能TCP服务器，负责处理即时通讯核心功能：

```
┌─────────────────────────────────────────────────────────────────┐
│                        ChatServer (C++)                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ muduo::TcpServer │  │ ChatService  │  │ Redis Client │          │
│  │  (网络层)     │  │  (业务层)    │  │  (消息转发)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                │                  │                    │
│         ▼                ▼                  ▼                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ MySQL        │  │ UserModel    │  │ Redis Pub/Sub│          │
│  │ (持久化)     │  │ FriendModel  │  │ (跨服务器)   │          │
│  │              │  │ GroupModel   │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 16.2 核心功能

| 功能模块 | 说明 |
|----------|------|
| 用户认证 | 登录/注册/登出，支持头像Base64编码传输 |
| 私聊消息 | 一对一消息转发，支持离线消息存储 |
| 群聊消息 | 群组消息广播，支持跨服务器转发 |
| AI消息拦截 | 识别AI角色ID（10000-10099），转发至AI服务 |
| 文件传输 | 点对点文件传输，支持分块传输和断点续传 |
| 表情包 | 用户自定义表情包上传和查询 |
| 农场游戏 | 种菜/答题/收割完整流程 |
| 状态同步 | 用户在线状态实时推送 |

### 16.3 消息协议

系统使用 **长度前缀 + JSON** 的消息格式，解决TCP粘包问题：

```
┌────────────────┬──────────────────────────────┐
│  4 bytes       │  N bytes                     │
│  (大端长度)    │  JSON消息体                  │
└────────────────┴──────────────────────────────┘
```

**消息类型枚举（MsgType）：**

| msgid | 常量名 | 说明 |
|-------|--------|------|
| 1 | LOGIN_MSG | 登录请求 |
| 2 | LOGIN_MSG_ACK | 登录响应 |
| 3 | LOGINOUT_MSG | 登出请求 |
| 4 | REG_MSG | 注册请求 |
| 5 | REG_MSG_ACK | 注册响应 |
| 6 | ONE_CHAT_MSG | 私聊消息 |
| 7 | ADD_FRIEND_MSG | 添加好友 |
| 9 | QUERY_FRIEND_MSG | 查询好友列表 |
| 11 | QUERY_GROUP_MSG | 查询群组列表 |
| 13 | CREATE_GROUP_MSG | 创建群组 |
| 17 | GROUP_CHAT_MSG | 群聊消息 |
| 18 | INVITE_GROUP_MSG | 邀请入群 |
| 20-24 | FILE_TRANSFER_* | 文件传输系列 |
| 25-28 | EMOJI_* | 表情包系列 |
| 40-43 | AVATAR_* | 头像系列 |
| 44 | STATE_UPDATE_MSG | 状态更新 |
| 50 | CREATE_INTERVIEW_GROUP_MSG | 创建面试群组 |
| 60 | VOICE_MSG | 语音消息 |
| 70-79 | FARM_* | 农场游戏系列 |

### 16.4 AI消息拦截机制

服务器端会自动识别目标用户ID，将AI相关消息转发至Java AI服务：

```cpp
const int AI_BOT_ID_MIN = 10000;
const int AI_BOT_ID_MAX = 10099;

if (toid >= AI_BOT_ID_MIN && toid <= AI_BOT_ID_MAX) {
    json aiRequest;
    aiRequest["userId"] = fromId;
    aiRequest["botId"] = toid;
    aiRequest["message"] = userMessage;
    _redis.xadd("ai_task_stream", "PRIVATE_CHAT", aiRequest.dump());
}
```

**群聊AI拦截：**
- **显式@**：消息包含 `@旗舰大师` 等，触发对应AI回复
- **面试群组**：群组包含面试官矩阵（10004, 10005, 10006），自动触发Router AI

### 16.5 Redis通信频道

| 频道 | 方向 | 用途 |
|------|------|------|
| `{userId}` | AI→C++ | AI回复推送给用户 |
| `9997` | AI→C++ | 群聊消息分发 |
| `9996` | AI→C++ | 农场游戏广播 |
| `9998` | C++→AI | 群聊AI请求 |
| `9999` | C++→AI | 私聊AI请求 |
| `9995` | C++→AI | 农场答题请求 |
| `ai_task_stream` | C++→AI | Redis Stream任务队列 |

---

## 17. C++客户端（QtChat）

### 17.1 架构概述

C++客户端是基于 **Qt 5** 框架构建的跨平台桌面应用，采用 Material Design 风格：

```
┌─────────────────────────────────────────────────────────────────┐
│                        QtChat Client                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ LoginWindow  │  │ ChatWindow   │  │ MainWindow   │          │
│  │ (登录界面)   │  │ (聊天界面)   │  │ (主窗口)     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                │                  │                    │
│         ▼                ▼                  ▼                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ChatClient   │  │ Qt Material  │  │ Live2D       │          │
│  │ (网络通信)   │  │ (UI组件)     │  │ (虚拟形象)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 17.2 核心功能模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 登录/注册 | `loginwindow.cpp` | 用户认证界面，支持头像上传 |
| 聊天窗口 | `chatwindow.cpp` | 私聊/群聊消息展示，支持富文本 |
| 消息组件 | `messagewidget.cpp` | 消息气泡渲染，支持图片/语音/文件 |
| 农场游戏 | `farmdialog.cpp` | 农场界面，种菜/答题/收割 |
| 知识图谱 | `knowledgegraphdialog.cpp` | 知识树可视化，掌握度展示 |
| 考情大屏 | `dashboarddialog.cpp` | 雷达图/活跃度/周报展示 |
| 实时语音 | `realtimevoicedialog.cpp` | WebSocket实时语音对话 |
| 伴读功能 | `companionreadingdialog.cpp` | 划选文本语音讲解 |
| 编程Agent | `codingagentdialog.cpp` | AI编程助手对话框 |
| 职业规划 | `career_dashboard_dialog.cpp` | 职业规划仪表盘 |

### 17.3 网络通信设计

**ChatClient类** 采用事件驱动架构：

```cpp
connect(socket, &QTcpSocket::connected, this, [=]() {
    isConnected = true;
    emit connectionStateChanged(true);
});

connect(socket, &QTcpSocket::readyRead, this, &ChatClient::onReadyRead);
```

**消息发送格式：**

```cpp
void ChatClient::sendJsonMessage(const QJsonObject &message) {
    qint32 length = jsonData.size();
    QByteArray lengthBytes;
    QDataStream stream(&lengthBytes, QIODevice::WriteOnly);
    stream.setByteOrder(QDataStream::BigEndian);
    stream << length;

    QByteArray data = lengthBytes + jsonData;
    socket->write(data);
}
```

### 17.4 信号槽机制

ChatClient通过Qt信号槽与UI层通信：

| 信号 | 说明 |
|------|------|
| `loginResponse(bool, QString)` | 登录/注册结果 |
| `messageReceived(qint64, QString, QString, bool, int, QString)` | 私聊消息接收 |
| `groupMessageReceived(int, qint64, QString, QString, QString)` | 群聊消息接收 |
| `voiceMessageReceived(qint64, QString, int, QString, QString)` | 语音消息接收 |
| `friendListUpdated(QList<User>)` | 好友列表更新 |
| `groupListUpdated(QList<Group>)` | 群组列表更新 |
| `friendStateUpdated(qint64, QString)` | 好友状态更新 |
| `farmPlantResponse(bool, int, QString)` | 种菜响应 |
| `farmAnswerResponse(bool, int, QString, int, bool)` | 答题响应 |
| `avatarUpdated(QString)` | 头像更新 |

### 17.5 Live2D虚拟形象

客户端内置Live2D虚拟形象支持：

- **模型**：hiyori_pro_t11
- **渲染**：基于Qt WebEngine，通过QWebChannel与HTML页面通信
- **动作**：支持idle、tap等动作触发
- **路径**：`live2d/hiyori/` 目录

### 17.6 跨平台支持

客户端支持多平台编译：

| 平台 | 编译器 | 说明 |
|------|--------|------|
| Linux | GCC | 主要开发平台 |
| Windows | MSVC/MinGW | 需处理Windows网络头文件兼容 |

**Windows兼容处理：**

```cpp
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #undef byte
#else
    #include <arpa/inet.h>
#endif
```

---

## 18. 完整项目结构

```
/home/xmy/code/
├── ai-service/                           # Java AI服务
│   ├── src/main/java/com/chat/ai/
│   │   ├── AiServiceApplication.java
│   │   ├── config/
│   │   ├── controller/
│   │   ├── service/
│   │   ├── model/
│   │   ├── memory/
│   │   ├── repository/
│   │   ├── websocket/
│   │   ├── exception/
│   │   └── scheduler/
│   ├── src/main/resources/
│   │   ├── application.yml
│   │   ├── scripts/
│   │   └── static/
│   ├── Dockerfile
│   └── pom.xml
│
├── eruitah-sandbox/                      # Python 编程沙盒
│   ├── main.py                           # FastAPI Web服务入口
│   ├── agent_runner.py                   # Agent核心引擎（run_agent生成器）
│   ├── agent_swarm.py                    # 多智能体协同系统（P2P网络+Coder-Reviewer对抗）
│   ├── agent_prompts.py                  # 专家身份系统（Supervisor路由+动态专家生成）
│   ├── agent_process.py                  # Agent子进程管理（进程级沙盒隔离）
│   ├── bash_executor.py                  # Bash命令执行器（安全沙盒）
│   ├── file_editor.py                    # 文件编辑器（SEARCH/REPLACE模式）
│   ├── file_read_tool.py                 # 文件读取工具（行号过滤）
│   ├── glob_tool.py                      # Glob文件模式匹配
│   ├── grep_tool.py                      # Grep正则搜索（rg/grep/python三级回退）
│   ├── tool_registry.py                  # 工具注册表
│   ├── task_manager.py                   # 任务管理器（创建/切换/删除/会话持久化）
│   ├── task_registry.py                  # 任务注册表（物理快照管理）
│   ├── session_storage.py                # 会话持久化存储
│   ├── rewind_system.py                  # 会话回退系统（Git指针+SQLite混合架构）
│   ├── rewind_command.py                 # 回退命令处理器
│   ├── sandbox_manager.py                # Git Worktree沙盒管理器（WarmPool预热池）
│   ├── shadow_sandbox.py                 # 影子沙盒
│   ├── interactive_terminal.py           # 交互式终端（PTY + 后台进程管理）
│   ├── mcp_client.py                     # MCP协议客户端（动态加载第三方工具）
│   ├── auto_test_tool.py                 # 自动测试工具
│   ├── browser_vision_tool.py            # 浏览器视觉工具
│   ├── computer_use_tool.py              # Computer Use工具
│   ├── lsp_tool.py                       # LSP语言服务工具
│   ├── lsp_client.py                     # LSP客户端
│   ├── semantic_search_tool.py           # 语义搜索工具
│   ├── tree_sitter_index.py              # Tree-sitter代码索引
│   ├── ast_tool.py                       # AST分析工具
│   ├── screenshot_tool.py                # 截图工具
│   ├── notebook_tool.py                  # Notebook工具
│   ├── cost_guardrails.py                # 成本护栏（Token计费+预算控制）
│   ├── token_budget.py                   # Token预算管理
│   ├── artifact_builder.py               # 产物构建器
│   ├── prompt_caching.py                 # 提示词缓存
│   ├── self_distill.py                   # 自蒸馏
│   ├── compute_autonomy.py               # 自主计算
│   ├── memory_manager.py                 # 记忆管理器
│   ├── memory_store.py                   # 记忆存储
│   ├── prompt_builder.py                 # 提示词构建器
│   ├── meta_tool.py                      # 元工具
│   ├── git_tool.py                       # Git工具
│   ├── ask_user_tool.py                  # 用户交互工具
│   ├── interactive_debugger_tool.py      # 交互式调试器
│   ├── dynamic_sequentialthinking.py     # 动态顺序思维
│   ├── theseus_rewrite.py                # Theseus重写引擎
│   ├── container_pool.py                 # 容器池管理
│   ├── insertion_sort.py                 # 插入排序示例
│   ├── requirements.txt                  # Python依赖
│   ├── Dockerfile                        # Docker构建文件
│   └── static/
│       └── coding_lab.html               # Web IDE界面
│
├── butcanthic/                           # Python 文档智能服务
│   ├── main.py                           # FastAPI 入口
│   ├── requirements.txt                  # Python 依赖
│   ├── ai_models_config.json             # AI 模型配置（多模型切换，.gitignore）
│   ├── metadata.db                       # SQLite 元数据数据库
│   ├── graph_db.json                     # NetworkX 知识图谱数据
│   ├── prompts/                          # 提示词模板目录
│   │   ├── supervisor_system.md          # Supervisor 主管调度提示词
│   │   ├── reason_and_fill_system.md     # AI 推理填充提示词
│   │   ├── critic_review_system.md       # Critic 审查提示词
│   │   ├── generate_ppt_system.md        # PPT 生成提示词
│   │   ├── process_summary_system.md     # 长文总结提示词
│   │   ├── literature_guide_system.md    # 文献导读提示词
│   │   └── ...                           # 其他提示词模板
│   ├── static/                           # 静态前端页面
│   │   ├── index.html                    # Vue 3 完整前端单页面应用
│   │   └── ppt-viewer/                   # PPT 查看器静态资源
│   ├── scripts/                          # 工具脚本
│   │   ├── run_rag_eval.py               # RAG 评估脚本
│   │   └── migrate_jsonl_to_chroma.py    # JSONL 迁移到 ChromaDB
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py                 # 全局配置
│   │   │   ├── lifespan.py               # 应用生命周期（启动/关闭）
│   │   │   ├── app_state.py              # 全局状态（LLM/RAG/服务实例）
│   │   │   ├── security.py               # JWT 鉴权
│   │   │   ├── file_manager.py           # 文件管理器
│   │   │   ├── task_runner.py            # 任务执行引擎（Celery/本地双模式）
│   │   │   ├── celery_app.py             # Celery 应用配置
│   │   │   └── prompt_manager.py         # 提示词管理器（.md模板加载+变量替换）
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py             # API 路由注册
│   │   │       └── endpoints.py          # 全部 API 端点
│   │   ├── agent_workflow/
│   │   │   ├── graph.py                  # LangGraph 工作流定义（16个节点）
│   │   │   ├── state.py                  # WorkflowState 状态定义
│   │   │   └── nodes/
│   │   │       ├── gateway_node.py       # 网关节点（文件类型路由）
│   │   │       ├── extract_context.py    # Word 字段提取
│   │   │       ├── retrieve_knowledge.py # RAG 知识检索
│   │   │       ├── reason_and_fill.py    # AI 推理填充
│   │   │       ├── critic_review.py      # Critic 审查（Word/PPT）
│   │   │       ├── process_excel.py      # Excel 数据清洗
│   │   │       ├── process_ppt.py        # PPT 分析
│   │   │       ├── generate_ppt.py       # PPT 生成
│   │   │       ├── process_summary.py    # 长文总结
│   │   │       ├── supervisor.py         # Supervisor 主管调度
│   │   │       ├── web_researcher.py     # 联网搜索
│   │   │       ├── knowledge_librarian.py # 知识库检索
│   │   │       ├── auto_tagging.py       # 自动标签
│   │   │       └── literature_guide.py   # 文献导读
│   │   ├── services/
│   │   │   ├── ai_client.py             # AI 客户端（多模型切换）
│   │   │   ├── rag_engine.py            # RAG 检索引擎（三路混合）
│   │   │   ├── graph_engine.py          # 知识图谱引擎
│   │   │   ├── document_service.py      # 文档处理服务
│   │   │   ├── excel_service.py         # Excel 数据处理
│   │   │   ├── ppt_service.py           # PPT 分析/生成
│   │   │   ├── ppt_export_service.py    # PPT 导出（JSON→.pptx）
│   │   │   ├── docx_parser.py           # Word 文档解析
│   │   │   ├── docx_to_html_converter.js # Node.js DOCX→HTML 转换（mammoth.js）
│   │   │   ├── word_export_service.py   # Word 文档导出（python-docx）
│   │   │   ├── kb_processor.py          # 知识库文件处理器（分块+向量化+闪卡）
│   │   │   ├── ocr_helper.py            # OCR+Vision 辅助
│   │   │   ├── evaluator.py             # 评估器
│   │   │   └── memory_service.py        # 对话记忆管理
│   │   ├── worker/
│   │   │   └── tasks.py                 # Celery 异步任务（文档处理/知识库/闪卡）
│   │   └── models/
│   │       ├── database.py              # SQLAlchemy 数据模型
│   │       ├── schemas.py               # Pydantic 请求/响应模型
│   │       └── ppt_schema.py            # PPT 结构化输出模型
│   └── frontend_vite/                   # React 前端（Vite 库模式，输出 IIFE 供 iframe 嵌入）
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       └── src/
│           ├── index.tsx                # Vite 构建入口
│           ├── PPTViewer.tsx            # PPT 在线查看器主组件
│           ├── SlideCanvas.tsx          # 幻灯片画布渲染组件
│           ├── types.ts                 # TypeScript 类型定义
│           └── components/
│               └── KnowledgeGraph.tsx   # 知识图谱 ECharts 可视化
│
├── coding-agent-ui/                      # Vue Web IDE
│   ├── index.html                        # 入口HTML
│   ├── package.json                      # 依赖配置
│   ├── vite.config.js                    # Vite配置（含开发代理）
│   ├── tailwind.config.js                # Tailwind CSS配置
│   ├── postcss.config.js                 # PostCSS配置
│   ├── src/
│   │   ├── main.js                       # 应用入口
│   │   ├── App.vue                       # 应用根组件
│   │   ├── style.css                     # 全局样式
│   │   ├── components/
│   │   │   ├── ChatPanel.vue             # AI聊天面板
│   │   │   ├── CodeEditor.vue            # Monaco代码编辑器
│   │   │   ├── TerminalPanel.vue         # xterm终端面板
│   │   │   ├── FileTree.vue              # 文件树
│   │   │   ├── TaskList.vue              # 任务列表
│   │   │   ├── ToolBar.vue               # 工具栏
│   │   │   ├── SkillPanel.vue            # 技能面板
│   │   │   ├── DirPicker.vue             # 目录选择器
│   │   │   └── PixelPet.vue              # 像素宠物
│   │   ├── stores/
│   │   │   └── agent.js                  # Pinia状态管理
│   │   ├── utils/
│   │   │   ├── webcontainerManager.js    # WebContainer管理器
│   │   │   └── mermaidRenderer.js        # Mermaid图表渲染器
│   │   └── assets/
│   │       └── pixel_pet_spritesheet.png # 像素宠物精灵图
│   └── dist/                             # 构建输出（Nginx/沙盒服务静态文件）
│
├── protobuf-rpc-bridge/                  # Protobuf RPC桥接
│   ├── proto/
│   │   └── chat.proto                    # Protobuf消息定义
│   ├── cpp/
│   │   ├── include/
│   │   │   ├── rpc_channel.h             # RPC通道
│   │   │   ├── protobuf_codec.h          # Protobuf编解码器
│   │   │   ├── chat_server.h             # RPC服务器
│   │   │   └── proto/
│   │   │       ├── chat.pb.h             # 生成的Protobuf头文件
│   │   │       └── chat.pb.cc            # 生成的Protobuf源文件
│   │   ├── src/
│   │   │   ├── main.cc                   # C++ RPC入口
│   │   │   ├── chat_server.cc            # C++ RPC服务器实现
│   │   │   ├── rpc_channel.cc            # RPC通道实现
│   │   │   ├── protobuf_codec.cc         # 编解码器实现
│   │   │   └── crosslang_test.cc         # 跨语言测试
│   │   └── CMakeLists.txt
│   ├── java/
│   │   ├── pom.xml
│   │   └── src/main/java/com/bridge/
│   │       ├── server/
│   │       │   ├── JavaBackendServer.java    # Java RPC服务器
│   │       │   ├── RpcMessageHandler.java    # RPC消息处理器
│   │       │   ├── ProtobufEncoder.java      # Protobuf编码器
│   │       │   └── ProtobufDecoder.java      # Protobuf解码器
│   │       ├── service/
│   │       │   ├── ChatService.java          # 聊天服务接口
│   │       │   └── impl/
│   │       │       └── AIChatService.java     # 聊天服务实现
│   │       └── test/
│   │           ├── JavaRpcClient.java        # Java RPC客户端
│   │           └── CrossLangTest.java        # 跨语言测试
│   ├── python/
│   │   ├── main.py                           # Python RPC入口
│   │   ├── requirements.txt
│   │   ├── bridge/
│   │   │   ├── rpc_server.py                 # RPC服务器
│   │   │   ├── streaming_rpc_server.py       # 流式RPC服务器
│   │   │   ├── rpc_client.py                 # RPC客户端
│   │   │   ├── codec.py                      # 编解码器
│   │   │   └── proto/
│   │   │       └── chat_pb2.py               # 生成的Protobuf Python代码
│   │   └── services/
│   │       ├── swarm_bridge.py               # Swarm P2P桥接
│   │       ├── sandbox_bridge.py             # 沙盒桥接
│   │       └── sandbox_adapter.py            # 沙盒适配器
│   ├── scripts/
│   │   ├── generate_proto.sh                 # Protobuf代码生成脚本
│   │   ├── build.sh                          # 构建脚本
│   │   ├── start.sh                          # 启动脚本
│   │   └── test_client.py                    # 测试客户端
│   └── Dockerfile
│
├── src/                                  # C++源代码
│   ├── main.cpp                          # 客户端入口
│   ├── public.h                          # 消息类型枚举
│   ├── chatclient.cpp/h                  # 客户端网络通信
│   ├── chatserver.cpp/h                  # 服务器端共享代码
│   ├── loginwindow.cpp/h                 # 登录窗口
│   ├── mainwindow.cpp/h                  # 主窗口
│   ├── chatwindow.cpp/h                  # 聊天窗口
│   ├── messagewidget.cpp/h               # 消息组件
│   ├── customtitlebar.cpp/h              # 自定义标题栏
│   ├── farmdialog.cpp/h                  # 农场对话框
│   ├── farmplotitem.cpp/h                # 农场地块组件
│   ├── knowledgegraphdialog.cpp/h        # 知识图谱对话框
│   ├── dashboarddialog.cpp/h             # 考情大屏对话框
│   ├── realtimevoicedialog.cpp/h         # 实时语音对话框
│   ├── companionreadingdialog.cpp/h      # 伴读对话框
│   ├── codingagentdialog.cpp/h           # 编程Agent对话框
│   ├── career_dashboard_dialog.cpp/h     # 职业规划仪表盘对话框
│   │
│   ├── client/                           # 客户端CMake配置
│   │   └── CMakeLists.txt
│   │
│   ├── server/                           # 服务器端代码
│   │   ├── main.cpp                      # 服务器入口
│   │   ├── chatserver.cpp                # muduo服务器
│   │   ├── chatservice.cpp               # 业务逻辑
│   │   ├── db/
│   │   │   └── db.cpp                    # MySQL数据库操作
│   │   ├── model/
│   │   │   ├── usermodel.cpp             # 用户模型
│   │   │   ├── friendmodel.cpp           # 好友模型
│   │   │   ├── groupmodel.cpp            # 群组模型
│   │   │   ├── offlinemessagemodel.cpp   # 离线消息模型
│   │   │   ├── emojimodel.cpp            # 表情包模型
│   │   │   └── farmmodel.cpp             # 农场模型
│   │   ├── redis/
│   │   │   └── redis.cpp                 # Redis客户端
│   │   └── CMakeLists.txt
│   │
│   ├── models/                           # 共享数据模型
│   │   ├── user.h/cpp
│   │   ├── group.h/cpp
│   │   ├── groupuser.h
│   │   └── usermodel.h/cpp
│   │
│   └── qtchat.qrc                        # Qt资源文件
│
├── include/                              # 头文件目录
│   └── server/
│       ├── db/
│       ├── model/
│       └── redis/
│
├── docker/                               # Docker配置
│   ├── nginx/
│   │   └── nginx.conf                    # Nginx反向代理配置
│   └── mysql/
│       └── init.sql                      # MySQL初始化脚本
│
├── qt-material-widgets/                  # Material Design UI组件库
│   ├── components/
│   │   ├── qtmaterialavatar.cpp/h
│   │   ├── qtmaterialbutton.cpp/h
│   │   ├── qtmaterialtextfield.cpp/h
│   │   ├── qtmaterialdialog.cpp/h
│   │   ├── qtmaterialdrawer.cpp/h
│   │   ├── qtmaterialsnackbar.cpp/h
│   │   └── ...
│   └── examples/
│
├── live2d/                               # Live2D虚拟形象资源
│   ├── core/
│   │   └── live2dcubismcore.js
│   └── hiyori/
│       ├── hiyori_pro_t11.model3.json
│       ├── hiyori_pro_t11.moc3
│       └── motion/
│
├── html/                                 # Web资源
│   └── avatar.html
│
├── thirdparty/                           # 第三方库
│   └── json.hpp                          # nlohmann/json
│
├── test/                                 # 测试代码
│   ├── testmuduo/
│   └── testjson/
│
├── bin/                                  # 编译输出目录
├── CMakeLists.txt                        # 根CMake配置
├── Dockerfile.chatserver                 # C++ ChatServer Docker构建文件
├── docker-compose.yml                    # Docker Compose编排
├── .env                                  # 环境变量配置文件
└── *.md                                  # 文档文件
```

---

## 19. Butcanthic 文档智能服务

### 19.1 架构概述

Butcanthic 是基于 **FastAPI + LangGraph** 的企业级文档智能处理微服务，核心采用 LangGraph 多 Agent 工作流，支持条件路由、自我纠错和 Critic 审查机制：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Butcanthic 文档智能服务                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    SSE/REST     ┌──────────────────┐                     │
│  │ Qt/C++ 客户端 │ ◄────────────► │  FastAPI (main)   │                     │
│  │ React 前端   │   双向通信      │  :8002            │                     │
│  └──────────────┘                 └──────────────────┘                     │
│                                          │                                  │
│                                          ▼                                  │
│                                   ┌──────────────┐                         │
│                                   │  LangGraph    │                         │
│                                   │  工作流引擎    │                         │
│                                   └──────────────┘                         │
│                                          │                                  │
│           ┌──────────────────────────────┼──────────────────────┐          │
│           ▼                              ▼                      ▼          │
│    ┌────────────┐               ┌────────────┐          ┌────────────┐    │
│    │ RAG Engine  │               │ Document   │          │ PPT Service │    │
│    │ (三路混合)  │               │ Service    │          │ (生成/分析) │    │
│    └────────────┘               └────────────┘          └────────────┘    │
│           │                              │                                │
│           ▼                              ▼                                │
│    ┌────────────┐               ┌────────────┐                           │
│    │ ChromaDB   │               │ Excel      │                           │
│    │ + BM25     │               │ Service    │                           │
│    │ + NetworkX │               │ + Pandas   │                           │
│    └────────────┘               └────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 19.2 LangGraph 工作流架构

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
| web_researcher | WebResearcher | 联网搜索（DuckDuckGo） |
| knowledge_librarian | KnowledgeLibrarian | 知识库检索 |
| generate_ppt | PPTGenAgent | PPT 生成 |
| critic_review_ppt | PPTCriticAgent | PPT 审查校验 |
| generate_summary | SummaryAgent | 长文总结 |
| auto_tagging | Auto_Tagging | 自动标签提取 |
| literature_guide | Literature_Guide | 文献导读 |

### 19.3 WorkflowState 状态定义

LangGraph 工作流的全局状态 `WorkflowState`：

| 字段 | 类型 | 说明 |
|------|------|------|
| file_path | str | 输入文件路径 |
| file_type | str | 文件类型（docx/xlsx/pptx） |
| user_instruction | str | 用户指令 |
| uploaded_files | List[Dict] | 上传文件列表 |
| global_context | str | 全局上下文 |
| original_html / current_html / filled_html | str | Word文档HTML内容 |
| empty_fields | List[Dict] | 待填充字段 |
| retrieved_context | List[Dict] | RAG检索结果 |
| retry_count / max_retries | int | 重试计数 |
| review_result / review_feedback | str | 审查结果与反馈 |
| generated_code / code_execution_log / code_execution_error | str | Excel代码生成相关 |
| ppt_data | dict | PPT数据 |
| task_intent | str | 任务意图 |
| messages | Annotated[Sequence[BaseMessage]] | 对话消息（累积追加） |
| user_id | str | 用户ID（用于RAG隔离） |

### 19.4 RAG 检索引擎

Butcanthic 内置三路混合检索引擎：

| 检索方式 | 技术 | Top-K | 说明 |
|----------|------|-------|------|
| 向量检索 | ChromaDB + BGE-M3 | 10 | 语义相似度检索 |
| 稀疏检索 | BM25 + jieba | 10 | 关键词精确匹配 |
| 图谱检索 | NetworkX + LLM | - | 实体关系推理（GraphRAG） |

三路召回结果去重合并后，经 BGE-Reranker-V2-m3 重排序，返回 Top-5。

**用户级隔离：** 每个用户拥有独立的 Chroma Collection（`kb_user_{user_id}`），数据物理隔离。

**嵌入模型配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| embedding model | BAAI/bge-m3 | 向量嵌入模型 |
| embedding dimension | 1024 | 向量维度 |
| reranker model | BAAI/bge-reranker-v2-m3 | 重排序模型 |
| embedding provider | SiliconFlow | 嵌入模型提供商 |

### 19.5 AI 模型配置

Butcanthic 使用 `ai_models_config.json` 配置 AI 模型提供商，支持多模型切换：

```json
{
  "default_model": "qwen-plus",
  "models": {
    "qwen-plus": {
      "provider": "aliyun",
      "api_key": "sk-xxx",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen-plus",
      "max_input_tokens": 997952,
      "max_output_tokens": 81920,
      "temperature": 0.0,
      "top_p": 0.1
    },
    "doubao-seed-1-6-flash": {
      "provider": "volcano",
      "api_key": "sk-xxx",
      "base_url": "https://ark.cn-beijing.volces.com/api/v3",
      "model_name": "doubao-seed-1-6-flash-250828",
      "max_input_tokens": 32000,
      "max_output_tokens": 9999
    }
  }
}
```

### 19.6 记忆管理

Butcanthic 支持对话记忆提取和持久化：

- **MemoryManager**：后台异步从用户指令中提取记忆三元组
- **会话保持**：通过 `thread_id` 实现跨轮对话记忆（LangGraph MemorySaver）
- **记忆存储**：用户级记忆持久化，后续对话可检索历史记忆

### 19.7 文件处理能力

| 文件类型 | 处理方式 | 输出 |
|----------|----------|------|
| .docx | HTML解析 → 字段提取 → RAG检索 → AI填充 → Critic审查 | 填充后的.docx |
| .xlsx | Pandas解析 → AI生成清洗代码 → 代码执行 → 自我纠错 | 清洗后的.xlsx |
| .pptx | python-pptx解析 → AI分析 | 分析报告 |
| 纯文本 | Supervisor调度 → 联网搜索/知识库检索 → PPT生成 → Critic审查 | PPT JSON / .pptx |

**Excel 自我纠错流程：**

```
DataAgent生成Python代码 → 执行代码 → 成功? → 下一步
                                    → 失败? → 追加错误日志 → 重新生成代码（最多3次）
```

### 19.8 Butcanthic Frontend

基于 React + Vite 的前端界面，提供 PPT 查看器和知识图谱可视化：

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.3+ | UI 框架 |
| Vite | 6.0+ | 构建工具 |
| ECharts | 6.1+ | 图表可视化（知识图谱、统计图） |
| echarts-for-react | 3.0+ | React ECharts 封装 |

**核心功能：**
- PPT 在线预览和编辑
- 知识图谱 ECharts 可视化
- 文档上传进度实时展示
- 多文件协同分析界面

---

## 20. Eruitah智能编程沙盒

### 20.1 架构概述

Eruitah智能编程沙盒是一个基于 **FastAPI + WebSocket** 的AI编程助手微服务，核心引擎对齐Claude Code的Agent Loop思想：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Eruitah 智能编程沙盒 v4                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    WebSocket     ┌──────────────────┐     API      ┌──────────┐
│  │ Qt/C++ 客户端 │ <─────────────> │  FastAPI (main)   │ ──────────> │  LLM API  │
│  │ Vue Web IDE  │   双向实时通信   │  main.py v4       │ <────────── │  Claude   │
│  └──────────────┘                  └──────────────────┘              │  GPT-4o   │
│                                           │                          └──────────┘
│                                           ▼                                        │
│                                    ┌──────────────┐                               │
│                                    │ agent_runner │                               │
│                                    │  (核心引擎)   │                               │
│                                    └──────────────┘                               │
│                                           │                                        │
│                    ┌──────────────────────┼──────────────────────┐                │
│                    ▼                      ▼                      ▼                │
│             ┌────────────┐        ┌────────────┐        ┌────────────┐          │
│             │bash_executor│        │file_editor │        │grep_tool   │          │
│             │ (命令执行)  │        │ (文件编辑) │        │ (代码搜索) │          │
│             └────────────┘        └────────────┘        └────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 20.2 核心功能

| 功能 | 说明 |
|------|------|
| AI编程助手 | 基于Claude/GPT-4o，自动编写、修改、调试代码 |
| 工具调用 | 5大基础工具 + 30+扩展工具（MCP/LSP/AST/语义搜索等） |
| 实时流式 | WebSocket双向通信，实时推送Agent思考过程 |
| 自愈机制 | 工具执行失败自动分析错误并重试 |
| 安全沙盒 | 危险命令拦截、路径越权检测、超时保护 |
| 多模型支持 | OpenAI兼容接口 + Anthropic Claude |
| 多智能体模式 | 极速/深度/SDD三种模式，红蓝对抗代码审查 |
| 任务管理 | 独立Git Worktree隔离，任务切换/合并/回退 |
| 会话回退 | Git指针+SQLite混合架构，支持任务级和步骤级回退 |
| 交互式终端 | PTY真实shell体验，支持resize和后台进程管理 |
| MCP客户端 | 动态加载第三方MCP Server工具 |
| 成本护栏 | Token计费追踪，预算超限自动停止 |

### 20.3 工具集详解

#### 20.3.1 bash - 命令执行器

```python
{
    "name": "bash",
    "description": "执行 shell 命令。用于编译代码、运行测试、查看文件等。",
    "parameters": {
        "command": "要执行的命令",
        "timeout_ms": "超时时间（毫秒），默认120000",
        "work_dir": "工作目录"
    }
}
```

**安全机制：**
- **危险命令拦截**：`rm -rf /`、`mkfs`、`dd of=/dev/`、Fork炸弹等
- **命令替换检测**：`$()`、反引号、`${}`变量替换
- **IFS注入检测**：防止绕过安全校验
- **路径越权检测**：限制在工作目录内操作
- **超时保护**：默认120秒，最大600秒
- **输出截断**：超过2000字符自动截断，防止Token爆炸

#### 20.3.2 file_edit - 文件编辑器

```python
{
    "name": "file_edit",
    "description": "使用 SEARCH/REPLACE 模式编辑文件",
    "parameters": {
        "file_path": "文件路径",
        "search_text": "要查找的文本（空字符串表示创建新文件）",
        "replace_text": "替换为的文本",
        "replace_all": "是否替换所有匹配"
    }
}
```

**核心特性：**
- **SEARCH/REPLACE模式**：局部替换而非全文件覆写
- **唯一性校验**：search_text必须在文件中唯一匹配（除非replace_all=True）
- **引号规范化**：自动处理弯引号与直引号的差异
- **Diff补丁**：生成unified diff格式变更展示

#### 20.3.3 file_read - 文件读取

```python
{
    "name": "file_read",
    "description": "读取文件内容，支持行号范围过滤",
    "parameters": {
        "file_path": "文件路径",
        "start_line": "起始行号（1-based），默认1",
        "end_line": "结束行号，None表示到末尾"
    }
}
```

**安全限制：**
- 文件超过1000行且没有指定行号范围时，拒绝读取
- 最大读取2000行
- 最大读取10 MiB文件
- 单行超过2000字符自动截断

#### 20.3.4 glob - 文件模式匹配

```python
{
    "name": "glob",
    "description": "使用 glob 模式查找文件",
    "parameters": {
        "pattern": "glob模式，如 **/*.py",
        "work_dir": "工作目录"
    }
}
```

**支持的glob模式：**
- `*`：匹配任意文件名（不含路径分隔符）
- `**`：递归匹配任意层目录
- `?`：匹配单个字符
- `[abc]`：匹配括号内任意字符

**默认忽略目录：** node_modules, .git, __pycache__, .venv, build, dist, target等

#### 20.3.5 grep - 正则搜索

```python
{
    "name": "grep",
    "description": "使用正则表达式搜索代码",
    "parameters": {
        "pattern": "正则表达式模式",
        "work_dir": "工作目录",
        "file_pattern": "文件过滤模式，如 *.py",
        "case_insensitive": "是否忽略大小写"
    }
}
```

**搜索引擎优先级：**
1. **ripgrep (rg)**：最快，默认尊重.gitignore，Rust多线程实现
2. **GNU grep**：次选，需要手动排除目录
3. **Python re**：最终回退，速度较慢但保证可用

### 20.4 Agent Loop核心流程

```
┌─────────────────────────────────────────────────────────────────────┐
│  run_agent(user_input)  →  Generator[dict]                          │
│                                                                     │
│  ┌──────────┐    调用 LLM     ┌──────────────┐    yield event      │
│  │ messages │ ─────────────→  │  大模型回复   │ ─────────────→ 前端  │
│  └──────────┘                 └──────────────┘                     │
│       ↑                           │                                │
│       │                    有 Tool Call?                            │
│       │                     /         \                            │
│       │                   是           否 (纯文本 → finish)          │
│       │                    │                                        │
│       │              执行 Python Tool                               │
│       │                    │                                        │
│       │              ┌─────┴─────┐                                  │
│       │              │ 成功/失败? │                                  │
│       │              └─────┬─────┘                                  │
│       │            成功 ↓     ↓ 失败(自愈!)                          │
│       │        追加 tool_result  追加错误消息作为 user 消息          │
│       │              ↓              ↓                              │
│       └──────────────┴──────────────┘  ← 回到循环顶部               │
│                                                                     │
│  最大 15 轮防止 Token 破产 + 死循环保护                              │
└─────────────────────────────────────────────────────────────────────┘
```

**自愈逻辑：**
- 工具执行抛出异常 → 不崩溃
- 将异常堆栈转为字符串 → 作为user消息喂回大模型
- 大模型分析错误 → 更换策略或修复参数 → 重试

### 20.5 多智能体模式

Eruitah 支持三种智能体运行模式，通过参数控制：

#### 20.5.1 极速模式（use_swarm=False）

单体 Agent 穿上专家外衣干活。Supervisor 路由器分析用户请求后，选择最合适的专家身份（预设或动态生成），Agent 以该专家身份执行任务。

**流程：**
```
用户请求 → Supervisor(CTO)审题 → 选择/生成专家身份 → Agent穿专家外衣执行 → 返回结果
```

**预设专家：**

| 专家ID | 名称 | 适用领域 |
|--------|------|----------|
| cpp_network_expert | C++高并发网络编程专家 | Muduo/Epoll/TCP-UDP/Reactor/RAII/智能指针 |
| db_expert | 数据库专家 | MySQL/Redis/SQL优化/事务/索引/分库分表 |
| qa_expert | 测试与质量保障专家 | 单元测试/集成测试/CI-CD/代码覆盖率/Mock |
| general_coder | 通用编程专家 | 常规脚本、Web开发、配置管理 |

**动态专家生成：** 当预设专家无法完美覆盖用户的长尾需求时，Supervisor 现场撰写 `custom_system_prompt`，动态生成最对口的专家。动态生成的专家必须包含：
1. 专家身份定义（"你是一位资深的 XXX 专家"）
2. 核心技能清单（3-8条，具体到技术栈和工具）
3. 工作原则（3-5条，约束代码风格和质量标准）
4. 与任务直接相关的领域知识提示

**多模态图片处理：** 当用户上传图片时，Supervisor 根据图片类型动态生成专家：
- 终端报错/IDE飘红 → 高级Debug与系统排错专家
- 网页UI/设计手稿 → 资深前端页面还原专家
- UML类图/架构图 → 后端架构师
- 代码截图 → 根据语言生成对应专家

#### 20.5.2 深度模式（use_swarm=True）

红蓝对抗模式，蓝军穿专家外衣写代码，红军从最佳实践角度挑刺。

**Coder-Reviewer 工作流：**

```
┌──────────┐    提交审查     ┌──────────┐
│  Coder   │ ──────────────→ │ Reviewer │
│ (全权限) │                  │ (只读)   │
└──────────┘ ←────────────── └──────────┘
              打回重写 / LGTM
```

**状态机：**
```
CODING → SUBMITTED → REVIEWING → LGTM (终态)
                              → REJECTED → CODING (循环)
                              → MAX_LOOPS (终态)
```

- **Coder（蓝军）**：拥有全部工具权限（bash/file_edit/file_read等），负责编写代码
- **Reviewer（红军）**：只读权限（file_read/grep/glob），从最佳实践角度审查代码质量
- **对抗循环**：Reviewer 审查后可打回（REJECTED），Coder 修改后重新提交，直到 LGTM 或达到最大循环次数

#### 20.5.3 SDD模式（skills包含"sdd"）

多智能体协作模式（Skills-Driven Development），通过 Agent Swarm P2P 网络实现多智能体协同工作。

#### 20.5.4 Supervisor路由

所有新任务先经过 Supervisor（CTO级别技术总监）审题，决定：
- 选择哪个预设专家（is_predefined: true）
- 还是动态生成专家（is_predefined: false）
- 判定执行环境（本地后端 vs WebContainer前端）
- 决定智能体模式（极速/深度/SDD）

### 20.6 任务管理系统

#### 20.6.1 核心设计

```
用户一句话 = 开启一个平行宇宙（独立任务）
AI 提炼标题 = 给这个平行宇宙贴个标签
记忆隔离 = 任务A的对话和代码，绝对不能串台到任务B
回退隔离 = 撤销任务A，只会把任务A相关的代码回滚，任务B毫发无损
```

**架构：** SessionManager = TaskRegistry（物理快照）+ TaskManager（会话记忆）的统一入口

#### 20.6.2 任务数据结构

```python
@dataclass
class TaskSession:
    id: str                    # 任务唯一ID
    summary: str               # AI提炼的任务标题
    work_dir: str              # 工作目录（独立Worktree）
    snapshot_path: str         # 物理快照路径
    messages_before: List[Dict] # 任务前的全局消息
    messages: List[Dict]       # 任务内对话消息
    created_at: float          # 创建时间
    status: str = "active"     # 任务状态：active/completed/rolled_back
    current_turn: int = 0      # 当前轮次
```

#### 20.6.3 核心操作

| 操作 | 说明 |
|------|------|
| register_task() | 新任务注册 + 强制物理快照 |
| get_or_create_session() | 获取/创建任务会话 |
| switch_session() | 切换任务（保存当前 + 加载目标） |
| rollback_session() | 物理级回滚（文件还原 + 记忆截断） |
| delete_session() | 删除任务及其Worktree |

#### 20.6.4 会话持久化

- **session_storage.py**：会话持久化存储
- 任务数据存储在 `.tasks/` 目录
- 快照数据存储在 `.eruitah_snapshots/` 目录
- 忽略模式：node_modules, __pycache__, .git, venv, dist, build等

### 20.7 回退系统（Rewind System）

#### 20.7.1 混合指针架构

```
Git 存肉体，SQLite 存灵魂（指针映射）

❌ 旧方案: 每轮存全量文件快照 → O(N^2) 磁盘 I/O 爆炸
✅ 新方案: 每轮只存 Git Commit Hash → O(1) 极致轻量
```

**检查点数据结构：**
```python
@dataclass
class Checkpoint:
    session_id: str          # 会话ID
    turn: int                # 轮次
    timestamp: float         # 时间戳
    messages: List[Dict]     # 灵魂：对话记忆
    git_commit: str = ""     # 肉体：Git指针（40字符）
    diff_stat: str = ""      # 前端展示用diff摘要
    description: str = ""    # 检查点描述
    code_diff: str = ""      # 代码差异
```

**时光倒流：**
1. 从SQLite查出目标轮次的git_commit
2. 恢复灵魂：把过去的messages塞回给大模型
3. 恢复肉体：`git reset --hard <git_commit>`

**优势：**
- 磁盘：从O(N^2)降到O(N)，不再存文件内容
- 查询：Git Commit Hash只有40字符
- 并发：多Agent同时存快照不会击穿I/O
- 增量：Git内部已经是增量存储（delta compression）

#### 20.7.2 回退操作

| 操作 | 说明 |
|------|------|
| rollback_session(task_id) | 任务级回退：恢复到任务创建前的快照 |
| rollback_step_session(session_id, turn) | 步骤级回退：恢复到指定轮次的检查点 |
| preview_rollback(session_id, turn) | 预览回退：展示目标检查点的diff，不实际执行 |
| view_checkpoint(session_id, turn) | 查看检查点：展示指定轮次的代码差异和对话 |

**自动检查点：** 每次文件编辑（file_edit）和bash执行（bash）后自动创建检查点。

**检查点存储：** SQLite数据库 `.checkpoints/rewind.db`

### 20.8 沙盒管理器（Sandbox Manager）

#### 20.8.1 Git Worktree隔离架构

```
主仓库 (workspace_dir) ── 永远停留在 master/main 分支
  ├── .git/
  └── agent-worktrees/         ← 与主仓库同级
      ├── task_abc123/         ← 任务A的专属物理目录（独立分支 task/task_abc123）
      ├── task_def456/         ← 任务B的专属物理目录（独立分支 task/task_def456）
      ├── warmup_a1b2/        ← 预热池中的待命worktree（分支 warmup/a1b2）
      ├── warmup_c3d4/        ← 预热池中的待命worktree（分支 warmup/c3d4）
      └── warmup_e5f6/        ← 预热池中的待命worktree（分支 warmup/c3d4）
```

#### 20.8.2 WarmPool预热池

后台守护线程持续维护 pool_size=3 的预热池。新任务到来时，直接 pop 预热好的 worktree，重命名分支即可，耗时约0ms。缓存击穿时降级为同步创建（Slow Path）。

#### 20.8.3 三级回退

| 级别 | 操作 | 说明 |
|------|------|------|
| L1 | rollback_task_step | `git reset --hard HEAD~N`（worktree内） |
| L2 | remove_task_workspace | `git worktree remove` + `branch -D` |
| L3 | revert_merged_task | `git revert -m 1 <merge_commit>`（主仓库） |

#### 20.8.4 任务合并

- **merge_session(task_id)**：将任务分支合并到主干（master/main）
- **冲突检测**：合并前自动检测冲突，有冲突时提示用户
- **revert_merged_task(task_id)**：撤销已合并的任务（`git revert -m 1`）

### 20.9 系统命令

WebSocket端点支持的系统命令：

| 命令 | 说明 | 参数 |
|------|------|------|
| list_tasks | 列出所有任务 | 无 |
| rollback_task | 回退任务 | task_id |
| preview_rollback | 预览回退 | task_id, turn |
| view_checkpoint | 查看检查点 | task_id, turn |
| stop_agent | 停止Agent | session_id |
| switch_task | 切换任务 | task_id |
| merge_task | 合并任务到主干 | task_id |
| revert_merged_task | 撤销已合并任务 | task_id |
| delete_task | 删除任务 | task_id |
| list_checkpoints | 列出检查点 | task_id |
| list_mcp_services | 列出MCP服务 | 无 |

### 20.10 交互式终端

#### 端点：`/ws/terminal`

提供真正的交互式shell体验，基于PTY（伪终端）实现。

**核心流程：**
```
前端 Xterm.js:
  terminal.onData(data => ws.send({type: 'input', data}))
       │
       ▼
Python 后端:
  1. 创建 PTY 进程 (bash/zsh)
  2. 收到前端输入 -> pty.write(data)
  3. pty 输出 -> ws.send({type: 'output', data})
       │
       ▼
前端 Xterm.js:
  收到输出 -> terminal.write(data)
```

**协议：**

| 消息类型 | 方向 | 格式 | 说明 |
|----------|------|------|------|
| input | 客户端→服务端 | `{"type": "input", "data": "ls\n"}` | 用户输入 |
| output | 服务端→客户端 | `{"type": "output", "data": "..."}` | 终端输出 |
| resize | 客户端→服务端 | `{"type": "resize", "cols": 80, "rows": 24}` | 终端尺寸变更 |
| started | 服务端→客户端 | `{"type": "started", "pid": 12345}` | 终端启动 |

**后台进程管理：** `BackgroundProcessManager` 支持Agent启动/监控/停止后台服务（如Web Server）。

### 20.11 MCP客户端

#### 20.11.1 架构

MCP（Model Context Protocol）客户端让Agent支持动态加载第三方MCP Server提供的工具。

**核心流程：**
```
mcp.json 配置文件
  → Agent启动时读取
  → 为每个Server启动子进程（stdio通信）
  → 发送 initialize + tools/list 请求
  → 获取Server提供的Tools
  → 合并到Agent的工具列表中
```

**动态加载：** Agent运行时根据需求自主开启新的MCP Server：
```
用户: "查看我的GitHub提醒"
→ Agent调用mcp_dynamic_load("github")
→ 后端拉起GitHub MCP容器
→ Agent获得GitHub工具能力
→ 执行查询并返回结果
```

#### 20.11.2 MCP服务配置

`mcp.json` 定义了多个MCP Server：

| 服务名 | 说明 | 用途 |
|--------|------|------|
| filesystem | 文件系统访问 | 读写文件、目录操作 |
| github | GitHub管理 | 仓库/Issue/PR管理 |
| puppeteer | 浏览器自动化 | 网页截图、表单填写、爬虫 |
| postgres | PostgreSQL查询 | 数据库查询和管理 |
| memory | 知识图谱持久化记忆 | 跨会话知识存储和检索 |
| sequential-thinking | 结构化推理 | 复杂问题的分步推理 |

### 20.12 其他工具

| 工具 | 文件 | 说明 |
|------|------|------|
| 自动测试 | auto_test_tool.py | 自动生成和运行测试用例 |
| 浏览器视觉 | browser_vision_tool.py | 浏览器截图和视觉分析（依赖虚拟桌面） |
| Computer Use | computer_use_tool.py | 桌面操作自动化（依赖虚拟桌面） |
| LSP语言服务 | lsp_tool.py / lsp_client.py | 代码补全、跳转定义、诊断 |
| 语义搜索 | semantic_search_tool.py | 基于向量的代码语义搜索 |
| Tree-sitter索引 | tree_sitter_index.py | 基于Tree-sitter的代码结构索引 |
| AST分析 | ast_tool.py | Python AST语法树分析 |
| 截图 | screenshot_tool.py | 屏幕截图工具 |
| Notebook | notebook_tool.py | Jupyter Notebook交互 |
| 成本护栏 | cost_guardrails.py | Token计费追踪，预算超限自动停止 |
| Token预算 | token_budget.py | Token预算管理和分配 |
| 产物构建 | artifact_builder.py | 代码产物构建和打包 |
| 提示词缓存 | prompt_caching.py | 提示词缓存优化 |
| 自蒸馏 | self_distill.py | 模型自蒸馏优化 |
| 自主计算 | compute_autonomy.py | Agent自主计算调度 |
| Git工具 | git_tool.py | Git操作封装 |
| 用户交互 | ask_user_tool.py | Agent主动向用户提问 |
| 交互式调试 | interactive_debugger_tool.py | 交互式代码调试 |
| 元工具 | meta_tool.py | 工具元信息管理 |
| 记忆管理 | memory_manager.py / memory_store.py | 对话记忆管理 |
| 提示词构建 | prompt_builder.py | 动态提示词构建 |
| 动态顺序思维 | dynamic_sequentialthinking.py | 动态分步推理 |
| Theseus重写 | theseus_rewrite.py | 代码重写引擎 |
| 容器池 | container_pool.py | Docker容器池管理 |
| 影子沙盒 | shadow_sandbox.py | 影子沙盒隔离执行 |

### 20.13 Agent子进程模式

#### 20.13.1 架构

```
┌──────────────────┐  asyncio.Queue  ┌──────────────┐  multiprocessing.Queue  ┌──────────────────┐
│  WebSocket (async) │ ◄──────────── │  Bridge 线程  │ ◄──────────────────── │  Agent 子进程     │
│  主进程 - 不变      │ ────────────► │  轻量级转发    │                        │  run_agent()     │
└──────────────────┘                 └──────────────┘                         └──────────────────┘
```

**核心优势：**
- 进程可被SIGKILL瞬间强杀，不受GIL和网络阻塞影响
- 沙盒隔离：Agent崩溃不会影响主进程
- 令行禁止：点停止 → SIGTERM(1s) → SIGKILL，灰飞烟灭

**关键设计：**
- `run_agent()` 在 yield ask_user 后直接return（生成器终止）
- 子进程不需要双向IPC，ask_user后子进程自然结束
- 父进程处理用户回答后，启动新子进程继续执行

**启用方式：** 环境变量 `ERUITAH_USE_SUBPROCESS=true`（默认开启）

### 20.14 VNC/屏幕功能

Eruitah 支持虚拟桌面环境，为 `computer_use_tool.py` 和 `browser_vision_tool.py` 提供图形界面操作能力。

**架构：**
```
Xvfb (虚拟X11显示) → x11vnc (可选VNC服务器) → 浏览器/客户端远程查看
```

**环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| ERUITAH_ENABLE_VNC | false | 是否启用VNC服务器 |
| ERUITAH_SCREEN_WIDTH | 1280 | 虚拟屏幕宽度 |
| ERUITAH_SCREEN_HEIGHT | 720 | 虚拟屏幕高度 |

**Docker端口：** VNC服务默认映射到5900端口。

### 20.15 成本护栏

`cost_guardrails.py` 提供Token级别的成本追踪和预算控制：

**支持模型定价：**

| 模型 | 输入价格（$/1K tokens） | 输出价格（$/1K tokens） |
|------|------------------------|------------------------|
| gpt-4o | 0.0025 | 0.01 |
| claude-sonnet-4 | 0.003 | 0.015 |
| deepseek-chat | 0.00014 | 0.00028 |
| qwen-plus | 0.0008 | 0.002 |

**SessionCostTracker：**
- 默认预算上限：5.0 USD
- 每次LLM调用后自动累计成本
- 超过预算自动停止Agent执行
- 记录成本历史，支持查询

### 20.16 WebSocket协议

#### 端点：`/ws/coding`（单任务模式）

**客户端发送：**

```json
{
    "task": "写一个Python二叉树实现",
    "model": "gpt-4o",
    "provider": "openai",
    "work_dir": "/tmp/eruitah-sandbox",
    "max_turns": 15
}
```

**服务端推送事件：**

| 事件类型 | 格式 | 说明 |
|----------|------|------|
| status | `{"type": "status", "data": "Agent 正在思考..."}` | 状态更新 |
| message | `{"type": "message", "content": "..."}` | 大模型纯文本回复 |
| tool_start | `{"type": "tool_start", "tool_name": "bash", "args": {...}}` | 工具开始执行 |
| tool_end | `{"type": "tool_end", "tool_name": "bash", "result": "...", "is_error": false}` | 工具执行结束 |
| code_stream | `{"type": "code_stream", "content": "..."}` | 代码流式推送（打字机效果） |
| file_updated | `{"type": "file_updated", "file_path": "...", "file_name": "...", "new_code": "...", "language": "py"}` | 文件更新事件 |
| finish | `{"type": "finish", "data": "..."}` | 任务完成 |
| error | `{"type": "error", "data": "..."}` | 错误信息 |

#### 端点：`/ws/coding/persistent`（持久连接多任务模式）

**客户端发送：**

```json
{"action": "run", "task": "写一个二叉树", "model": "gpt-4o"}
{"action": "ping"}
{"action": "close"}
```

**服务端响应：**

```json
{"type": "pong"}
{"type": "finish", "data": "...", "task_id": "xxx"}
```

### 20.17 REST API

#### 同步执行：`POST /api/v1/execute`

**请求体：**

```json
{
    "prompt": "写一个Python快速排序实现",
    "work_dir": "/tmp/eruitah-sandbox",
    "max_turns": 15,
    "model": "gpt-4o",
    "provider": "openai"
}
```

**响应体：**

```json
{
    "success": true,
    "message": "任务完成",
    "events": [
        {"type": "status", "data": "..."},
        {"type": "tool_start", "tool_name": "file_edit", ...},
        {"type": "tool_end", ...},
        {"type": "finish", "data": "..."}
    ]
}
```

#### 文件管理：`GET /api/v1/files`

```
GET /api/v1/files?path=/tmp/eruitah-sandbox
```

**响应：**

```json
{
    "files": ["main.py", "utils/helper.py", "test_main.py"]
}
```

#### 读取文件：`GET /api/v1/file`

```
GET /api/v1/file?path=/tmp/eruitah-sandbox/main.py
```

**响应：**

```json
{
    "content": "def quicksort(arr):\n    ...",
    "path": "/tmp/eruitah-sandbox/main.py"
}
```

#### 健康检查：`GET /api/v1/health`

```json
{
    "status": "ok",
    "sandbox_dir": "/tmp/eruitah-sandbox",
    "api_provider": "openai"
}
```

### 20.18 Qt客户端对接示例

```cpp
void CodingLabWindow::onTextMessageReceived(QString message) {
    QJsonObject obj = QJsonDocument::fromJson(message.toUtf8()).object();
    QString type = obj["type"].toString();

    if (type == "tool_start") {
        QString toolName = obj["tool_name"].toString();
        ui->statusLabel->setText("正在执行: " + toolName);
    }
    else if (type == "tool_end") {
        bool isError = obj["is_error"].toBool();
        QString result = obj["result"].toString();
        if (isError) {
            appendTerminalLog("[ERROR] " + result);
        } else {
            appendTerminalLog(result);
        }
    }
    else if (type == "code_stream") {
        QString chunk = obj["content"].toString();
        ui->codeEditor->insertPlainText(chunk);
    }
    else if (type == "file_updated") {
        QString newCode = obj["new_code"].toString();
        QString language = obj["language"].toString();
        ui->codeEditor->setPlainText(newCode);
        ui->codeEditor->setLanguage(language);
    }
    else if (type == "finish") {
        ui->statusLabel->setText("任务完成");
    }
}
```

---

## 21. Coding Agent UI（Vue Web IDE）

### 21.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.4.0 | 前端框架（Composition API） |
| Vite | ^5.4.0 | 构建工具 |
| Pinia | ^2.1.7 | 状态管理 |
| Monaco Editor | ^0.45.0 | 代码编辑器 |
| @guolao/vue-monaco-editor | ^1.5.4 | Monaco Vue组件封装 |
| @xterm/xterm | ^5.5.0 | 终端模拟器 |
| @xterm/addon-fit | ^0.10.0 | 终端自适应尺寸 |
| Mermaid | ^11.15.0 | 图表渲染（流程图/时序图等） |
| @webcontainer/api | ^1.3.0 | 浏览器端Node.js运行时 |
| Tailwind CSS | ^3.4.0 | 原子化CSS框架 |

### 21.2 组件说明

| 组件 | 文件 | 说明 |
|------|------|------|
| App.vue | src/App.vue | 应用根组件，布局编排 |
| ChatPanel.vue | src/components/ChatPanel.vue | AI聊天面板，与Agent对话交互 |
| CodeEditor.vue | src/components/CodeEditor.vue | Monaco代码编辑器，语法高亮+代码补全 |
| TerminalPanel.vue | src/components/TerminalPanel.vue | xterm终端面板，交互式shell |
| FileTree.vue | src/components/FileTree.vue | 文件树，浏览和打开项目文件 |
| TaskList.vue | src/components/TaskList.vue | 任务列表，管理多个编程任务 |
| ToolBar.vue | src/components/ToolBar.vue | 工具栏，快捷操作入口 |
| SkillPanel.vue | src/components/SkillPanel.vue | 技能面板，Agent技能展示和触发 |
| DirPicker.vue | src/components/DirPicker.vue | 目录选择器，选择工作目录 |
| PixelPet.vue | src/components/PixelPet.vue | 像素宠物，Agent状态可视化（精灵图动画） |

### 21.3 状态管理

**stores/agent.js** 使用Pinia管理全局状态：

| 状态 | 类型 | 说明 |
|------|------|------|
| ws | shallowRef | WebSocket连接实例 |
| connected | ref | 连接状态 |
| messages | ref | 聊天消息列表 |
| files | ref | 文件树数据 |
| basePath | ref | 当前工作目录 |
| currentFile | ref | 当前打开的文件 |
| currentCode | ref | 当前文件代码内容 |
| openFiles | ref | 已打开的文件标签页 |
| isRunning | ref | Agent是否正在运行 |
| status | ref | 当前状态文本 |
| currentTool | ref | 当前执行的工具 |
| mermaidDiagrams | ref | Mermaid图表列表 |
| costInfo | ref | 成本信息 |
| taskList | ref | 任务列表 |
| currentTaskId | ref | 当前任务ID |
| petStatus | ref | 像素宠物状态（IDLE/RUNNING/THINKING等） |
| agentState | ref | Agent状态 |
| checkpointList | ref | 检查点列表 |
| mcpServices | ref | MCP服务列表 |

### 21.4 工具类

#### webcontainerManager.js

WebContainer管理器，单例模式，负责在浏览器端启动Node.js运行时：

- **boot()**：启动WebContainer实例
- **runCommand()**：在WebContainer中执行命令
- **onPreviewUrl**：监听预览URL（前端项目实时预览）
- **onServerReady**：监听服务就绪事件

**用途：** 前端项目（Vue/React/HTML）可在浏览器端直接运行，无需后端Docker。

#### mermaidRenderer.js

Mermaid图表渲染器，提供暗色主题配置：

- **renderMermaid(code)**：渲染Mermaid代码为SVG
- 主题：dark，紫色系配色
- 字体：JetBrains Mono / Fira Code
- 支持流程图、时序图、甘特图等

### 21.5 开发代理配置

**vite.config.js** 配置了开发环境的反向代理：

| 代理路径 | 目标 | 说明 |
|----------|------|------|
| /ws/simple-ide | http://127.0.0.1:8001/ws/coding | 简化IDE WebSocket（重写路径） |
| /ws/coding | http://127.0.0.1:8001 | 编码Agent WebSocket |
| /ws/terminal | http://127.0.0.1:8001 | 交互式终端WebSocket |
| /api | http://127.0.0.1:8001 | REST API代理 |

**COOP/COEP头：** 配置了 `Cross-Origin-Embedder-Policy: require-corp` 和 `Cross-Origin-Opener-Policy: same-origin`，以支持WebContainer的SharedArrayBuffer需求。

**构建优化：**
- Monaco Editor 和 xterm.js 独立分包（manualChunks）
- chunk大小警告阈值：1500KB

---

## 22. Protobuf RPC Bridge

### 22.1 架构概述

Protobuf RPC Bridge 实现了 C++ ↔ Java ↔ Python 三语言的高性能RPC通信，替代部分Redis Pub/Sub通信：

```
┌──────────────┐     TCP/Protobuf      ┌──────────────┐     TCP/Protobuf      ┌──────────────┐
│  C++ ChatServer│ ◄──────────────────► │  Java AI服务  │ ◄──────────────────► │ Python 沙盒   │
│  (rpc_channel) │                      │ (InternalRpc) │                      │ (rpc_server)  │
│  (protobuf_    │                      │ (ProtobufRpc) │                      │ (streaming_   │
│   codec)       │                      │ (RouterHandler)│                     │  rpc_server)  │
└──────────────┘                       └──────────────┘                      └──────────────┘
```

### 22.2 Proto定义（chat.proto）

#### 22.2.1 聊天核心

| 消息类型 | 说明 |
|----------|------|
| ChatRequest | 聊天请求（userId, botId, message, voiceUrl, metadata等） |
| ChatResponse | 聊天响应（message, voiceUrl, msgType, metadata等） |

#### 22.2.2 群聊

| 消息类型 | 说明 |
|----------|------|
| GroupChatRequest | 群聊请求（groupId, senderId, content, aiBotIds） |
| GroupChatResponse | 群聊响应（groupId, botId, content） |

#### 22.2.3 伴读服务

| 消息类型 | 说明 |
|----------|------|
| CompanionReadRequest | 伴读请求（userId, action, text） |
| CompanionReadResponse | 伴读响应（audioUrl, explanationText） |

#### 22.2.4 考情大屏

| 消息类型 | 说明 |
|----------|------|
| DashboardRequest/Response | 雷达图+活跃度数据 |
| DashboardSummaryRequest/Response | 考情摘要（avgMastery, strongestSubject等） |
| WeeklyReportRequest/Response | AI周报 |

#### 22.2.5 PDF解析

| 消息类型 | 说明 |
|----------|------|
| PdfParseRequest | PDF解析请求（pdf_data bytes, filename） |
| PdfParseResponse | PDF解析响应（content, pageCount） |

#### 22.2.6 编程沙盒

| 消息类型 | 说明 |
|----------|------|
| SandboxExecuteRequest | 沙盒执行请求（prompt, workDir, model, provider, apiKey等） |
| SandboxExecuteResponse | 沙盒执行响应（sessionId, turnsUsed, finalResult） |
| SandboxTaskRequest | 沙盒任务请求（action, taskId, workDir） |
| SandboxTaskResponse | 沙盒任务响应（action, taskId, data） |
| SandboxToolEvent | 沙盒工具事件（eventType, toolName, argsJson, result等） |

#### 22.2.7 Agent Swarm P2P网络

| 消息类型 | 说明 |
|----------|------|
| SwarmMessage | P2P网络消息（REGISTER/HEARTBEAT/BROADCAST/DIRECT/HELP_REQUEST等） |
| SwarmAgentNode | 智能体节点信息（agentId, capabilities, specialties, status） |
| SwarmRegisterRequest/Response | 节点注册 |
| SwarmHelpRequest/Response | 跨节点求助 |
| SwarmNodeListResponse | 节点列表 |

#### 22.2.8 内部路由服务

**InternalRouterService** 定义了5个RPC方法：

| 方法 | 说明 |
|------|------|
| ForwardToJava | C++→Java请求转发（同步RPC） |
| PushToClient | Java→C++消息推送（私聊/群聊/通知） |
| StreamToClient | Java→C++流式推送（流式聊天） |
| UpdateCareerProfile | 更新职业档案 |
| EmitSkillEvent | 发射技能事件 |

**InternalMsgType枚举：**

| 类型值 | 说明 |
|--------|------|
| CHAT_PRIVATE | 私聊消息 |
| CHAT_GROUP | 群聊消息 |
| AI_AT_MENTION | AI@提及 |
| COMPANION_READ | 伴读服务 |
| DASHBOARD_QUERY/PUSH | 考情大屏查询/推送 |
| VOICE_CHAT | 语音聊天 |
| SANDBOX_EXECUTE | 沙盒执行 |
| SKILL_EVENT | 技能事件 |

#### 22.2.9 RPC消息封装

**RpcMessage** 是所有RPC通信的统一封装：

| 字段 | 类型 | 说明 |
|------|------|------|
| type | enum | REQUEST/RESPONSE/ERROR/STREAM/STREAM_END |
| id | int64 | 消息唯一ID |
| service_name | string | 服务名称 |
| method_name | string | 方法名称 |
| payload | bytes | Protobuf序列化的业务数据 |
| error_code | int32 | 错误码 |
| error_desc | string | 错误描述 |

### 22.3 C++端

| 文件 | 说明 |
|------|------|
| rpc_channel.h / rpc_channel.cc | RPC通道，管理连接和请求分发 |
| protobuf_codec.h / protobuf_codec.cc | Protobuf编解码器，处理消息序列化/反序列化 |
| chat_server.h / chat_server.cc | C++ RPC服务器，处理来自Java/Python的RPC请求 |
| main.cc | C++ RPC入口 |
| crosslang_test.cc | 跨语言测试 |

### 22.4 Java端

| 文件 | 说明 |
|------|------|
| JavaBackendServer.java | Java RPC服务器（Netty实现） |
| RpcMessageHandler.java | RPC消息分发处理器 |
| ProtobufEncoder.java | Protobuf编码器（Netty ChannelHandler） |
| ProtobufDecoder.java | Protobuf解码器（Netty ChannelHandler） |
| ChatService.java | 聊天服务接口 |
| AIChatService.java | 聊天服务实现 |

### 22.5 Python端

| 文件 | 说明 |
|------|------|
| bridge/rpc_server.py | Python RPC服务器（async实现） |
| bridge/streaming_rpc_server.py | 流式RPC服务器（支持Server Streaming） |
| bridge/rpc_client.py | Python RPC客户端 |
| bridge/codec.py | 编解码器 |
| services/swarm_bridge.py | Swarm P2P桥接服务 |
| services/sandbox_bridge.py | 沙盒桥接服务 |
| services/sandbox_adapter.py | 沙盒适配器 |
| main.py | Python RPC入口 |

---

## 23. Docker Compose 部署

### 23.1 服务架构

系统通过 Docker Compose 编排 7 个服务（Butcanthic 需单独部署）：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                                 │
│                                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                 │
│  │  MySQL  │  │  Redis  │  │  Neo4j  │     基础设施层                    │
│  │ :3306   │  │ :6379   │  │ :7474   │                                 │
│  └─────────┘  └─────────┘  └─────────┘                                 │
│       │            │            │                                       │
│       ▼            ▼            ▼                                       │
│  ┌──────────────────────────────────────┐                               │
│  │        ChatServer (C++)              │     通讯网关层                  │
│  │        :6000(TCP) :8888(RPC)         │                               │
│  └──────────────────────────────────────┘                               │
│       │            │                                                    │
│       ▼            ▼                                                    │
│  ┌─────────────────────┐  ┌─────────────────────┐                      │
│  │   AI Service (Java) │  │   Sandbox (Python)   │   业务服务层          │
│  │   :8081 :9999(RPC)  │  │   :8001 :5900(VNC)   │                      │
│  └─────────────────────┘  └─────────────────────┘                      │
│       │            │            │                                       │
│       ▼            ▼            ▼                                       │
│  ┌──────────────────────────────────────┐                               │
│  │          Nginx (反向代理)             │     统一入口层                  │
│  │          :80(HTTP) :8000(TCP)        │                               │
│  └──────────────────────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 23.2 服务清单

| 服务 | 镜像/构建 | 端口映射 | 依赖 |
|------|-----------|----------|------|
| mysql | mysql:8.0 | 3306:3306 | 无 |
| redis | redis/redis-stack:latest | 6379:6379 | 无 |
| neo4j | neo4j:latest | 7474:7474, 7687:7687 | 无 |
| chatserver | Dockerfile.chatserver | 6000:6000, 8888:8888 | mysql, redis |
| sandbox | eruitah-sandbox/Dockerfile | 8001:8001, 5900:5900 | 无 |
| ai-service | ai-service/Dockerfile | 8081:8081, 9999:9999 | mysql, redis, neo4j, sandbox, chatserver |
| nginx | nginx:1.25-alpine | 80:80, 8000:8000 | chatserver, ai-service, sandbox |

### 23.3 一键部署

```bash
# 克隆项目
cd /home/xmy/code

# 配置环境变量（可选，有默认值）
cp .env.example .env
# 编辑 .env 填入 API Key 等

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f ai-service
docker-compose logs -f sandbox
```

### 23.4 关键环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| MYSQL_ROOT_PASSWORD | xieming562 | MySQL root密码 |
| REDIS_PASSWORD | 123456 | Redis密码 |
| NEO4J_PASSWORD | 12345678 | Neo4j密码 |
| OPENAI_API_KEY | （空） | OpenAI/兼容API密钥 |
| OPENAI_BASE_URL | https://token-plan-cn.xiaomimimo.com/v1 | API基础URL |
| ERUITAH_API_PROVIDER | openai | 沙盒API提供商 |
| ERUITAH_MODEL_OPENAI | mimo-v2.5 | 沙盒OpenAI模型 |
| ERUITAH_MODEL_ANTHROPIC | claude-sonnet-4-20250514 | 沙盒Anthropic模型 |
| ERUITAH_ENABLE_VNC | false | 是否启用VNC |
| ERUITAH_SCREEN_WIDTH | 1280 | 虚拟屏幕宽度 |
| ERUITAH_SCREEN_HEIGHT | 720 | 虚拟屏幕高度 |

### 23.5 数据持久化

Docker Compose 使用命名卷持久化数据：

| 卷名 | 挂载点 | 说明 |
|------|--------|------|
| mysql-data | /var/lib/mysql | MySQL数据 |
| redis-data | /data | Redis数据 |
| neo4j-data | /data | Neo4j数据 |
| neo4j-logs | /logs | Neo4j日志 |
| audio-storage | /tmp/audio | 语音文件存储 |

**主机目录挂载：**

| 主机路径 | 容器路径 | 说明 |
|----------|----------|------|
| /tmp/eruitah-sandbox | /tmp/eruitah-sandbox | 沙盒工作目录 |
| /tmp/agent-worktrees | /tmp/agent-worktrees | Agent Worktree目录 |
| ./coding-agent-ui/dist | /app/coding-agent-ui/dist:ro | Web IDE静态文件（只读） |
| ./docker/mysql/init.sql | /docker-entrypoint-initdb.d/init.sql | MySQL初始化脚本 |
| ./docker/nginx/nginx.conf | /etc/nginx/nginx.conf:ro | Nginx配置（只读） |

### 23.6 健康检查

| 服务 | 检查方式 | 间隔 | 超时 | 重试 |
|------|----------|------|------|------|
| mysql | mysqladmin ping | 10s | 5s | 10 |
| redis | redis-cli ping | 10s | 5s | 5 |
| neo4j | service_started | - | - | - |

---

## 24. Nginx 反向代理

### 24.1 架构概述

Nginx 作为统一入口，将外部请求路由到后端各服务：

```
客户端 → Nginx(:80/:8000) → AI Service(:8081) / Sandbox(:8001) / ChatServer(:6000)
```

### 24.2 路由规则

#### HTTP路由（端口80）

| 路径 | 后端 | 说明 |
|------|------|------|
| /api/ | ai-service:8081 | Java AI服务REST API |
| /audio/ | ai-service:8081 | 语音文件访问 |
| /ws/ai/ | ai-service:8081 | AI WebSocket（升级） |
| /ws/voice/ | ai-service:8081 | 语音WebSocket（升级） |
| /ws/ | ai-service:8081 | 通用WebSocket（升级） |
| /sandbox/ws/coding | sandbox:8001 | 沙盒编码WebSocket（升级） |
| /sandbox/ws/terminal | sandbox:8001 | 沙盒终端WebSocket（升级） |
| /sandbox/ | sandbox:8001 | 沙盒REST API和静态文件 |
| /ide | sandbox:8001 | Web IDE页面 |
| /butcanthic/ | butcanthic:8002 | Butcanthic 文档智能服务REST API |
| /butcanthic/ws/ | butcanthic:8002 | Butcanthic WebSocket（升级） |
| /assets/ | sandbox:8001 | 静态资源（缓存30天） |
| /api/v1/ | sandbox:8001 | 沙盒REST API |

#### TCP路由（端口8000）

| 端口 | 后端 | 说明 |
|------|------|------|
| 8000 | chatserver:6000 | C++ ChatServer TCP连接 |

### 24.3 WebSocket配置

所有WebSocket路径均配置了升级头：

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

- **读写超时**：3600秒（1小时），防止长时间WebSocket连接被断开
- **Connection升级映射**：通过 `map $http_upgrade $connection_upgrade` 动态设置

### 24.4 超时配置

| 场景 | 读写超时 | 说明 |
|------|----------|------|
| REST API | 300s | 普通HTTP请求 |
| WebSocket | 3600s | 长连接WebSocket |
| TCP代理 | 300s | ChatServer TCP连接 |
| TCP连接超时 | 5s | TCP连接建立超时 |

### 24.5 其他配置

- **client_max_body_size**: 50m（支持大文件上传，如PDF/音频）
- **tcp_nodelay**: on（TCP代理禁用Nagle算法，降低延迟）
- **静态资源缓存**: /assets/ 路径设置30天过期，Cache-Control: public, immutable
