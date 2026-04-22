# AI Service 用户手册

## 1. 项目简介

AI Service 是一个面向 **408计算机考研** 的智能辅导后端服务，基于 Spring Boot 3.2 + Spring AI 构建。系统集成了多个AI角色、RAG知识检索、语音交互、知识图谱、多智能体编排等核心能力，为考研学生提供全方位的AI辅助学习体验。

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

**处理流程：** 下载音频 → ASR语音识别 → LLM生成回复 → TTS语音合成 → 返回文字+语音

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

## 15. 项目结构

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
│   │   └── RealtimeVoiceWebSocketHandler.java  # 实时语音WebSocket
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
    // 投递到Redis Stream: ai_task_stream
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

### 17.3 网络通信设计

**ChatClient类** 采用事件驱动架构：

```cpp
// 连接信号和槽 - 异步事件处理模式
connect(socket, &QTcpSocket::connected, this, [=]() {
    isConnected = true;
    emit connectionStateChanged(true);
});

connect(socket, &QTcpSocket::readyRead, this, &ChatClient::onReadyRead);
```

**消息发送格式：**

```cpp
void ChatClient::sendJsonMessage(const QJsonObject &message) {
    // 长度前缀法解决粘包问题
    qint32 length = jsonData.size();
    QByteArray lengthBytes;
    QDataStream stream(&lengthBytes, QIODevice::WriteOnly);
    stream.setByteOrder(QDataStream::BigEndian);  // 大端字节序
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
    #undef byte  // 防止与Qt冲突
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
├── protobuf-rpc-bridge/                  # Protobuf RPC桥接
│   └── cpp/
│       ├── include/
│       └── CMakeLists.txt
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
├── .env                                  # 环境变量配置文件
└── *.md                                  # 文档文件
```

---

## 19. Eruitah智能编程沙盒

### 19.1 架构概述

Eruitah智能编程沙盒是一个基于 **FastAPI + WebSocket** 的AI编程助手微服务，核心引擎对齐Claude Code的Agent Loop思想：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Eruitah 智能编程沙盒 v4                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    WebSocket     ┌──────────────────┐     API      ┌──────────┐
│  │ Qt/C++ 客户端 │ <─────────────> │  FastAPI (main)   │ ──────────> │  LLM API  │
│  │ Monaco Editor │   双向实时通信   │  main.py v4       │ <────────── │  Claude   │
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

### 19.2 核心功能

| 功能 | 说明 |
|------|------|
| AI编程助手 | 基于Claude/GPT-4o，自动编写、修改、调试代码 |
| 工具调用 | 5大工具：bash、file_edit、file_read、glob、grep |
| 实时流式 | WebSocket双向通信，实时推送Agent思考过程 |
| 自愈机制 | 工具执行失败自动分析错误并重试 |
| 安全沙盒 | 危险命令拦截、路径越权检测、超时保护 |
| 多模型支持 | OpenAI兼容接口 + Anthropic Claude |

### 19.3 工具集详解

#### 19.3.1 bash - 命令执行器

```python
# 工具定义
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

#### 19.3.2 file_edit - 文件编辑器

```python
# 工具定义
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

#### 19.3.3 file_read - 文件读取

```python
# 工具定义
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

#### 19.3.4 glob - 文件模式匹配

```python
# 工具定义
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

#### 19.3.5 grep - 正则搜索

```python
# 工具定义
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

### 19.4 Agent Loop核心流程

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

### 19.5 WebSocket协议

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
// 运行任务
{"action": "run", "task": "写一个二叉树", "model": "gpt-4o"}

// 心跳
{"action": "ping"}

// 关闭连接
{"action": "close"}
```

**服务端响应：**

```json
{"type": "pong"}
{"type": "finish", "data": "...", "task_id": "xxx"}
```

### 19.6 REST API

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

### 19.7 Qt客户端对接示例

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
        // 打字机效果
        QString chunk = obj["content"].toString();
        ui->codeEditor->insertPlainText(chunk);
    }
    else if (type == "file_updated") {
        // 完整文件内容
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

### 19.8 项目结构

```
eruitah-sandbox/
├── main.py                    # FastAPI Web服务入口
├── agent_runner.py            # Agent核心引擎（run_agent生成器）
├── bash_executor.py           # Bash命令执行器（安全沙盒）
├── file_editor.py             # 文件编辑器（SEARCH/REPLACE模式）
├── file_read_tool.py          # 文件读取工具（行号过滤）
├── glob_tool.py               # Glob文件模式匹配
├── grep_tool.py               # Grep正则搜索（rg/grep/python三级回退）
├── tool_registry.py           # 工具注册表
├── memory_manager.py          # 记忆管理器
├── requirements.txt           # Python依赖
├── Dockerfile                 # Docker构建文件
├── venv/                      # Python虚拟环境
└── static/
    └── coding_lab.html        # Web IDE界面
```
